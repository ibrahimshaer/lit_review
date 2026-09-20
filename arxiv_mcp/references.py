"""Reference-list parsing: split a bibliography into entries, detect its style
deterministically, parse each entry by position into authors, title and year,
and normalise titles for exact matching.

The splitter and title parser have been tuned against real bibliographies.
Change what they accept only with a test case that shows why."""

from __future__ import annotations

import asyncio
import re
from typing import Any

from arxiv_api import DOI, ID_IN_TEXT, ID_TOLERANT, normalise_id, strip_version
from index_terms import STOP
from pdf_text import REF_HEADING, extract_pages, find_reference_section, pdf_path

# ---------------------------------------------------------------------------
# Entry splitting
# ---------------------------------------------------------------------------

# Bibliography layouts handled by the splitter:
#   numbered:      "[12] Author, ..." at the start of a line
#   dot-numbered:  "12. Author, ..." counting up from 1 (Springer LNCS)
#   author-year:   "Surname, I., Surname, I. ..." or "Organisation. ..." at the start of a line
_ENTRY_NUMBERED = re.compile(r"^\s*\[(\d{1,3})\]\s+", re.MULTILINE)
_ENTRY_DOT_NUMBERED = re.compile(r"^\s*(\d{1,3})\.\s+(?=[A-Z])", re.MULTILINE)
_ORG_NAME = r"[A-Z][A-Za-z&]+(?:\s[A-Z][A-Za-z&]+){0,3}\."   # Anthropic.  OpenAI.  Google DeepMind.
_ENTRY_AUTHOR = re.compile(
    r"^(?:[A-Z][\w\-'’À-ɏ]+,\s+(?:[A-Z]\s?\.\s?(?:-?[A-Z]\s?\.\s?)*)"  # Surname, I. or Surname, I.-J.
    rf"|{_ORG_NAME}\s)",
    re.MULTILINE,
)
# An entry normally ends with a year, a page range, a URL, or an arXiv id.
_ENTRY_END = re.compile(
    r"(?:(?:19|20)\d\d[a-z]?|\d+\s*[–—-]\s*\d+|pp\.\s*\d+|https?://\S+|\d{4}\s*\.\s*\d{4,5}(?:v\d+)?)\s*[.,;)]*\s*$"
)
_LOWER_WORD = re.compile(r"\b[a-z][a-z\-]{2,}\b")

JOIN = "­"   # soft hyphen: marks a word joined across a line-ending hyphen


def _looks_like_authors(piece: str) -> bool:
    """An author block has almost no lowercase words; a title has many."""
    words = [w for w in _LOWER_WORD.findall(piece) if w not in {"and", "et", "al", "eds"}]
    return len(words) < 2


def _clean_entry(text: str) -> str:
    # A hyphen at a line end is either a broken word ("Adver-\nsarial") or a real
    # compound ("tool-\nintegrated"). Nothing in the text says which, so the join
    # point is marked and both spellings are tried when the entry is looked up.
    text = re.sub(r"-\s*\n\s*([a-z])", rf"{JOIN}\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\b([A-Z]) \.", r"\1.", text)          # "Y ." -> "Y."
    text = re.sub(r"[`´ˆ˜¨ˇ]\s?", "", text)  # accent rendered as a mark: "Tram` er" -> "Tramer"
    text = text.replace("{", "").replace("}", "")         # BibTeX brace protection: "{StruQ}"
    return text


def _spellings(marked: str) -> list[str]:
    """The joined spelling first, then the hyphenated one, if they differ."""
    joined = marked.replace(JOIN, "")
    hyphenated = marked.replace(JOIN, "-")
    return [joined] if joined == hyphenated else [joined, hyphenated]


def _chunks(body: str, starts: list[int]) -> list[str]:
    return [body[s:e] for s, e in zip(starts, starts[1:] + [len(body)])]


