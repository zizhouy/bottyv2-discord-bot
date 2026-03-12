# MyAnimeList API access

import os
import asyncio
import json
import aiohttp

from http_client import get_http_session, close_http_session

MAL_CLIENT_ID = os.getenv("MAL_CLIENT_ID")
MAL_API_URL = "https://api.myanimelist.net/v2/anime"
MAL_MANGA_API_URL = "https://api.myanimelist.net/v2/manga"

MAL_ANIME_FIELDS = (
    "alternative_titles,"
    "start_date,"
    "end_date,"
    "mean,"
    "rank,"
    "popularity,"
    "genres,"
    "media_type,"
    "status,"
    "num_episodes,"
    "start_season,"
    "source,"
    "rating,"
    "studios"
)

MAL_MANGA_FIELDS = (
    "alternative_titles,"
    "start_date,"
    "end_date,"
    "mean,"
    "rank,"
    "popularity,"
    "genres,"
    "media_type,"
    "status,"
    "num_volumes,"
    "num_chapters,"
    "authors{first_name,last_name}"
)

async def _fetch_anime_list(params: dict, url_ext: str = ""):
    if not MAL_CLIENT_ID:
        raise RuntimeError("MAL_CLIENT_ID is not set")

    http_session = await get_http_session()

    headers = {
        "X-MAL-CLIENT-ID": MAL_CLIENT_ID
    }

    params["fields"] = MAL_ANIME_FIELDS

    async with http_session.get(MAL_API_URL+url_ext, headers=headers, params=params) as resp:
        if resp.status != 200:
            error_text = await resp.text()
            raise RuntimeError(f"MAL API error {resp.status}: {error_text}")

        data = await resp.json()

    results = []

    for item in data.get("data", []):
        node = item.get("node", {})
        picture = node.get("main_picture", {})

        alt_titles = node.get("alternative_titles", {})
        title_candidates = []

        if alt_titles.get("en"):
            title_candidates.append(alt_titles["en"])

        if alt_titles.get("ja"):
            title_candidates.append(alt_titles["ja"])

        title_candidates.extend(alt_titles.get("synonyms", []))

        results.append({
            "id": node.get("id"),
            "title": node.get("title"),
            "titles": title_candidates,

            "media_type": node.get("media_type"),
            "status": node.get("status"),
            "episodes": node.get("num_episodes"),

            "start_date": node.get("start_date"),
            "end_date": node.get("end_date"),

            "release_season": {
                "season": node.get("start_season", {}).get("season"),
                "year": node.get("start_season", {}).get("year")
            },

            "score": node.get("mean"),
            "score_rank": node.get("rank"),
            "popularity_rank": node.get("popularity"),

            "genres": [g.get("name") for g in node.get("genres", [])],
            "source_material": node.get("source"),
            "age_rating": node.get("rating"),

            "studios": [s.get("name") for s in node.get("studios", [])],

            "images": {
                "medium": picture.get("medium"),
                "large": picture.get("large")
            }
        })

    return results


async def _fetch_manga_list(params: dict, url_ext: str = ""):
    if not MAL_CLIENT_ID:
        raise RuntimeError("MAL_CLIENT_ID is not set")

    http_session = await get_http_session()

    headers = {
        "X-MAL-CLIENT-ID": MAL_CLIENT_ID
    }

    params["fields"] = MAL_MANGA_FIELDS

    async with http_session.get(MAL_MANGA_API_URL+url_ext, headers=headers, params=params) as resp:
        if resp.status != 200:
            error_text = await resp.text()
            raise RuntimeError(f"MAL API error {resp.status}: {error_text}")

        data = await resp.json()

    results = []

    for item in data.get("data", []):
        node = item.get("node", {})
        picture = node.get("main_picture", {})

        alt_titles = node.get("alternative_titles", {})
        title_candidates = []

        if alt_titles.get("en"):
            title_candidates.append(alt_titles["en"])

        if alt_titles.get("ja"):
            title_candidates.append(alt_titles["ja"])

        title_candidates.extend(alt_titles.get("synonyms", []))

        results.append({
            "id": node.get("id"),
            "title": node.get("title"),
            "titles": title_candidates,

            "media_type": node.get("media_type"),
            "status": node.get("status"),
            "volumes": node.get("num_volumes"),
            "chapters": node.get("num_chapters"),

            "start_date": node.get("start_date"),
            "end_date": node.get("end_date"),

            "score": node.get("mean"),
            "score_rank": node.get("rank"),
            "popularity_rank": node.get("popularity"),

            "genres": [g.get("name") for g in node.get("genres", [])],
            "authors": [
                " ".join(
                    part for part in [
                        a.get("node", {}).get("first_name"),
                        a.get("node", {}).get("last_name"),
                    ] if part
                )
                for a in node.get("authors", [])
            ],

            "images": {
                "medium": picture.get("medium"),
                "large": picture.get("large")
            }
        })

    return results


