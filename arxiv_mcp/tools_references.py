"""MCP tools for the three search directions: references cited by a paper,
papers citing it, and the paper's index terms."""

from __future__ import annotations

import asyncio
import re
from typing import Any

from arxiv_api import normalise_id, query, strip_version
from index_terms import explicit_terms, title_terms
from pdf_text import extract_pages, pdf_path
from references import AUTHORS_ORG, extract, norm_title


async def extract_references(arxiv_id: str, whole_document: bool = False) -> dict[str, Any]:
    """Pull every reference entry out of a paper's reference list.

    Identifiers: uses a pattern that tolerates whitespace inside identifiers,
    because PDF text extraction breaks 'arxiv.org/abs/2511.05269' across lines
    both after 'abs/' and inside the number. The response reports both the
    tolerant count and the strict count so the gap is visible.

    Entries: the reference section is split into entries and the bibliography
    style is detected deterministically from them (`reference_style`, one of
    author_year_surname_first, numbered_initials_first, numbered_surname_first,
    numbered_lncs, apa, unknown). Each entry is then parsed by position for that
    style into `authors` (surnames), `title` and `year`, alongside its arXiv id
    or DOI if it carries one. Entries with no identifier are listed under
    `entries_without_identifier`; pass the paper to resolve_references to look
    them up by exact title. `entry_count` against `arxiv_count` shows how much
    of the bibliography identifiers alone cover.

    By default only the text after the last 'References' heading is scanned for
    identifiers. Set `whole_document` to scan everything, which also catches
    identifiers cited inline or in footnotes. Entry splitting always uses the
    reference section only.
    """
    return await extract(normalise_id(arxiv_id), whole_document)


async def resolve_references(arxiv_id: str) -> dict[str, Any]:
    """Resolve a paper's reference list to arXiv identifiers, deterministically.

    For each entry from extract_references: an entry that carries an arXiv id
    is taken as is. An entry without one is searched with one query that ANDs
    its unambiguous title words on the ti: field (words whose spelling PDF
    extraction left uncertain are omitted), and a hit is accepted only when the
    hit's title equals the parsed title after normalisation (lowercase, '&' to
    'and', then letters and digits only, so joined, split and hyphenated words
    compare equal). No fuzzy matching. Everything else is reported as unresolved
    with the reason: no title parsed, no hits, or hits whose titles did not
    match (listed, so a human can decide).

    Returns `resolved_ids` (identifier and title-resolved ids, deduplicated,
    ready for get_papers), per-entry `status`, and counts. One arXiv query per
    identifier-less entry, throttled, so a long bibliography takes a minute.
    """
    aid = normalise_id(arxiv_id)
    ext = await extract(aid)
    results: list[dict[str, Any]] = []
    resolved_ids: list[str] = []
    for e in ext["entries"]:
        rec: dict[str, Any] = {"n": e["n"], "title": e["title"], "authors": e["authors"], "year": e["year"]}
        if e["arxiv_id"]:
            rec.update(status="identifier", arxiv_id=e["arxiv_id"])
            resolved_ids.append(e["arxiv_id"])
        elif not e["title"]:
            rec.update(status="unresolved", arxiv_id=None, reason="no title parsed", text=e["text"][:200])
        elif not e["title_query"]:
            rec.update(status="unresolved", arxiv_id=None, reason="no usable title words", text=e["text"][:200])
        else:
            want = norm_title(e["title"])
            rec["query"] = e["title_query"]
            hits, _ = await query({"search_query": e["title_query"], "max_results": 10})
            match = next((h for h in hits if norm_title(h.title) == want), None)
            if match:
                rec.update(status="resolved", arxiv_id=strip_version(match.id), matched_title=match.title)
                resolved_ids.append(strip_version(match.id))
            elif hits:
                rec.update(status="unresolved", arxiv_id=None, reason="hits but no exact title match",
                           candidates=[{"id": strip_version(h.id), "title": h.title} for h in hits[:3]])
            else:
                rec.update(status="unresolved", arxiv_id=None, reason="no hits",
                           doi=e["doi"], organisation_author=bool(AUTHORS_ORG.match(e["text"])))
        results.append(rec)
    seen: set[str] = set()
    resolved_ids = [i for i in resolved_ids if not (i in seen or seen.add(i))]
    counts = {
        "entry_count": ext["entry_count"],
        "identifier": sum(1 for r in results if r["status"] == "identifier"),
        "resolved_by_title": sum(1 for r in results if r["status"] == "resolved"),
        "unresolved": sum(1 for r in results if r["status"] == "unresolved"),
    }
    return {
        "id": aid,
        "reference_style": ext["reference_style"],
        "counts": counts,
        "resolved_ids": resolved_ids,
        "entries": results,
        "unresolved": [r for r in results if r["status"] == "unresolved"],
    }


