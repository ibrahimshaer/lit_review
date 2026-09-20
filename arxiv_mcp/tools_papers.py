"""MCP tools for papers: search, metadata, PDFs, full text, categories."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import asdict
from typing import Any, Literal

from arxiv_api import Paper, normalise_id, strip_version
from arxiv_api import query as api_query
from config import CACHE_DIR, MAX_PAGE_SIZE
from pdf_text import extract_pages, page_marked, pdf_path, strip_reference_list


async def search_papers(
    query: str,
    max_results: int = 25,
    start: int = 0,
    sort_by: Literal["relevance", "lastUpdatedDate", "submittedDate"] = "relevance",
    sort_order: Literal["ascending", "descending"] = "descending",
    category: str | None = None,
) -> dict[str, Any]:
    """Search arXiv with the API query syntax.

    `query` uses arXiv field prefixes: ti: (title), au: (author), abs: (abstract),
    cat: (category), all: (everything). Combine with AND, OR, ANDNOT, and quote
    phrases. Examples:
        all:"agent harness" AND all:safety
        ti:"prompt injection" AND cat:cs.CR
        au:vaswani AND ti:attention

    `category` is a convenience that ANDs a cat: clause onto the query.
    Returns the matching papers with full abstracts, the total number of hits
    on arXiv, and the `start` offset to pass for the next page.
    """
    max_results = max(1, min(max_results, MAX_PAGE_SIZE))
    q = query.strip()
    if category:
        q = f"({q}) AND cat:{category}"
    papers, total = await api_query(
        {
            "search_query": q,
            "start": start,
            "max_results": max_results,
            "sortBy": sort_by,
            "sortOrder": sort_order,
        }
    )
    # Full results, abstracts included, go to disk. Only a compact list comes back,
    # so the sweep does not sit in the conversation and get re-read every turn.
    results_dir = CACHE_DIR / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^A-Za-z0-9]+", "_", q).strip("_")[:80]
    out = results_dir / f"{slug}__start{start}.json"
    out.write_text(json.dumps({
        "query": q, "total_results": total, "start": start, "returned": len(papers),
        "papers": [asdict(p) for p in papers],
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    return {
        "query": q,
        "total_results": total,
        "start": start,
        "returned": len(papers),
        "next_start": start + len(papers) if start + len(papers) < total else None,
        "results_file": str(out),
        "papers": [{"id": p.id, "title": p.title, "published": p.published[:10]} for p in papers],
        "note": "Abstracts and authors are in results_file; read it from disk when you need them.",
    }


async def get_paper(arxiv_id: str) -> dict[str, Any]:
    """Fetch metadata and the full abstract for one arXiv identifier."""
    aid = normalise_id(arxiv_id)
    papers, _ = await api_query({"id_list": aid, "max_results": 1})
    if not papers:
        raise ValueError(f"No arXiv record for {aid}")
    return asdict(papers[0])


async def get_papers(arxiv_ids: list[str]) -> dict[str, Any]:
    """Fetch metadata and full abstracts for a list of identifiers in one call.

    Use this for the backward and forward lists and for the abstracts step:
    one request per 100 identifiers instead of one per paper. Identifiers
    that arXiv does not know are listed under `missing`.
    """
    wanted: list[str] = []
    bad: list[str] = []
    for raw in arxiv_ids:
        try:
            wanted.append(normalise_id(raw))
        except ValueError:
            bad.append(raw)

    found: list[Paper] = []
    for i in range(0, len(wanted), 100):
        chunk = wanted[i : i + 100]
        papers, _ = await api_query({"id_list": ",".join(chunk), "max_results": len(chunk)})
        found.extend(papers)

    got = {strip_version(p.id) for p in found}
    missing = [w for w in wanted if strip_version(w) not in got]
    return {
        "requested": len(arxiv_ids),
        "found": len(found),
        "missing": missing,
        "invalid": bad,
        "papers": [asdict(p) for p in found],
    }


async def download_pdf(arxiv_id: str) -> dict[str, Any]:
    """Download a paper's PDF into the cache directory and return its local path."""
    aid = normalise_id(arxiv_id)
    path = await pdf_path(aid)
    return {"id": aid, "path": str(path), "bytes": path.stat().st_size}


async def get_paper_text(
    arxiv_id: str,
    pages: str | None = None,
    max_chars: int = 200_000,
) -> dict[str, Any]:
    """Extract the text of a paper's PDF with '=== page N ===' markers.

    The reference list is removed and the page-marked text is written to a
    file in the cache; the response names the file. `pages` selects a range
    such as "1-3" or "7" (1-indexed, inclusive) to also return inline, cut at
    `max_chars`; omit it to get only the file. Page markers make it possible
    to cite a page for every claim taken from the text.
    """
    aid = normalise_id(arxiv_id)
    path = await pdf_path(aid)
    all_pages = await asyncio.to_thread(extract_pages, path)

    first, last = 1, len(all_pages)
    if pages:
        m = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+))?\s*", pages)
        if not m:
            raise ValueError("pages must look like '5' or '2-6'")
        first = int(m.group(1))
        last = int(m.group(2) or first)
        if first < 1 or last > len(all_pages) or first > last:
            raise ValueError(f"page range {pages!r} outside 1-{len(all_pages)}")

    marked, removed = strip_reference_list(page_marked(all_pages))

    text_dir = CACHE_DIR / "text"
    text_dir.mkdir(parents=True, exist_ok=True)
    out = text_dir / f"{aid}.md"
    out.write_text(marked, encoding="utf-8")

    result: dict[str, Any] = {
        "id": aid,
        "page_count": len(all_pages),
        "text_file": str(out),
        "chars": len(marked),
        "references_removed_chars": removed,
        "note": "Full page-marked text is in text_file; read the pages you need from disk. "
                "The reference list has been removed; use extract_references or resolve_references for it.",
    }
    if pages:
        # A small explicit range is still returned inline for convenience.
        sel = re.search(rf"=== page {first} ===.*?(?==== page {last + 1} ===|\Z)", marked, re.DOTALL)
        inline = sel.group(0) if sel else ""
        result["pages_returned"] = f"{first}-{last}"
        result["truncated"] = len(inline) > max_chars
        result["text"] = inline[:max_chars]
    return result


async def list_categories() -> dict[str, str]:
    """Common arXiv category codes for use in cat: queries."""
    return {
        "cs.AI": "Artificial Intelligence",
        "cs.CL": "Computation and Language",
        "cs.CR": "Cryptography and Security",
        "cs.CV": "Computer Vision",
        "cs.CY": "Computers and Society",
        "cs.DB": "Databases",
        "cs.DC": "Distributed Computing",
        "cs.HC": "Human-Computer Interaction",
        "cs.IR": "Information Retrieval",
        "cs.LG": "Machine Learning",
        "cs.MA": "Multiagent Systems",
        "cs.NE": "Neural and Evolutionary Computing",
        "cs.RO": "Robotics",
        "cs.SE": "Software Engineering",
        "stat.ML": "Machine Learning (Statistics)",
        "math.OC": "Optimization and Control",
        "eess.SP": "Signal Processing",
        "q-bio.QM": "Quantitative Methods",
        "econ.EM": "Econometrics",
    }