# Search by title
async def get_anime_list(query: str, offset: int = 0, limit: int = 5):
    return await _fetch_anime_list({
        "q": query,
        "offset": offset,
        "limit": limit
        })


async def get_anime_ranking(rank_type: str, offset: int = 0, limit: int = 5):
    return await _fetch_anime_list({
        "ranking_type": rank_type,
        "offset": offset,
        "limit": limit
        },
        url_ext="/ranking")


async def get_seasonal_anime(year: int, season: str, offset: int = 0, limit: int = 5):
    return await _fetch_anime_list({
        "offset": offset,
        "limit": limit
        },
        url_ext=f"/season/{year}/{season}")


async def get_manga_list(query: str, offset: int = 0, limit: int = 5):
    return await _fetch_manga_list({
        "q": query,
        "offset": offset,
        "limit": limit
        })


async def get_manga_ranking(rank_type: str, offset: int = 0, limit: int = 5):
    return await _fetch_manga_list({
        "ranking_type": rank_type,
        "offset": offset,
        "limit": limit
        },
        url_ext="/ranking")


async def get_anime_details(anime_id: int):
    if not MAL_CLIENT_ID:
        raise RuntimeError("MAL_CLIEND_ID is not set")

    http_session = await get_http_session()

    url = f"{MAL_API_URL}/{anime_id}"
    headers = {
        "X-MAL-CLIENT-ID": MAL_CLIENT_ID
    }
    params = {
        "fields": (
            "alternative_titles,"
            "start_date,"
            "end_date,"
            "synopsis,"
            "mean,"
            "rank,"
            "popularity,"
            "genres,"
            "media_type,"
            "status,"
            "num_episodes,"
            "start_season,"
            "source,"
            "average_episode_duration,"
            "rating,"
            "studios,"
            "background,"
            "related_anime,"
            "related_manga,"
            "recommendations,"
            "statistics"
        )
    }

    async with http_session.get(url, headers=headers, params=params) as resp:
        if resp.status != 200:
            error_text = await resp.text()
            raise RuntimeError(f"MAL API error {resp.status}: {error_text}")

        data = await resp.json()

    alt_titles = data.get("alternative_titles", {})
    picture = data.get("main_picture", {})

    title_candidates = []
    seen = set()

    for t in [
        data.get("title"),
        alt_titles.get("en"),
        alt_titles.get("ja"),
        *alt_titles.get("synonyms", [])
    ]:
        if t and t not in seen:
            title_candidates.append(t)
            seen.add(t)

    result = {
        "id": data.get("id"),
        "title": data.get("title"),

        "titles": {
            "english": alt_titles.get("en"),
            "japanese": alt_titles.get("ja"),
            "synonyms": alt_titles.get("synonyms", [])
        },

        "title_candidates": title_candidates,

        "images": {
            "medium": picture.get("medium"),
            "large": picture.get("large")
        },

        "synopsis": data.get("synopsis"),
        "background": data.get("background"),

        "media_type": data.get("media_type"),
        "status": data.get("status"),
        "episodes": data.get("num_episodes"),

        "release": {
            "start_date": data.get("start_date"),
            "end_date": data.get("end_date"),
            "season": data.get("start_season", {}).get("season"),
            "year": data.get("start_season", {}).get("year")
        },

        "score": data.get("mean"),
        "score_rank": data.get("rank"),
        "popularity_rank": data.get("popularity"),

        "genres": [g["name"] for g in data.get("genres", [])],
        "source_material": data.get("source"),

        "studios": [s["name"] for s in data.get("studios", [])],

        "related_anime": [
            {
                "id": r["node"]["id"],
                "title": r["node"]["title"],
                "relation": r["relation_type"],
                "relation_label": r["relation_type_formatted"]
            }
            for r in data.get("related_anime", [])
        ],

        "recommendations": [
            {
                "id": r["node"]["id"],
                "title": r["node"]["title"],
                "recommendations": r["num_recommendations"]
            }
            for r in data.get("recommendations", [])[:5]
        ],

        "statistics": {
            "total_users": data.get("statistics", {}).get("num_list_users"),
            "watching": data.get("statistics", {}).get("status", {}).get("watching"),
            "completed": data.get("statistics", {}).get("status", {}).get("completed"),
            "on_hold": data.get("statistics", {}).get("status", {}).get("on_hold"),
            "dropped": data.get("statistics", {}).get("status", {}).get("dropped"),
            "plan_to_watch": data.get("statistics", {}).get("status", {}).get("plan_to_watch"),
        }
    }

    return result