def split_reference_entries(scope: str) -> list[str]:
    """Split a reference section into entries. Heuristic; see extract_references."""
    body = REF_HEADING.sub("", scope, count=1)
    numbered = list(_ENTRY_NUMBERED.finditer(body))
    if len(numbered) >= 3:
        return [_clean_entry(c) for c in _chunks(body, [m.start() for m in numbered]) if c.strip()]

    # Dot-numbered entries ("1. Ai, L., ...", Springer LNCS). A year or a page
    # number at a line start also looks like "2025. ", so only a run of labels
    # that counts up from 1 is accepted.
    seq: list[re.Match] = []
    expect = 1
    for m in _ENTRY_DOT_NUMBERED.finditer(body):
        if int(m.group(1)) == expect:
            seq.append(m)
            expect += 1
    if len(seq) >= 3:
        return [_clean_entry(c) for c in _chunks(body, [m.start() for m in seq]) if c.strip()]

    starts = [m.start() for m in _ENTRY_AUTHOR.finditer(body)]
    if not starts:
        return []
    # Merge a chunk into the previous one when the previous does not look finished,
    # which happens when a long author list wraps onto a new line.
    merged: list[str] = []
    for c in _chunks(body, starts):
        if merged and not _ENTRY_END.search(merged[-1].strip()):
            merged[-1] = merged[-1] + c
        else:
            merged.append(c)
    return [_clean_entry(c) for c in merged if c.strip()]


# ---------------------------------------------------------------------------
# Style detection and positional parsing
# ---------------------------------------------------------------------------

_NAME = r"[A-Z][^\s,.;:()\[\]\"]+"   # a surname: capital, then anything up to a separator
_AUTHORS_SURNAME_FIRST = re.compile(   # "Bai, F., Liu, R., and Yang, Y. "
    rf"^(?:{_NAME}(?:\s{_NAME})?,\s+(?:[A-Z]\.\s?-?){{1,3}},?\s*(?:and\s+|&\s+)?|et al\.,?\s*)+"
)
_AUTHORS_INITIALS_FIRST = re.compile(  # "F. Bai, R. Liu, and Y. Yang. "
    rf"^(?:(?:[A-Z]\.\s?-?){{1,3}}{_NAME}(?:\s{_NAME})?,?\s*(?:and\s+|&\s+)?|et al\.,?\s*)+\.?\s*"
)
AUTHORS_ORG = re.compile(rf"^{_ORG_NAME}\s+")   # "Anthropic. "
_SURNAME_BEFORE_INITIALS = re.compile(rf"({_NAME}(?:\s{_NAME})?),\s+(?:[A-Z]\.\s?-?){{1,3}}")
_SURNAME_AFTER_INITIALS = re.compile(rf"(?:[A-Z]\.\s?-?){{1,3}}\s*({_NAME}(?:\s{_NAME})?)")
_APA_YEAR = re.compile(r"\((\d{4}[a-z]?)\)\.?\s*")
_YEAR = re.compile(r"\b((?:19|20)\d{2})[a-z]?\b")
_QUOTED = re.compile(r"[\"“]([^\"”]{8,}?)[\"”,]")
# A title ends at the first period that is followed by whitespace, an uppercase
# letter (PDF extraction glues "openclaw.arXiv"), or the end of the entry.
_TITLE_STOP = re.compile(
    r"\.(?=\s|[A-Z]|arXiv|$)"          # sentence-ending period
    r"|[?!](?=\s+[A-Z]|\s*$)"          # a title that is a question, before the venue
    r"|\s\((?:19|20)\d{2}[a-z]?\)"     # LNCS: "Title (2025), https://..."
)
_NUMBERED_PREFIX = re.compile(r"^\s*(?:\[\d{1,3}\]|\d{1,3}\.(?=\s+[A-Z]))\s*")

REFERENCE_STYLES = (
    "author_year_surname_first",   # natbib / ICML / NeurIPS: Bai, F., and Liu, R. Title. Venue, 2025.
    "numbered_initials_first",     # IEEE / ACM: [3] F. Bai and R. Liu, "Title," in Proc. X, 2025.
    "numbered_surname_first",      # [3] Bai, F., Liu, R. Title. Venue, 2025.
    "numbered_lncs",               # Springer LNCS: 3. Bai, F., Liu, R.: Title. In: Venue, pp. 1-8 (2025)
    "apa",                         # Bai, F., & Liu, R. (2025). Title. Venue.
    "unknown",
)


