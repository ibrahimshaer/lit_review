# arXiv MCP server

An MCP server that exposes arXiv to Claude Code for a five-step literature review: anchor paper, user's notes, three-direction search space (references, citations, index terms), tiers, and diffs.

## Install

Python 3.10+ with mcp, httpx, and pypdf:

```
pip install "mcp>=1.26" httpx pypdf
```

Register with Claude Code. Copy `.mcp.json.example` to `.mcp.json` in the project root and replace the placeholder paths:

```json
{
  "mcpServers": {
    "arxiv": {
      "command": "/path/to/python",
      "args": ["/path/to/arxiv_mcp/server.py"],
      "env": {
        "ARXIV_MCP_CACHE": "/path/to/arxiv_cache"
      }
    }
  }
}
```

Or from the terminal:

```
claude mcp add arxiv -- /path/to/python /path/to/arxiv_mcp/server.py
```

Environment variables: `ARXIV_MCP_CACHE` (default `./arxiv_cache`), `ARXIV_MCP_DELAY` (default 3.0 seconds), `ARXIV_MCP_RETRIES` (default 12, each wait capped at 300 seconds).

Skill: copy `literature_review_skill.md` to `.claude/skills/literature-review/SKILL.md`.

## Which tool serves which step

| Step | Tool |
|---|---|
| Step 1, anchors | `search_papers` (only for the "last N surveys" option; naming papers needs no tool) |
| Step 2, user reads | no tool; `get_paper_text` if the user wants the text |
| Step 3, search space | `build_search_space` does all three directions in one call. Under the hood: `resolve_references` (cited by the anchor), `find_citations_in_text` (citing the anchor, skipped if anchor is under 90 days old), `get_index_terms` (index-term sweep, terms saved to `queries.json`) |
| Step 4, tiers | no tool; read `scratch/abstracts.md` written by Step 3 |
| Step 5, diffs | `get_paper_text`, writes page-marked text with reference list removed to a file |
| Manual reruns and inspection | `extract_references`, `get_papers`, `get_paper`, `download_pdf`, `list_categories` |

## File layout

| File | Holds |
|---|---|
| `server.py` | Entry point; registers tools and starts stdio server |
| `config.py` | Environment configuration |
| `arxiv_api.py` | Throttled client, identifier handling, Paper record, Atom parsing |
| `pdf_text.py` | PDF download, page text, locating and removing reference list |
| `references.py` | Bibliography splitting, style detection, entry parsing, title normalisation |
| `index_terms.py` | Keywords line or title terms, stopwords |
| `tools_papers.py` | `search_papers`, `get_paper`, `get_papers`, `download_pdf`, `get_paper_text`, `list_categories` |
| `tools_references.py` | `extract_references`, `resolve_references`, `find_citations_in_text`, `get_index_terms` |
| `search_space.py` | `build_search_space`; all of Step 3 in one call |

## Tests

```
python handshake_test.py
```

No network; lists the tools.

```
python smoke_test.py
```

Hits arXiv; exercises search, metadata, text and reference extraction.

All arXiv requests are throttled and retried; failures surface as tool errors, never as silent gaps.
