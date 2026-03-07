import os
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from collections import defaultdict

from msg_request import stream_msg, stream_msg_openai
from memory import ChannelMemory

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
        "About web searches: Use only if necessary and HARD limit to 3 searches MAX. "
        "If more searches are needed, ASK the user first."
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
    username = interaction.user.display_name

    print(f"User: {username}\nChannel: {channel_id}\nQuestion: {question}")
    if interaction.user.id not in ALLOWED_USERS:
        await interaction.response.send_message("You are not authorized to use this command.", ephemeral=True)
        return
    
    await interaction.response.defer(
            ephemeral=False # visible to everyone in channel, not just user
    )
    
    # Only act in one channel at a time
    #  (LLM processes one at a time)
    async with channel_locks[channel_id]:
        mem.append_user(channel_id, f"{username}: {question}")
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

                await last_message.edit(content="**Reasoning…**\n" + "*" + reasoning_buffer + "*")
                continue

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
            if buffer_len > BUFFER_SOFT_CUT and "\n" in chunk or buffer_len > BUFFER_HARD_CUT:
                end_line_index = message_buffer.rfind("\n")
                if end_line_index == -1:
                    end_line_index = message_buffer.rfind(". ") + 1
                    if end_line_index == -1:
                        end_line_index = min(BUFFER_HARD_CUT, buffer_len)  # hard cut-off

                # Update last message and start new buffer
                await last_message.edit(content=message_buffer[:end_line_index + 1])
                message_buffer = message_buffer[end_line_index + 1:]

                # Start new message if there's remaining buffer
                if chunk: # FIXME: probably change chunk to message_buffer
                    last_message = await interaction.followup.send(message_buffer + "…", wait=True)
            
            # Not cutting, keep updating last message
            else:
                print("Edit")
                await last_message.edit(content=message_buffer + "…")

        await last_message.edit(content=message_buffer)
        print(f"Full text -----\n{full_text}\n-----")
        mem.append_assistant(channel_id, full_text)

# alive heartbeat task
@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}')
    from heartbeat import heartbeat_task
    bot.loop.create_task(heartbeat_task())


bot.run(TOKEN)
