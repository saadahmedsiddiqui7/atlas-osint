"""Public, credential-free open-knowledge search connectors."""

import html
import json
import re
import ssl
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import certifi


USER_AGENT = "ATLAS-OSINT/0.3 (local public-source research)"


def _get_json(url: str) -> dict:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    context = ssl.create_default_context(cafile=certifi.where())
    with urlopen(request, timeout=8, context=context) as response:
        return json.loads(response.read().decode("utf-8"))


def _plain_text(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", value or "")).strip()


def search_wikipedia(query: str, limit: int = 5) -> list[dict]:
    """Search English Wikipedia pages through the official MediaWiki API."""
    params = urlencode({"q": query, "limit": min(max(limit, 1), 10)})
    payload = _get_json(f"https://en.wikipedia.org/w/rest.php/v1/search/page?{params}")
    pages = payload.get("pages", [])
    return [
        {
            "title": page.get("title") or "Untitled Wikipedia page",
            "url": page.get("key") and f"https://en.wikipedia.org/wiki/{page['key']}" or "",
            "snippet": _plain_text(page.get("excerpt", "")) or page.get("description", ""),
            "source": "Wikipedia",
            "source_type": "wikipedia",
        }
        for page in pages
        if page.get("key")
    ]


def search_wikidata(query: str, limit: int = 5) -> list[dict]:
    """Search Wikidata labels; results are candidates, not identity matches."""
    params = urlencode({
        "action": "wbsearchentities",
        "search": query,
        "language": "en",
        "format": "json",
        "limit": min(max(limit, 1), 10),
    })
    payload = _get_json(f"https://www.wikidata.org/w/api.php?{params}")
    entities = payload.get("search", [])
    return [
        {
            "title": item.get("label") or item.get("id") or "Untitled Wikidata item",
            "url": item.get("concepturi") or f"https://www.wikidata.org/wiki/{item.get('id', '')}",
            "snippet": item.get("description", ""),
            "source": "Wikidata",
            "source_type": "wikidata",
        }
        for item in entities
        if item.get("id")
    ]
