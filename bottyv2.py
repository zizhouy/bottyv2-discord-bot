import os
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from collections import defaultdict
from datetime import datetime, timezone

from msg_request import stream_msg, stream_msg_openai
from memory import ChannelMemory
from heartbeat import heartbeat_task
from search import init_http_session, close_http_session

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN environment variable not set")

intents = discord.Intents.none()
bot = commands.Bot(command_prefix="!", intents=intents)

TEST_GUILD_ID = os.getenv("GUILD_IDS")
ALLOWED_USERS_STR = os.getenv("USER_IDS")
if ALLOWED_USERS_STR:
    ALLOWED_USERS = set(int(uid.strip()) for uid in ALLOWED_USERS_STR.split(","))
else:
    ALLOWED_USERS = set()

BUFFER_SOFT_CUT = 1400
BUFFER_HARD_CUT = 1800

SYSTEM_MESSAGE = {
    "role": "system",
    "content": (
        "You are BottyV2, a helpful assistant for Discord users. "
        "Your name is BottyV2. "
        "User messages will be formatted as \"Username: prompt\". "
        "You should respond with only the assistant's reply. "
        "Respond clearly and concisely, suitable for Discord. "
        "Use web search only if absolutely necessary and at most once."
    )
}

mem = ChannelMemory(system_message=SYSTEM_MESSAGE, keep_turns=8)
channel_locks = defaultdict(asyncio.Lock)

# 
@bot.event
async def setup_hook():
    if TEST_GUILD_ID:
        guild = discord.Object(id=TEST_GUILD_ID)
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
        await bot.tree.sync()
        print("Slash commands synced globally")
    else:
        await bot.tree.sync()
        print("Slash commands synced globally")

# 
@bot.tree.command(name="ask", description="One-off helper command")
@app_commands.allowed_installs(users=True, guilds=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def ask(interaction: discord.Interaction, question: str):
    channel_id = interaction.channel_id or -1
    user = interaction.user

    print(f"User: {user.display_name}\nChannel: {channel_id}\nQuestion: {question}")
    if user.id not in ALLOWED_USERS:
        await interaction.response.send_message("You are not authorized to use this command.", ephemeral=True)
        return
    
    await interaction.response.defer(
            ephemeral=False # visible to everyone in channel, not just user
    )
    
    # Only act in one channel at a time
    #  (LLM processes one at a time)
    async with channel_locks[channel_id]:

        # Update with current date
        now = datetime.now(timezone.utc).strftime("%A, %Y-%m-%d at %H:%M UTC")
        time_updated_system_message = SYSTEM_MESSAGE.copy()
        time_updated_system_message["content"] += f" Current time is {now}."
        mem.set_system_message(channel_id, time_updated_system_message)

        mem.append_user(channel_id, f"[Display name: {user.display_name} | Username {user.name} | User ID: {user.id} ]\n{question}")
        history = mem.get(channel_id)
    
        # Show user message
        await interaction.followup.send(f"**@ChatGPT** {question}\n\n")

        message_buffer = ""
        full_text = ""

        reasoning_buffer = ""

        last_message = await interaction.followup.send("…", wait=True)

        async for event in stream_msg_openai(history, emit_interval=0.5):
            chunk = ""

            if event["type"] == "status":
                status = event["status"]
                if status == "thinking":
                    await last_message.edit(content="Thinking…")
                elif status == "searching":
                    await last_message.edit(content="Searching the web…")
                elif status == "done_searching":
                    await last_message.edit(content="Done searching")
                elif status == "done":
                    break

                print(f"Status: {status}")
                continue

            elif event["type"] == "reasoning":
                reasoning_buffer += event["delta"]

                if len(reasoning_buffer) > 1500:
                    reasoning_buffer = reasoning_buffer[-1000:]

                await last_message.edit(content=f"**Reasoning…**\n*{reasoning_buffer}*")
                continue

            elif event["type"] == "tool":
                if event["tool_name"] == "web_serach":
                    await last_message.edit(content=f"**Reasoning…**\n*{reasoning_buffer}*\n**Searching: {event["args"]}")

            elif event["type"] == "text":
                chunk = event["delta"]

            elif event["type"] == "error":
                await last_message.edit(content=f"Error: {event.get('message', 'Unknown error')}")
                return

            
            message_buffer += chunk
            full_text += chunk

            buffer_len = len(message_buffer)

            # If cutting
            #  (checking for newline or if nearing hard cut-off)
            while buffer_len > BUFFER_SOFT_CUT and "\n" in chunk or buffer_len > BUFFER_HARD_CUT:
                end_line_index = BUFFER_HARD_CUT # hard cutoff
                for end_token in ["\n", ". ", "! ", "? ", "-", ", ", " "]: # possible "nice" break points
                    idx = message_buffer[:BUFFER_HARD_CUT].rfind(end_token)
                    if idx != -1:
                        end_line_index = idx + (len(end_token) if end_token.strip() else 0)
                        break

                # Update last message and start new buffer
                await last_message.edit(content=message_buffer[:end_line_index + 1])
                message_buffer = message_buffer[end_line_index + 1:]
                buffer_len = len(message_buffer)

                # Start new message if there's still buffer
                if message_buffer.strip():
                    last_message = await interaction.followup.send("…", wait=True)

            # Done/Not cutting, just update message
            await last_message.edit(content=message_buffer + "…")

        await last_message.edit(content=message_buffer)
        print(f"Full text -----\n{full_text}\n-----")
        mem.append_assistant(channel_id, full_text)

# alive heartbeat task
@bot.event
async def on_ready():
    await init_http_session()
    bot.loop.create_task(heartbeat_task())

    print(f'We have logged in as {bot.user}')


bot.run(TOKEN)
