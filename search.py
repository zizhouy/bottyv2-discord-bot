import aiohttp
import asyncio
import os

import trafilatura

from http_client import get_http_session

BRAVE_SEARCH_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY")


async def web_search_brave(query: str, items: int = 3, description_length: int = 200):
    http_session = await get_http_session()

    if not BRAVE_SEARCH_API_KEY:
        raise RuntimeError("BRAVE_SEARCH_API_KEY is not set")

    url = "https://api.search.brave.com/res/v1/web/search"
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": BRAVE_SEARCH_API_KEY,
    }
    params = {
        "q": query,
        "count": 5,
    }

    async with http_session.get(url, headers=headers, params=params) as resp:
        resp.raise_for_status()
        data = await resp.json()

    results = []
    for item in data.get("web", {}).get("results", [])[:items]:
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "description": item.get("description", "")[:description_length],
        })

    top_source = None
    if results:
        excerpt = await fetch_top_source_excerpt(results[0]["url"], max_chars=3000)
        top_source = {
            "title": results[0]["title"],
            "url": results[0]["url"],
            "excerpt": excerpt,
        }

    data = {
        "original_query": query,
        "results": results,
        "top_source": top_source,
    }

    print("=== Search results ===")
    for i, result in enumerate(data["results"], start=1):
        print(f"[{i}] {result['title']}")
        print(f"URL: {result['url']}")
        print(f"Description: {result['description']}")
        print()

    print("=== Top source ===")
    top = data["top_source"]
    if top:
        print(f"Title: {top['title']}")
        print(f"URL: {top['url']}")
        print(f"Excerpt: {top['excerpt'][:500]}")
    else:
        print("No top source available.")

    return {
        "original_query": query,
        "results": results,
        "top_source": top_source,
    }


async def fetch_top_source_excerpt(url: str, max_chars: int = 1500) -> str:
    http_session = await get_http_session()

    try:
        async with http_session.get(url) as resp:
            resp.raise_for_status()
            html = await resp.text()
    except Exception:
        return ""

    extracted = trafilatura.extract(
        html,
        output_format="txt",
        include_comments=False,
        favor_precision=True,
    )

    if not extracted:
        return ""

    return extracted[:max_chars]



async def main():
    data = await web_search_brave(
        "Kunon light novel volume 6",
        items=3,
        description_length=200,
    )

    print("=== Search results ===")
    for i, result in enumerate(data["results"], start=1):
        print(f"[{i}] {result['title']}")
        print(f"URL: {result['url']}")
        print(f"Description: {result['description']}")
        print()

    print("=== Top source ===")
    top = data["top_source"]
    if top:
        print(f"Title: {top['title']}")
        print(f"URL: {top['url']}")
        print(f"Excerpt: {top['excerpt'][:500]}")
    else:
        print("No top source available.")

if __name__ == "__main__":
    asyncio.run(main())