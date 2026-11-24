"""Public web search using DDGS with a stable, explicit search backend."""

import os
from concurrent.futures import ThreadPoolExecutor

import certifi
from ddgs import DDGS
from ddgs.exceptions import DDGSException


SEARCH_BACKEND = os.environ.get("ATLAS_SEARCH_BACKEND", "yahoo")
USERNAME_SEARCH_BACKENDS = ("yahoo", "bing", "brave", "google")


def search_public_sources(query: str, max_results: int = 5, backend: str | None = None):
    """Search indexed public web pages and return title, URL, and short snippet."""
    cleaned_query = (query or "").strip()
    if len(cleaned_query) < 3:
        return []
    if not 1 <= max_results <= 25:
        raise ValueError("max_results must be between 1 and 25")

    try:
        with DDGS(timeout=12, verify=certifi.where()) as ddgs:
            search_results = ddgs.text(
                cleaned_query,
                max_results=max_results,
                backend=backend or SEARCH_BACKEND,
            )
    except DDGSException as exc:
        # DDGS reports an empty provider response as an exception too.
        if "no results found" in str(exc).lower():
            return []
        raise

    return [
        {
            "title": item.get("title"),
            "url": item.get("href"),
            "snippet": item.get("body"),
            "verification_status": "unverified",
        }
        for item in search_results
    ]


def search_username_sources(query: str, max_results: int = 5, search_fn=None):
    """Search several public web indexes and report their coverage separately."""
    search_fn = search_fn or search_public_sources
    outcomes = {}
    with ThreadPoolExecutor(max_workers=len(USERNAME_SEARCH_BACKENDS)) as executor:
        pending = {
            backend: executor.submit(search_fn, query, max_results, backend=backend)
            for backend in USERNAME_SEARCH_BACKENDS
        }
        for backend in USERNAME_SEARCH_BACKENDS:
            try:
                outcomes[backend] = {"results": pending[backend].result(), "error": None}
            except Exception:
                outcomes[backend] = {"results": [], "error": "Search provider temporarily unavailable."}

    combined = []
    seen_urls = set()
    coverage = []
    for backend in USERNAME_SEARCH_BACKENDS:
        outcome = outcomes[backend]
        provider_results = outcome["results"]
        coverage.append({
            "provider": backend.title(),
            "status": "unavailable" if outcome["error"] else ("results" if provider_results else "no_results"),
            "result_count": len(provider_results),
            "note": outcome["error"] or (
                "No matching indexed pages returned." if not provider_results else
                "Results are limited to pages this search provider indexed."
            ),
        })
        for result in provider_results:
            result.setdefault("source", f"{backend.title()} web search")
            result.setdefault("source_type", f"{backend}_web_search")
            url = (result.get("url") or "").split("#", 1)[0].rstrip("/").casefold()
            if url and url not in seen_urls:
                seen_urls.add(url)
                combined.append(result)
    return combined, coverage
