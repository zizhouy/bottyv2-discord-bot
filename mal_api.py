# MyAnimeList API access

import os
import aiohttp

MAL_CLIENT_ID = os.getenv("MAL_CLIENT_ID")

http_session: aiohttp.ClientSession | None = None



def get_anime_list(query):
    if http_session is None or http_session.closed:
        raise RuntimeError("HTTP session is not initialized")

    if not MAL_CLIENT_ID:
        raise RuntimeError("MAL_CLIENT_ID is not set")
    
    url = "https://api.myanimelist.net/v2/anime"
    headers = {
        "X-MAL-CLIENT-ID": MAL_CLIENT_ID,
        "q": query
    }

    


