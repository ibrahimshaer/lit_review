"""arXiv MCP server: entry point.

Exposes the arXiv API and PDF text extraction as MCP tools, over stdio,
for the anchor-and-difference literature review. The code lives in the
sibling modules; this file only registers the tools and starts the server.

    config.py            environment configuration
    arxiv_api.py         throttled client, identifiers, Paper, Atom parsing
    pdf_text.py          PDF download, page text, reference-list location
    references.py        bibliography splitting, style detection, entry parsing
    index_terms.py       keywords line or title terms, stopwords
    tools_papers.py      search_papers, get_paper, get_papers, download_pdf,
                         get_paper_text, list_categories
    tools_references.py  extract_references, resolve_references,
                         find_citations_in_text, get_index_terms
    search_space.py      build_search_space (all of Step 3 in one call)

Run:
    python server.py

Register in Claude Code (.mcp.json in the project root):
    {
      "mcpServers": {
        "arxiv": {
          "command": "python",
          "args": ["/path/to/arxiv_mcp/server.py"]
        }
      }
    }

Environment: see config.py.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from search_space import build_search_space  # noqa: E402
from tools_papers import (  # noqa: E402
    download_pdf,
    get_paper,
    get_paper_text,
    get_papers,
    list_categories,
    search_papers,
)
from tools_references import (  # noqa: E402
    extract_references,
    find_citations_in_text,
    get_index_terms,
    resolve_references,
)

mcp = FastMCP(
    "arxiv",
    instructions=(
        "Tools for searching arXiv, fetching paper metadata and abstracts, "
        "downloading PDFs, extracting page-marked text, and parsing reference "
        "lists. Identifiers may be given as '2605.14271', '2605.14271v2', "
        "'arXiv:2605.14271', or a full arxiv.org URL. Requests to arXiv are "
        "throttled to one every few seconds; batch identifiers with "
        "get_papers instead of calling get_paper in a loop."
    ),
)

TOOLS = (
    search_papers,
    get_paper,
    get_papers,
    download_pdf,
    get_paper_text,
    extract_references,
    resolve_references,
    find_citations_in_text,
    get_index_terms,
    build_search_space,
    list_categories,
)
for _tool in TOOLS:
    mcp.tool()(_tool)

if __name__ == "__main__":
    mcp.run(transport="stdio")
