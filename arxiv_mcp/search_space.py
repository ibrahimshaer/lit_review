"""Step 3 in one call: the three directions, the search-space artifact, the
abstract dump and the union file."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from arxiv_api import Paper, normalise_id, query, strip_version
from tools_references import find_citations_in_text, get_index_terms, resolve_references

# ---------------------------------------------------------------------------
# Table cell formatters
# ---------------------------------------------------------------------------


def _first_sentence(text: str) -> str:
    m = re.match(r"(.+?[.!?])(?:\s|$)", text.strip())
    return (m.group(1) if m else text.strip())[:300]


def _link(pid: str) -> str:
    return f"[{pid}](https://arxiv.org/abs/{pid})"


def _authors_short(authors: list[str]) -> str:
    return ", ".join(authors[:3]) + (" et al." if len(authors) > 3 else "")


def _row(pid: str, p: Paper, *extra: str) -> str:
    cells = [_link(pid), p.title, _authors_short(p.authors), p.published[:10], *extra]
    return "| " + " | ".join(cells) + " |"


async def _papers_by_id(ids: list[str]) -> dict[str, Paper]:
    """Metadata for a list of ids, 100 per request, keyed by versionless id."""
    out: dict[str, Paper] = {}
    for i in range(0, len(ids), 100):
        chunk = ids[i:i + 100]
        got, _ = await query({"id_list": ",".join(chunk), "max_results": len(chunk)})
        for p in got:
            out[strip_version(p.id)] = p
    return out


# ---------------------------------------------------------------------------
# The tool
# ---------------------------------------------------------------------------


async def build_search_space(
    arxiv_id: str,
    out_dir: str,
    short_name: str = "",
    queries_file: str = "queries.json",
    forward_min_age_days: int = 90,
    max_per_query: int = 25,
) -> dict[str, Any]:
    """Run the whole of Step 3 deterministically and write its artifacts.

    In one call: resolves the anchor's references (resolve_references), builds
    or loads the index-term queries (get_index_terms, persisted to
    `queries_file` in `out_dir`), runs every query, runs the full-text citation
    scan over sweep papers posted after the anchor when the anchor is at least
    `forward_min_age_days` old (otherwise the direction is marked skipped),
    and writes:

      <out_dir>/<id>_search_space.md   Method, Totals, three direction tables,
                                       unresolved references, Caveats
      <out_dir>/scratch/abstracts.md   one full abstract per paper in the space
      <out_dir>/scratch/union.json     every id with the directions it came from

    Nothing is ranked or cut. Selection from the sweep is Step 4's reading
    judgement. Returns the totals so the caller can report them. A long
    bibliography or a large forward scan can take several minutes.
    """
    aid = strip_version(normalise_id(arxiv_id))
    out = Path(out_dir).resolve()
    (out / "scratch").mkdir(parents=True, exist_ok=True)
    today = time.strftime("%Y-%m-%d")

    anchors, _ = await query({"id_list": aid, "max_results": 1})
    if not anchors:
        raise ValueError(f"No arXiv record for {aid}")
    anchor = anchors[0]

    # --- queries -----------------------------------------------------------
    qpath = out / queries_file
    if qpath.exists():
        qdata = json.loads(qpath.read_text(encoding="utf-8"))
        queries_source = f"loaded from {queries_file}"
    else:
        terms = await get_index_terms(aid)
        qdata = {"anchor": aid, "source": terms["source"], "primary_category": terms["primary_category"],
                 "terms": terms["terms"], "queries": terms["queries"]}
        qpath.write_text(json.dumps(qdata, indent=2, ensure_ascii=False), encoding="utf-8")
        queries_source = f"built by get_index_terms and written to {queries_file}"

    # --- direction 1: cited ------------------------------------------------
    res = await resolve_references(aid)
    cited_ids = res["resolved_ids"]
    cited = await _papers_by_id(cited_ids)
    cited_missing = [i for i in cited_ids if i not in cited]

    # --- direction 3: sweep ------------------------------------------------
    sweep: dict[str, Paper] = {}
    hits: dict[str, list[int]] = {}
    qrows: list[dict[str, Any]] = []
    for n, q in enumerate(qdata["queries"], start=1):
        papers, total = await query({"search_query": q, "start": 0, "max_results": max_per_query,
                                     "sortBy": "relevance", "sortOrder": "descending"})
        qrows.append({"n": n, "query": q, "total": total, "returned": len(papers)})
        for p in papers:
            pid = strip_version(p.id)
            if pid == aid:
                continue
            sweep.setdefault(pid, p)
            hits.setdefault(pid, []).append(n)

    # --- direction 2: citing -----------------------------------------------
    anchor_date = anchor.published[:10]
    age_days = int((time.time() - time.mktime(time.strptime(anchor_date, "%Y-%m-%d"))) // 86400)
    skipped = age_days < forward_min_age_days
    citing: list[dict[str, Any]] = []
    scan: dict[str, Any] = {}
    if skipped:
        forward_status = (f"skipped: anchor posted {anchor_date}, {age_days} days ago, under the "
                          f"{forward_min_age_days}-day rule; nothing will cite it yet in a form the scan can find")
    else:
        candidates = [pid for pid, p in sweep.items() if p.published[:10] > anchor_date]
        scan = await find_citations_in_text(candidates, aid, [short_name] if short_name else None)
        citing = scan["citing"]
        forward_status = (f"ran: {len(candidates)} sweep papers posted after {anchor_date} scanned by full text "
                          f"for the id, the title and the alias; {len(citing)} citing, {len(scan['failed'])} unreadable")
    citing_papers = await _papers_by_id([c["id"] for c in citing]) if citing else {}

    # --- union ---------------------------------------------------------------
    union: dict[str, dict[str, Any]] = {}
    for pid, p in cited.items():
        union.setdefault(pid, {"paper": p, "directions": []})["directions"].append(1)
    for c in citing:
        pid = strip_version(c["id"])
        if pid in citing_papers:
            union.setdefault(pid, {"paper": citing_papers[pid], "directions": []})["directions"].append(2)
    for pid, p in sweep.items():
        union.setdefault(pid, {"paper": p, "directions": []})["directions"].append(3)

    # --- artifact ------------------------------------------------------------
    L: list[str] = []

    def w(*lines: str) -> None:
        """Append lines, then one blank line."""
        L.extend(lines)
        L.append("")

    c = res["counts"]
    w(f"# Search space for arXiv {aid}" + (f" ({short_name})" if short_name else ""))
    w(f"Anchor: {_link(aid)}, \"{anchor.title}\" ({_authors_short(anchor.authors)}). Posted {anchor_date}. "
      f"Primary category {anchor.primary_category}; categories {', '.join(anchor.categories)}.")
    w(f"Built {today} by `build_search_space` with the arXiv MCP tools only. Every row is an id a tool returned; "
      "nothing was added, ranked or cut. Selection from the sweep happens in Step 4.")
    w("## Method")
    w(f"**Direction 1, cited by the anchor.** `resolve_references`: reference style `{res['reference_style']}`, "
      f"{c['entry_count']} entries; {c['identifier']} carried an arXiv id, "
      f"{c['resolved_by_title']} resolved by exact normalised title, {c['unresolved']} unresolved. No cap.")
    w(f"**Direction 2, citing the anchor.** {forward_status}.")
    w(f"**Direction 3, index terms.** Queries {queries_source}; source of terms: `{qdata.get('source')}`. "
      f"Each query run once, {max_per_query} results by relevance, category {qdata.get('primary_category')}.")
    w("| # | Query | arXiv total hits | Returned |",
      "|---|---|---|---|",
      *[f"| {r['n']} | `{r['query']}` | {r['total']} | {r['returned']} |" for r in qrows])
    w("### Totals")
    w("| Direction | Returned |",
      "|---|---|",
      f"| 1. Cited by the anchor | {len(cited)} |",
      f"| 2. Citing the anchor | {len(citing_papers)}{' (skipped)' if skipped else ''} |",
      f"| 3. Index-term sweep | {len(sweep)} unique ({sum(r['returned'] for r in qrows)} rows) |",
      f"| **Union going into Step 4** | **{len(union)}** |")

    w(f"## Direction 1: cited by the anchor ({len(cited)})")
    w("| id | title | authors | date | first sentence of abstract |",
      "|---|---|---|---|---|",
      *[_row(pid, cited[pid], _first_sentence(cited[pid].abstract)) for pid in cited_ids if pid in cited])
    w(f"### Unresolved reference entries ({c['unresolved']})")
    w("| entry | parsed title | year | server's reason | candidates |",
      "|---|---|---|---|---|",
      *[f"| {u['n']} | {u.get('title') or u.get('text', '')[:120]} | {u.get('year') or ''} | {u['reason']} | "
        + "; ".join(f"{_link(k['id'])} {k['title']}" for k in u.get("candidates", [])) + " |"
        for u in res["unresolved"]])

    w(f"## Direction 2: citing the anchor ({len(citing_papers)})")
    if citing_papers:
        w("| id | title | authors | date | found by | page |",
          "|---|---|---|---|---|---|",
          *[_row(strip_version(h["id"]), citing_papers[strip_version(h["id"])],
                 f"full-text scan, matched \"{h['matched'][:60]}\"", str(h["page"]))
            for h in citing if strip_version(h["id"]) in citing_papers])
    else:
        w(forward_status + ".")

    w(f"## Direction 3: index-term sweep ({len(sweep)} unique)")
    w("| id | title | authors | date | first sentence of abstract | queries |",
      "|---|---|---|---|---|---|",
      *[_row(pid, p, _first_sentence(p.abstract), ",".join(map(str, hits[pid])))
        for pid, p in sorted(sweep.items(), key=lambda kv: (-len(hits[kv[0]]), kv[0]))])

    caveats = [
        f"- Reference resolution is the server's: style `{res['reference_style']}`, entry_count {c['entry_count']}, "
        f"identifiers {c['identifier']}, by title {c['resolved_by_title']}, unresolved {c['unresolved']}. "
        f"Check: {len(cited_ids)} resolved + {c['unresolved']} unresolved = {len(cited_ids) + c['unresolved']} "
        f"against entry_count {c['entry_count']}.",
    ]
    if cited_missing:
        caveats.append(f"- Resolved ids arXiv did not return metadata for: {', '.join(cited_missing)}.")
    caveats.append(f"- Forward direction: {forward_status}."
                   + (f" Unreadable PDFs: {', '.join(f['id'] for f in scan['failed'])}." if scan.get("failed") else ""))
    caveats.append(f"- Sweep: each query returns only its first {max_per_query} results by arXiv relevance; "
                   "queries with more total hits than returned were not paged.")
    caveats.append(f"- Terms and queries are in `{queries_file}`; edit that file and rerun to change the sweep.")
    w("## Caveats")
    w(*caveats)

    artifact = out / f"{aid}_search_space.md"
    artifact.write_text("\n".join(L), encoding="utf-8")

    # --- abstracts and union for Step 4 ----------------------------------------
    A = [f"# Abstracts for Step 4 ({aid} search space)", f"Papers: {len(union)}", ""]
    for pid in sorted(union):
        p = union[pid]["paper"]
        dirs = ",".join(f"D{d}" for d in sorted(set(union[pid]["directions"])))
        A += [f"## {pid} | {p.title}",
              f"Date: {p.published[:10]} | Direction: {dirs} | Categories: {', '.join(p.categories)}",
              "", p.abstract, ""]
    (out / "scratch" / "abstracts.md").write_text("\n".join(A), encoding="utf-8")
    (out / "scratch" / "union.json").write_text(json.dumps(
        {pid: {"title": u["paper"].title, "directions": sorted(set(u["directions"]))} for pid, u in union.items()},
        indent=1, ensure_ascii=False), encoding="utf-8")

    return {
        "anchor": aid,
        "artifact": str(artifact),
        "abstracts_file": str(out / "scratch" / "abstracts.md"),
        "union_file": str(out / "scratch" / "union.json"),
        "queries": queries_source,
        "totals": {"cited": len(cited), "citing": len(citing_papers), "sweep_unique": len(sweep), "union": len(union)},
        "reference_counts": res["counts"],
        "reference_style": res["reference_style"],
        "forward": forward_status,
        "per_query": qrows,
    }