async def get_manga_details(manga_id: int):
    if not MAL_CLIENT_ID:
        raise RuntimeError("MAL_CLIENT_ID is not set")

    http_session = await get_http_session()

    url = f"{MAL_MANGA_API_URL}/{manga_id}"
    headers = {
        "X-MAL-CLIENT-ID": MAL_CLIENT_ID
    }
    params = {
        "fields": (
            "alternative_titles,"
            "start_date,"
            "end_date,"
            "synopsis,"
            "mean,"
            "rank,"
            "popularity,"
            "genres,"
            "media_type,"
            "status,"
            "num_volumes,"
            "num_chapters,"
            "authors{first_name,last_name},"
            "background,"
            "related_anime,"
            "related_manga,"
            "recommendations,"
            "statistics"
        )
    }

    async with http_session.get(url, headers=headers, params=params) as resp:
        if resp.status != 200:
            error_text = await resp.text()
            raise RuntimeError(f"MAL API error {resp.status}: {error_text}")

        data = await resp.json()

    alt_titles = data.get("alternative_titles", {})
    picture = data.get("main_picture", {})

    title_candidates = []
    seen = set()

    for t in [
        data.get("title"),
        alt_titles.get("en"),
        alt_titles.get("ja"),
        *alt_titles.get("synonyms", [])
    ]:
        if t and t not in seen:
            title_candidates.append(t)
            seen.add(t)

    result = {
        "id": data.get("id"),
        "title": data.get("title"),

        "titles": {
            "english": alt_titles.get("en"),
            "japanese": alt_titles.get("ja"),
            "synonyms": alt_titles.get("synonyms", [])
        },

        "title_candidates": title_candidates,

        "images": {
            "medium": picture.get("medium"),
            "large": picture.get("large")
        },

        "synopsis": data.get("synopsis"),
        "background": data.get("background"),

        "media_type": data.get("media_type"),
        "status": data.get("status"),
        "volumes": data.get("num_volumes"),
        "chapters": data.get("num_chapters"),

        "release": {
            "start_date": data.get("start_date"),
            "end_date": data.get("end_date")
        },

        "score": data.get("mean"),
        "score_rank": data.get("rank"),
        "popularity_rank": data.get("popularity"),

        "genres": [g["name"] for g in data.get("genres", [])],

        "authors": [
            " ".join(
                part for part in [
                    a.get("node", {}).get("first_name"),
                    a.get("node", {}).get("last_name"),
                ] if part
            )
            for a in data.get("authors", [])
        ],

        "related_manga": [
            {
                "id": r["node"]["id"],
                "title": r["node"]["title"],
                "relation": r["relation_type"],
                "relation_label": r["relation_type_formatted"]
            }
            for r in data.get("related_manga", [])
        ],

        "related_anime": [
            {
                "id": r["node"]["id"],
                "title": r["node"]["title"],
                "relation": r["relation_type"],
                "relation_label": r["relation_type_formatted"]
            }
            for r in data.get("related_anime", [])
        ],

        "recommendations": [
            {
                "id": r["node"]["id"],
                "title": r["node"]["title"],
                "recommendations": r["num_recommendations"]
            }
            for r in data.get("recommendations", [])[:5]
        ],

        "statistics": {
            "total_users": data.get("statistics", {}).get("num_list_users"),
            "reading": data.get("statistics", {}).get("status", {}).get("reading"),
            "completed": data.get("statistics", {}).get("status", {}).get("completed"),
            "on_hold": data.get("statistics", {}).get("status", {}).get("on_hold"),
            "dropped": data.get("statistics", {}).get("status", {}).get("dropped"),
            "plan_to_read": data.get("statistics", {}).get("status", {}).get("plan_to_read"),
        }
    }

    return result


async def test_endpoint(name: str, coro) -> None:
    print(f"\n=== {name} ===")
    try:
        data = await coro
        print(json.dumps(data, indent=2, ensure_ascii=False)[:2000])
        print("✓ OK")
    except Exception as e:
        print(f"✗ FAILED: {e}")


async def main():
    try:
        await test_endpoint(
            "get_anime_list",
            get_anime_list("frieren", limit=2)
        )

        await test_endpoint(
            "get_anime_details",
            get_anime_details(52991)  # Sousou no Frieren
        )

        await test_endpoint(
            "get_anime_ranking",
            get_anime_ranking("all", limit=2)
        )

        await test_endpoint(
            "get_seasonal_anime",
            get_seasonal_anime(2023, "fall", limit=2)
        )

        await test_endpoint(
            "get_manga_list",
            get_manga_list("berserk", limit=2)
        )

        await test_endpoint(
            "get_manga_details",
            get_manga_details(2)  # Berserk
        )

        await test_endpoint(
            "get_manga_ranking",
            get_manga_ranking("all", limit=2)
        )

    finally:
        await close_http_session()


if __name__ == "__main__":
    asyncio.run(main())