async def find_citations_in_text(
    candidate_ids: list[str],
    target_id: str,
    target_aliases: list[str] | None = None,
) -> dict[str, Any]:
    """Full-text scan: which of `candidate_ids` cite `target_id`?

    Citation indexes lag on recent preprints by months. This downloads each
    candidate's PDF and searches its text for the target's identifier, the
    target's title (fetched from arXiv, matched case-insensitively with any
    whitespace or line break between words), and any short names in
    `target_aliases` (for example a method name or acronym). The title search
    is what catches a citation to a workshop or venue version that carries no
    arXiv id. Returns the candidates that cite the target, with the page and
    the matched string, plus the candidates whose PDF could not be read.
    Each download is throttled, so scanning hundreds of papers takes a while.
    """
    target = strip_version(normalise_id(target_id))
    needles = [re.compile(re.escape(target).replace(r"\.", r"\s*\.\s*"))]
    title_used: str | None = None
    try:
        found, _ = await query({"id_list": target, "max_results": 1})
        if found and found[0].title:
            title_used = found[0].title
            words = re.findall(r"[A-Za-z0-9]+", title_used)
            if len(words) >= 3:
                needles.append(re.compile(r"\W*".join(re.escape(w) for w in words), re.IGNORECASE))
    except Exception:
        title_used = None
    for alias in target_aliases or []:
        if alias.strip():
            needles.append(re.compile(re.escape(alias.strip()), re.IGNORECASE))

    citing: list[dict[str, Any]] = []
    not_citing: list[str] = []
    failed: list[dict[str, str]] = []
    for raw in candidate_ids:
        try:
            cid = normalise_id(raw)
            if strip_version(cid) == target:
                continue
            path = await pdf_path(cid)
            pages = await asyncio.to_thread(extract_pages, path)
        except Exception as e:  # noqa: BLE001 - report, don't abort the scan
            failed.append({"id": raw, "error": str(e)})
            continue
        hit = None
        for page_no, text in enumerate(pages, start=1):
            for needle in needles:
                m = needle.search(text)
                if m:
                    hit = {"id": cid, "page": page_no, "matched": m.group(0)}
                    break
            if hit:
                break
        if hit:
            citing.append(hit)
        else:
            not_citing.append(cid)

    return {
        "target": target,
        "title_searched": title_used,
        "aliases_searched": [a.strip() for a in (target_aliases or []) if a.strip()],
        "scanned": len(citing) + len(not_citing),
        "citing": citing,
        "not_citing": not_citing,
        "failed": failed,
    }


async def get_index_terms(arxiv_id: str) -> dict[str, Any]:
    """Index terms for a paper, and the arXiv queries built from them.

    Source, in order:
    1. `keywords`: the paper's own Keywords, Index Terms, or CCS Concepts line
       from the PDF's first pages, parsed and returned verbatim.
    2. `title`: when the paper has no such line, the title's phrase runs (two or
       more words between stopwords and punctuation) and its single non-stopword
       words, both. Nothing is taken from the abstract.

    Both are deterministic: same paper, same terms, same queries. Also returns
    `categories` (the arXiv subject classes) and `queries`, one per term, of the
    form `abs:"<term>" AND cat:<primary category>`. Use the queries verbatim for
    the index-term sweep so that two runs on the same anchor search the same
    space.
    """
    aid = normalise_id(arxiv_id)
    papers, _ = await query({"id_list": aid, "max_results": 1})
    if not papers:
        raise ValueError(f"No arXiv record for {aid}")
    paper = papers[0]
    path = await pdf_path(aid)
    pages = await asyncio.to_thread(extract_pages, path)
    keywords = explicit_terms("\n".join(pages[:2]))
    from_title = title_terms(paper.title)
    if keywords:
        source, terms = "keywords", keywords
    else:
        source, terms = "title", from_title["phrases"] + [w for w in from_title["words"] if w not in from_title["phrases"]]
    primary = paper.primary_category or (paper.categories[0] if paper.categories else "")
    queries = [f'abs:"{t}"' + (f" AND cat:{primary}" if primary else "") for t in terms]
    return {
        "id": aid,
        "title": paper.title,
        "primary_category": primary,
        "categories": paper.categories,
        "source": source,
        "keywords": keywords,
        "title_phrases": from_title["phrases"],
        "title_words": from_title["words"],
        "terms": terms,
        "queries": queries,
    }
