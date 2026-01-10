import os
import aiohttp
import asyncio
import logging

# Uptime Kuma Push check
PUSH_URL = os.getenv("PUSH_URL")

async def heartbeat_task():
    if not PUSH_URL:
        logging.info("PUSH_URL not set, skipping heartbeat task")
        return
    
    timeout = aiohttp.ClientTimeout(total=10)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        while True:
            try:
                async with session.get(PUSH_URL, params={"status": "up"}) as resp:
                    if resp.status != 200:
                        logging.warning("Kuma hearbeat failed: %s", resp.status)
            except Exception as e:
                logging.warning("Kuma heartbeat exception: %s", e)
            await asyncio.sleep(55) # Send heartbeat every 55 seconds