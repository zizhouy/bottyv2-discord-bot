import os
import aiohttp
import asyncio
import json
import time

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
MODEL = os.getenv("MODEL", "llama3.1:8b")

SYSTEM_MESSAGE = {
    "role": "system",
    "content": "You are a helpful assistant for Discord users. You're name is BottyV2. Users will send you questions with \"Username: prompt\""
}

async def fetch_msg(prompt: str, user: str = "user") -> str:
    payload = {
        "model": MODEL,
        "messages": [
            SYSTEM_MESSAGE,
            {"role": "user", 
            "content": f"{user}: {prompt}"},
        ],
        "stream": False,
    }
    
    async with aiohttp.ClientSession() as session:
        timeout = aiohttp.ClientTimeout(total=60)
        async with session.post(OLLAMA_URL, json=payload, timeout=timeout) as resp:
            text = await resp.text()
            print("HTTP", resp.status)
            print("RAW BODY:", text)
            
            resp.raise_for_status()
            data = await resp.json()
            # print("PARSED:", data)
            
            return data["message"]["content"]

async def stream_msg(messages: list[dict], emit_interval: float = 1.0):
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": True
    }

    buffer: list[str] = []
    last_emit = time.monotonic()

    async with aiohttp.ClientSession() as session:
        timeout = aiohttp.ClientTimeout(total=None)
        async with session.post(OLLAMA_URL, json=payload, timeout=timeout) as resp:
            resp.raise_for_status()

            async for raw_line in resp.content:
                if not raw_line:
                    continue

                line = raw_line.decode("utf-8").strip()
                if not line:
                    continue

                # split json checker

                for part in line.splitlines():
                    data = json.loads(part)
                    
                    chunk = data.get("message", {}).get("content", "")
                    done = data.get("done", False)

                    if chunk:
                        buffer.append(chunk)
                    
                    now = time.monotonic()
                    if buffer and (now - last_emit >= emit_interval):
                        yield "".join(buffer)
                        buffer.clear()
                        last_emit = now

                    if done:
                        break
    if buffer:
        yield "".join(buffer)


async def main():
    test = await fetch_msg("What's my name?", "Bobby")
    print(test)

if __name__ == "__main__":
    asyncio.run(main())