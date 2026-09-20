"""Configuration for the arXiv MCP server, all from the environment.

ARXIV_MCP_CACHE    directory for downloaded PDFs, search results and text
                   (default: ./arxiv_cache)
ARXIV_MCP_DELAY    minimum seconds between arXiv requests (default: 3.0,
                   which is what arXiv asks for)
ARXIV_MCP_RETRIES  retries on 429 or 5xx before giving up (default: 12)
"""

from __future__ import annotations

import os
from pathlib import Path

API_URL = "https://export.arxiv.org/api/query"
PDF_URL = "https://arxiv.org/pdf/{id}"
ABS_URL = "https://arxiv.org/abs/{id}"

CACHE_DIR = Path(os.environ.get("ARXIV_MCP_CACHE", "arxiv_cache")).resolve()
MIN_DELAY = float(os.environ.get("ARXIV_MCP_DELAY", "3.0"))
MAX_RETRIES = int(os.environ.get("ARXIV_MCP_RETRIES", "12"))
USER_AGENT = "arxiv-mcp/0.1 (literature review tooling)"
MAX_PAGE_SIZE = 200  # arXiv API hard limit is 2000, but large pages time out
