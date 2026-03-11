# To manage http session

import aiohttp

_http_session: aiohttp.ClientSession | None = None


async def get_http_session() -> aiohttp.ClientSession:
    global _http_session

    if _http_session is None or _http_session.closed:
        _http_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10),
            headers={
                "User-Agent": "bottyv2/1.0",
            },
        )

    return _http_session


async def close_http_session() -> None:
    global _http_session

    if _http_session is not None and not _http_session.closed:
        await _http_session.close()

    _http_session = None