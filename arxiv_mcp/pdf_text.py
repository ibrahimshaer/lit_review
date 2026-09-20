"""PDF download, page extraction, and locating or removing the reference list."""

from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader

from arxiv_api import get
from config import CACHE_DIR, PDF_URL

REF_HEADING = re.compile(r"^\s*(References|Bibliography|REFERENCES|BIBLIOGRAPHY)\s*$", re.MULTILINE)
_LONE_SURROGATE = re.compile(r"[\ud800-\udfff]")
_APPENDIX_HEADING = re.compile(
    r"^\s*(?:Appendix|APPENDIX|Appendices|Supplementary Material|[A-Z]\s+[A-Z][A-Za-z ]{3,60})\s*$",
    re.MULTILINE,
)
_PAGE_MARKER = re.compile(r"=== page \d+ ===")


async def pdf_path(arxiv_id: str) -> Path:
    """Return the cached PDF path for an id, downloading it if needed."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{arxiv_id.replace('/', '_')}.pdf"
    if path.exists() and path.stat().st_size > 0:
        return path
    resp = await get(PDF_URL.format(id=arxiv_id))
    ctype = resp.headers.get("content-type", "")
    if "pdf" not in ctype and not resp.content.startswith(b"%PDF"):
        raise RuntimeError(f"arXiv returned {ctype or 'unknown content'} instead of a PDF for {arxiv_id}")
    path.write_bytes(resp.content)
    return path


def extract_pages(path: Path) -> list[str]:
    """Page texts. Lone surrogate code points, which some PDF fonts produce and
    which cannot be encoded to UTF-8, are replaced so a bad glyph never makes a
    whole page unreadable."""
    reader = PdfReader(str(path))
    return [_LONE_SURROGATE.sub("�", page.extract_text() or "") for page in reader.pages]


def page_marked(pages: list[str]) -> str:
    """Join pages with '=== page N ===' markers so every claim can cite a page."""
    return "\n\n".join(f"=== page {i} ===\n{t}" for i, t in enumerate(pages, start=1))


def find_reference_section(full_text: str) -> str:
    """Return text from the last 'References' heading onward, or all text."""
    matches = list(REF_HEADING.finditer(full_text))
    if not matches:
        return full_text
    return full_text[matches[-1].start():]


def strip_reference_list(marked: str) -> tuple[str, int]:
    """Remove the reference list from page-marked text: from the last References
    heading up to an appendix heading if one follows, otherwise to the end. The
    page markers inside the removed span are kept so pages stay addressable.
    Returns the new text and the number of characters removed."""
    heads = list(REF_HEADING.finditer(marked))
    if not heads:
        return marked, 0
    ref_start = heads[-1].start()
    appendix = _APPENDIX_HEADING.search(marked[ref_start:])
    ref_end = ref_start + appendix.start() if appendix else len(marked)
    kept_markers = "\n\n".join(_PAGE_MARKER.findall(marked[ref_start:ref_end]))
    stripped = marked[:ref_start] + "[references removed]\n\n" + kept_markers + "\n\n" + marked[ref_end:]
    return stripped, ref_end - ref_start
