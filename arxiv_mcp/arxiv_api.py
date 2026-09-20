"""Throttled arXiv API client: identifiers, the Paper record, Atom parsing."""

from __future__ import annotations

import asyncio
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

import httpx

from config import ABS_URL, API_URL, MAX_RETRIES, MIN_DELAY, PDF_URL, USER_AGENT

# ---------------------------------------------------------------------------
# Throttled HTTP client
# ---------------------------------------------------------------------------


class Throttle:
    """Serialises arXiv requests and enforces a minimum gap between them."""

    def __init__(self, delay: float) -> None:
        self._delay = delay
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def wait(self) -> None:
        async with self._lock:
            gap = self._delay - (time.monotonic() - self._last)
            if gap > 0:
                await asyncio.sleep(gap)
            self._last = time.monotonic()


_throttle = Throttle(MIN_DELAY)
_client: httpx.AsyncClient | None = None
_RETRY_STATUSES = {429, 500, 502, 503, 504}


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            timeout=httpx.Timeout(60.0, connect=15.0),
            follow_redirects=True,
        )
    return _client


async def get(url: str, params: dict[str, Any] | None = None) -> httpx.Response:
    """GET with throttling and backoff. arXiv answers 429 or 503 when busy;
    the Retry-After header is honoured when present, else the wait doubles
    from 5 seconds."""
    delay = 5.0
    for attempt in range(MAX_RETRIES + 1):
        await _throttle.wait()
        try:
            resp = await _http().get(url, params=params)
        except httpx.TransportError:
            if attempt == MAX_RETRIES:
                raise
            await asyncio.sleep(delay)
            delay *= 2
            continue
        if resp.status_code in _RETRY_STATUSES and attempt < MAX_RETRIES:
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if retry_after and retry_after.isdigit() else delay
            await asyncio.sleep(min(wait, 300.0))
            delay *= 2
            continue
        resp.raise_for_status()
        return resp
    raise RuntimeError("unreachable")


# ---------------------------------------------------------------------------
# Identifier handling
# ---------------------------------------------------------------------------

# New-style ids: YYMM.NNNNN with optional version. Old-style: archive/YYMMNNN.
_ID_NEW = r"\d{4}\.\d{4,5}(?:v\d+)?"
_ID_OLD = r"[a-z\-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?"
_ID_ANY = rf"(?:{_ID_NEW}|{_ID_OLD})"

ID_STRICT = re.compile(rf"^{_ID_ANY}$")
ID_IN_TEXT = re.compile(rf"(?:arxiv\.org/(?:abs|pdf)/|arXiv:\s*){_ID_ANY}", re.IGNORECASE)

# The tolerant pattern. PDF extraction breaks identifiers across lines in two
# places: between 'abs/' and the number, and inside the number itself.
# Whitespace is allowed at both, which is what catches the dropped references.
ID_TOLERANT = re.compile(
    r"(?:arxiv\.org/(?:abs|pdf)/|arXiv:)\s*"
    r"(\d{4}\s*\.\s*\d{4,5}(?:\s*v\d+)?|[a-z\-]+(?:\.[A-Z]{2})?/\s*\d{7}(?:v\d+)?)",
    re.IGNORECASE,
)
DOI = re.compile(r"\b10\.\d{4,9}/[^\s\"<>]+", re.IGNORECASE)


def normalise_id(raw: str) -> str:
    """Accept '2605.14271', 'arXiv:2605.14271v1', or an arxiv.org URL."""
    s = raw.strip()
    s = re.sub(r"^arxiv:\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^https?://(?:www\.)?arxiv\.org/(?:abs|pdf)/", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\.pdf$", "", s)
    s = s.rstrip("/")
    if not ID_STRICT.match(s):
        raise ValueError(f"Not an arXiv identifier: {raw!r}")
    return s


def strip_version(arxiv_id: str) -> str:
    return re.sub(r"v\d+$", "", arxiv_id)


# ---------------------------------------------------------------------------
# Atom parsing
# ---------------------------------------------------------------------------

ATOM = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


@dataclass
class Paper:
    id: str
    title: str
    authors: list[str]
    abstract: str
    published: str
    updated: str
    primary_category: str
    categories: list[str]
    doi: str | None
    journal_ref: str | None
    comment: str | None
    abs_url: str
    pdf_url: str


def _text(el: ET.Element | None) -> str:
    if el is None or el.text is None:
        return ""
    return " ".join(el.text.split())


def _parse_entry(entry: ET.Element) -> Paper:
    raw_id = _text(entry.find("atom:id", ATOM))
    arxiv_id = normalise_id(raw_id)
    primary = entry.find("arxiv:primary_category", ATOM)
    return Paper(
        id=arxiv_id,
        title=_text(entry.find("atom:title", ATOM)),
        authors=[_text(a.find("atom:name", ATOM)) for a in entry.findall("atom:author", ATOM)],
        abstract=_text(entry.find("atom:summary", ATOM)),
        published=_text(entry.find("atom:published", ATOM)),
        updated=_text(entry.find("atom:updated", ATOM)),
        primary_category=primary.get("term", "") if primary is not None else "",
        categories=[c.get("term", "") for c in entry.findall("atom:category", ATOM)],
        doi=_text(entry.find("arxiv:doi", ATOM)) or None,
        journal_ref=_text(entry.find("arxiv:journal_ref", ATOM)) or None,
        comment=_text(entry.find("arxiv:comment", ATOM)) or None,
        abs_url=ABS_URL.format(id=arxiv_id),
        pdf_url=PDF_URL.format(id=arxiv_id),
    )


def _parse_feed(xml_text: str) -> tuple[list[Paper], int]:
    root = ET.fromstring(xml_text)
    total_el = root.find("{http://a9.com/-/spec/opensearch/1.1/}totalResults")
    total = int(total_el.text) if total_el is not None and total_el.text else 0
    papers = []
    for entry in root.findall("atom:entry", ATOM):
        # The API reports errors as a single entry whose id ends in '/api/errors'.
        entry_id = _text(entry.find("atom:id", ATOM))
        if "api/errors" in entry_id:
            raise RuntimeError("arXiv API error: " + _text(entry.find("atom:summary", ATOM)))
        papers.append(_parse_entry(entry))
    return papers, total


async def query(params: dict[str, Any]) -> tuple[list[Paper], int]:
    """One arXiv API request. Returns the papers and arXiv's total hit count."""
    resp = await get(API_URL, params=params)
    return _parse_feed(resp.text)
