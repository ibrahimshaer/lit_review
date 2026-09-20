"""Index terms: the paper's Keywords / Index Terms / CCS Concepts line, else the title."""

from __future__ import annotations

import re

_EXPLICIT_TERMS = re.compile(
    r"(?:Index\s+Terms|Keywords?|Key\s+words|CCS\s+Concepts)\s*[:—–\-]?\s*(.+?)"
    r"(?=\n\s*\n|\n\s*(?:\d+\.?\s*)?(?:Introduction|INTRODUCTION)\b|$)",
    re.IGNORECASE | re.DOTALL,
)

STOP = set("""
a an the and or but of in on at to for from by with without as is are was were be been being this that these those it its
we our us they their them he she his her you your i my me which who whom whose what when where why how not no nor so than
then there here also such via into onto over under between among across through during while both either each any all
some more most many much few several other another same different new recent existing current various can could may might
must shall should will would do does did done have has had having using use used uses based paper work approach method
methods results show shows shown demonstrate demonstrates present presents propose proposes proposed introduce introduces
however therefore thus moreover furthermore first second third finally further two three four five six seven eight nine ten
et al eg ie vs
combine combines combining identify identifies identifying rely relies relying create creates creating construct constructs
evaluate evaluates evaluating formulate formulates balance balances present presents span spans spanning achieve achieves
outperform outperforms enable enables enabling leverage leverages remain remains provide provides require requires suggest
suggests reveal reveals find finds observe observes report reports argue argues consider considers develop develops design
designs build builds apply applies conduct conducts perform performs obtain obtains yield yields indicate indicates highlight
highlights include includes including allow allows make makes made take takes taken give gives given see seen study studies
investigate investigates explore explores address addresses improve improves reduce reduces increase increases compare
compared against within without across toward towards
""".split())


def is_stop(low: str) -> bool:
    return low in STOP or (low.endswith("ly") and len(low) > 4 and "-" not in low)


def explicit_terms(first_pages: str) -> list[str]:
    """The paper's own keywords line, split on separators, at most 20 terms."""
    m = _EXPLICIT_TERMS.search(first_pages)
    if not m:
        return []
    raw = re.sub(r"\s+", " ", m.group(1))
    parts = re.split(r"\s*[;,•·]\s*|\s+→\s+", raw)
    out: list[str] = []
    for p in parts:
        p = p.strip(" .")
        if 2 <= len(p) <= 80 and p.lower() not in {t.lower() for t in out}:
            out.append(p)
    return out[:20]


def _phrase_runs(text: str) -> list[list[tuple[str, str]]]:
    """Maximal runs of non-stopword tokens between punctuation and stopwords."""
    runs: list[list[tuple[str, str]]] = []
    for seg in re.split(r"[.,;:()\[\]—–\"?!]|\s-\s", text):
        run: list[tuple[str, str]] = []
        for tok in re.findall(r"[A-Za-z][A-Za-z\-]*", seg):
            low = tok.lower().strip("-")
            if not low or len(low) < 3 or is_stop(low):
                if run:
                    runs.append(run)
                run = []
            else:
                run.append((tok, low))
        if run:
            runs.append(run)
    return runs


def title_terms(title: str) -> dict[str, list[str]]:
    """Fallback index terms when the paper has no keywords line: the title's
    phrase runs (two or more words between stopwords and punctuation) and its
    single non-stopword words. Hyphenated words stay whole."""
    phrases: list[str] = []
    for run in _phrase_runs(title):
        if len(run) >= 2:
            phrases.append(" ".join(low for _, low in run))
    words: list[str] = []
    for tok in re.findall(r"[A-Za-z][A-Za-z\-]*", title):
        low = tok.lower().strip("-")
        if low and len(low) >= 3 and not is_stop(low) and low not in words:
            words.append(low)
    return {"phrases": phrases, "words": words}
