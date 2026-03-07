import os
import aiohttp
import asyncio
import json
import time

from typing import cast, Any

from openai import AsyncOpenAI

# URL for local LLM API running through Ollama
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
MODEL = os.getenv("MODEL", "llama3.1:8b")

SYSTEM_MESSAGE = {
    "role": "system",
    "content": (
        "You are a helpful assistant for Discord users. "
        "You're name is BottyV2. "
        "Users will send you questions with \"Username: prompt\"")
}

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = AsyncOpenAI()


# Ollama
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

# Ollama
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

                # Split json checker
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

# OpenAI
# TODO: Add support for sending status updates based on response types (thinking, searching, etc.)
async def stream_msg_openai(messages: list[dict], emit_interval: float = 1.0):

    stream = await client.responses.create(
        model="gpt-5-mini",
        input=cast(Any, messages),
        stream=True,
        text={
            "format": {
                "type": "text"
            },
            "verbosity": "medium"
        },
        reasoning={
            "effort": "medium",
            "summary": "auto"
        },
        tools=[
            {
                "type": "web_search",
                "user_location": {
                    "type": "approximate",
                    "country": "CA"
                },
                "search_context_size": "medium"
            }
        ],
        store=True,
        include=[
            "reasoning.encrypted_content",
            "web_search_call.action.sources"
        ]
    )

    # Response types we care about: (response.<type>)
    # created                       - "Thinking…"
    # in_progress                   - "Thinking…"
    # output_item.added             - 
    # output_text.delta             - for streaming chunks
    # output_text.done              - specific part is done
    # output_item.done              - 
    # reasoning_summary_text.delta  - "Planning…"
    # web_search_call.searching     - "Searching the web…"
    # web_search_call.completed     - "Found sources…"
    # completed                     -

    text_buffer = ""
    last_emit = time.monotonic()

    async for event in stream:

        t = event.type
        
        if t in ("response.created", "response.in_progress"):
            status = "thinking"

        elif t == "response.reasoning_summary_text.delta":
            status = "reasoning"
            # optional: accumulate summary text

        elif t == "response.web_search_call.searching":
            status = "searching_web"

        elif t == "response.web_search_call.completed":
            status = "writing_answer"

        elif t == "response.output_text.delta":
            # NOTE: type: ignore because elif t == "..." should guarantee .delta exists
            text_buffer += event.delta # type: ignore

        elif t == "response.output_text.done":
            pass

        elif t == "response.output_item.done":
            pass

        elif t == "response.completed":
            status = "done"
        
        now = time.monotonic()
        if text_buffer and (now - last_emit >= emit_interval):
            yield text_buffer
            text_buffer = ""
            last_emit = time.monotonic()

    if text_buffer:
        yield text_buffer
    

async def main():

    async for chunk in stream_msg_openai([
        {
            "role": "user",
            "content": "Bobby: What is the capital of Canada?"
        },
        {
            "role": "assistant",
            "content": "The capital of Canada is Ottawa."
        },
        {
            "role": "user",
            "content": "Bobby: What's the weather like in Toronto right now?"
        }]):
        print("CHUNK:", chunk)

if __name__ == "__main__":
    asyncio.run(main())