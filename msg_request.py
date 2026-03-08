import os
import aiohttp
import asyncio
import json
import time
from typing import cast, Any

from openai import AsyncOpenAI

from search import close_http_session, init_http_session, web_search_brave

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
async def stream_msg_openai(
        messages: list[dict], 
        emit_interval: float = 1.0, 
        max_steps: int = 10):

    # Conversation details for tools
    conversation_items: list[Any] = list(messages)

    # Safety loop to prevent too many searches
    for step in range(max_steps):
        allow_tools = step < 4

        stream = await client.responses.create(
            model="gpt-5.1-codex-mini",
            input=cast(Any, conversation_items),
            stream=True,
            text={
                "format": {
                    "type": "text"
                },
                "verbosity": "medium"
            },
            reasoning={
                "effort": "low",
                "summary": "auto"
            },
            tools=cast(Any, TOOLS) if allow_tools else [],
            tool_choice="auto" if allow_tools else "none",
            store=True,
            include=[
                "reasoning.encrypted_content",
            ]
        )

        text_buffer = ""
        reasoning_buffer = ""
        last_text_emit = time.monotonic()
        last_reasoning_emit = time.monotonic()
        last_status = None

        # Buffers for tool calls
        function_args_by_item_id: dict[str, str] = {}
        
        # Tool calls fully requested
        requested_tool_calls: list[Any] = []

        # Items produced this response; append to conversation for context in future steps
        response_items: list[Any] = []

        async for event in stream:

            t = event.type

            # Emit any reasoning buffer if leaving reasoning status
            if t != "response.reasoning_summary_text.delta":
                if last_status == "reasoning" and reasoning_buffer:
                    # Emit any buffered reasoning summary before changing status
                    if reasoning_buffer:
                        yield {"type": "reasoning", "delta": reasoning_buffer}
                        reasoning_buffer = ""
            
            if t in ("response.created", "response.in_progress"):
                if last_status != "thinking":
                    last_status = "thinking"
                    yield {"type": "status", "status": "thinking"}

            elif t == "response.reasoning_summary_text.delta":
                if last_status != "reasoning":
                    last_status = "reasoning"
                    yield {"type": "status", "status": "reasoning"}

                # Thinking summary
                reasoning_buffer += getattr(event, "delta", "")

                # Emit buffered reasoning summary at intervals
                now = time.monotonic()
                if reasoning_buffer and (now - last_reasoning_emit >= emit_interval):
                    yield {"type": "reasoning", "delta": reasoning_buffer}
                    reasoning_buffer = ""
                    last_reasoning_emit = now

            elif t == "response.function_call_arguments.delta":
                item_id = getattr(event, "item_id", None)
                delta = getattr(event, "delta", "")
                if item_id:
                    function_args_by_item_id[item_id] = function_args_by_item_id.get(item_id, "") + delta

            elif t == "response.output_text.delta":
                if last_status != "writing":
                    last_status = "writing"
                    yield {"type": "status", "status": "writing"}
                
                text_buffer += getattr(event, "delta", "")

                # Emit buffered text at intervals
                now = time.monotonic()
                if text_buffer and (now - last_text_emit >= emit_interval):
                    yield {"type": "text", "delta": text_buffer}
                    text_buffer = ""
                    last_text_emit = now

            elif t == "response.output_item.done":
                item = getattr(event, "item", None)
                if item is None:
                    continue
                
                response_items.append(item)

                item_type = getattr(item, "type", "")
                if item_type == "function_call":
                    item_id = getattr(item, "id", "")
                    streamed_args = function_args_by_item_id.get(item_id, "")
                    if streamed_args:
                        item.arguments = streamed_args
                    requested_tool_calls.append(item)

            elif t == "response.completed":
                if reasoning_buffer:
                    yield {"type": "reasoning", "delta": reasoning_buffer}
                    reasoning_buffer = ""

                if text_buffer:
                    yield {"type": "text", "delta": text_buffer}
                    text_buffer = ""

            elif t == "error":
                yield {
                    "type": "error",
                    "message": getattr(event, "message", "Unknown stream error"),
                }
                return
        # End Async stream

        # Save conversation items
        conversation_items.extend(response_items)

        # End if no tools requested
        if not requested_tool_calls:
            yield {"type": "status", "status": "done"}
            return

        # Process tool calls
        for call in requested_tool_calls:
            tool_name = getattr(call, "name", "")
            call_id = getattr(call, "call_id", "")
            raw_args = getattr(call, "arguments", "{}")

            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                tool_result = {"error": f"Invalid JSON arguments for tool {tool_name}: {raw_args}"}
            else:
                yield {"type": "status", "status": f"running_tool:{tool_name}"}
                try:
                    yield {"type": "tool", "tool_name": tool_name, "args": args}
                    tool_result = await run_tool(tool_name, args)
                except Exception as e:
                    tool_result = {"error": f"Error running tool {tool_name}: {str(e)}"}
            
            conversation_items.append(
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(tool_result)
                }
            )

            # print("TOOL NAME:", tool_name)
            # print("CALL ID:", call_id)
            # print("RAW ARGS:", raw_args)
            # print("TOOL RESULT:", tool_result)


    # End protection for loop
    yield {
        "type": "error",
        "message": f"Maximum steps={max_steps} reached without completion.",
    }
    

# OpenAI Custom Tools
SEARCH_TOOL = {
    "type": "function",
    "name": "web_search",
    "description": "Search the web for current information.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string"}
        },
        "required": ["query"],
        "additionalProperties": False,
    },
}

TOOLS = [SEARCH_TOOL]

async def run_tool(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    if tool_name == SEARCH_TOOL["name"]:
        return await web_search_brave(args["query"])
    return {"error": f"Unknown tool: {tool_name}"}


async def main():
    await init_http_session()

    msgs = [
        {
            "role": "developer",
            "content": (
                "You are a Discord bot. "
                "Use the web_search tool at most two times when current external information is needed. "
                "If the tool returns enough information, answer directly. "
                "Do not repeat the same search. "
                "If required information is missing, ask a clarifying question. "
                "The current date is March 8, 2026"
            ),
        },
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
            "content": "Bobby: Who is the current prime minister of Canada?"
        },
    ]

    try:
        async for chunk in stream_msg_openai(msgs, emit_interval=0.5):
            print(chunk)
    finally:
        await close_http_session()

if __name__ == "__main__":
    asyncio.run(main())