def detect_reference_style(entries: list[str]) -> str:
    """Deterministic style detection from the entries themselves. Majority rules."""
    if not entries:
        return "unknown"
    n = len(entries)
    numbered = sum(1 for e in entries if _NUMBERED_PREFIX.match(e))
    if numbered >= n / 2:
        bodies = [_NUMBERED_PREFIX.sub("", e) for e in entries]
        initials_first = sum(1 for b in bodies if re.match(r"^(?:[A-Z]\.\s?-?){1,3}\s*[A-Z]", b))
        surname_first = sum(1 for b in bodies if re.match(rf"^{_NAME},\s+[A-Z]\.", b))
        # LNCS: surname-first author block that ends in a colon before the title
        lncs = 0
        for b in bodies:
            m = _AUTHORS_SURNAME_FIRST.match(b)
            if m and b[m.end():].lstrip().startswith(":"):
                lncs += 1
        if initials_first >= n / 2:
            return "numbered_initials_first"
        if lncs >= n / 2:
            return "numbered_lncs"
        if surname_first >= n / 2:
            return "numbered_surname_first"
        return "unknown"
    apa = sum(1 for e in entries if _APA_YEAR.search(e[:250]))
    if apa >= n / 2:
        return "apa"
    surname_first = sum(1 for e in entries if _AUTHORS_SURNAME_FIRST.match(e) or AUTHORS_ORG.match(e))
    if surname_first >= n / 2:
        return "author_year_surname_first"
    return "unknown"


def _title_from(rest: str) -> str:
    """Title from the text that follows the author block (and year, for APA)."""
    rest = rest.lstrip(" .,;:")
    q = _QUOTED.match(rest)
    if q:
        return q.group(1).strip().rstrip(".,")
    m = _TITLE_STOP.search(rest)
    title = rest[: m.start()] if m else rest
    return title.strip().rstrip(".,;:")


def parse_reference(entry: str, style: str) -> dict:
    """Authors (surnames), title and year from one cleaned entry, by style.
    Positional, not heuristic: each style says where the title starts and ends."""
    body = _NUMBERED_PREFIX.sub("", entry).strip()
    authors: list[str] = []
    title = ""
    year = None

    if style in ("author_year_surname_first", "numbered_surname_first", "numbered_lncs", "apa"):
        m = _AUTHORS_SURNAME_FIRST.match(body)
        if m:
            authors = _SURNAME_BEFORE_INITIALS.findall(m.group(0))
            rest = body[m.end():]
        else:
            o = AUTHORS_ORG.match(body)
            if o:
                authors = [o.group(0).strip(" .")]
                rest = body[o.end():]
            else:
                rest = body
        if style == "apa":
            y = _APA_YEAR.match(rest.lstrip(" .,"))
            if y:
                year = y.group(1)
                rest = rest.lstrip(" .,")[y.end():]
        title = _title_from(rest)

    elif style == "numbered_initials_first":
        m = _AUTHORS_INITIALS_FIRST.match(body)
        if m:
            authors = _SURNAME_AFTER_INITIALS.findall(m.group(0))
            rest = body[m.end():]
        else:
            rest = body
        title = _title_from(rest)

    else:  # unknown: best effort, flagged by the caller
        for pat in (_AUTHORS_SURNAME_FIRST, _AUTHORS_INITIALS_FIRST, AUTHORS_ORG):
            m = pat.match(body)
            if m:
                rest = body[m.end():]
                break
        else:
            rest = body
        title = _title_from(rest)

    if year is None:
        years = _YEAR.findall(entry)
        year = years[-1] if years else None
    if len(title.split()) < 2 or _looks_like_authors(title):
        title = ""
    return {"authors": authors, "title": title[:250], "year": year}


# ---------------------------------------------------------------------------
# Title matching
# ---------------------------------------------------------------------------


def norm_title(t: str) -> str:
    """Normalisation used for exact title matching: lowercase, '&' to 'and', then
    only letters and digits are kept. Spaces go too, so a word joined or split by
    PDF extraction ("toolintegrated", "tool-integrated", "tool integrated") still
    compares equal, and so does an apostrophe the extractor mangled."""
    t = t.lower().replace("&", " and ").replace(JOIN, "")
    return re.sub(r"[^a-z0-9]+", "", t)


def title_query(marked_title: str) -> str:
    """One arXiv query for a parsed title: every unambiguous title word, ANDed on
    the ti: field. Words that contain a line-break join (their spelling is
    uncertain) or a character the extractor mangled are left out, hyphenated
    words are split, and words under three letters are dropped. The hit is then
    checked by exact normalised title equality, so leaving words out of the
    query cannot produce a false acceptance."""
    words: list[str] = []
    for tok in marked_title.split():
        if JOIN in tok or not re.fullmatch(r"[A-Za-z0-9\-:;,.()'\"]+", tok):
            continue
        for part in re.split(r"[-]", tok):
            part = re.sub(r"[^A-Za-z0-9]", "", part).lower()
            if len(part) >= 3 and part not in words and part not in STOP:
                words.append(part)
    return " AND ".join(f"ti:{w}" for w in words)


# ---------------------------------------------------------------------------
# Whole-paper extraction
# ---------------------------------------------------------------------------


def _dedupe(ids: list[str], own: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for i in ids:
        base = strip_version(i)
        if base != own and base not in seen:
            seen.add(base)
            out.append(base)
    return out


async def extract(aid: str, whole_document: bool = False) -> dict[str, Any]:
    """Identifiers (tolerant and strict counts) and parsed entries from a paper's
    reference list. The tool extract_references returns this unchanged."""
    path = await pdf_path(aid)
    pages = await asyncio.to_thread(extract_pages, path)
    full = "\n".join(pages)
    refs = find_reference_section(full)
    scope = full if whole_document else refs

    tolerant: list[str] = []
    for m in ID_TOLERANT.finditer(scope):
        cleaned = re.sub(r"\s+", "", m.group(1))
        try:
            tolerant.append(normalise_id(cleaned))
        except ValueError:
            continue
    strict = [normalise_id(re.sub(r"^(?:arxiv\.org/(?:abs|pdf)/|arXiv:\s*)", "", m.group(0), flags=re.IGNORECASE))
              for m in ID_IN_TEXT.finditer(scope)]
    own = strip_version(aid)
    tolerant_ids = _dedupe(tolerant, own)
    strict_ids = _dedupe(strict, own)
    dois = sorted({d.rstrip(".,;)") for d in DOI.findall(scope)})

    raw_entries = split_reference_entries(refs)
    style = detect_reference_style(raw_entries)
    entries: list[dict[str, Any]] = []
    for n, text in enumerate(raw_entries, start=1):
        m = ID_TOLERANT.search(text)
        entry_id: str | None = None
        if m:
            try:
                entry_id = strip_version(normalise_id(re.sub(r"\s+", "", m.group(1))))
            except ValueError:
                entry_id = None
        d = DOI.search(text)
        parsed = parse_reference(text, style)
        spellings = _spellings(parsed["title"]) if parsed["title"] else []
        entries.append(
            {
                "n": n,
                "text": text.replace(JOIN, "")[:500],
                "arxiv_id": entry_id,
                "doi": d.group(0).rstrip(".,;)") if d else None,
                "authors": [a.replace(JOIN, "") for a in parsed["authors"]],
                "title": spellings[0] if spellings else "",
                "title_spellings": spellings,
                "title_query": title_query(parsed["title"]) if parsed["title"] else "",
                "year": parsed["year"],
                "title_source": "heuristic" if style == "unknown" else f"parsed:{style}",
            }
        )
    without = [e for e in entries if not e["arxiv_id"] and not e["doi"]]
    return {
        "id": aid,
        "scanned": "whole document" if whole_document else "reference section",
        "scanned_chars": len(scope),
        "reference_style": style,
        "arxiv_ids": tolerant_ids,
        "arxiv_count": len(tolerant_ids),
        "strict_count": len(strict_ids),
        "recovered_by_tolerant_pattern": [i for i in tolerant_ids if i not in set(strict_ids)],
        "dois": dois,
        "entry_count": len(entries),
        "entries_with_identifier": len(entries) - len(without),
        "entries_without_identifier": without,
        "entries": entries,
    }
