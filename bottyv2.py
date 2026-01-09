import os
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from collections import defaultdict

from msg_request import stream_msg
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
        "You should repspond with only the assistant's reply. "
        "Respond clearly and concisely, suitable for Discord."
    )
}

mem = ChannelMemory(system_message=SYSTEM_MESSAGE, keep_turns=15)
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
            ephemeral=False
    )
    
    async with channel_locks[channel_id]:
        mem.append_user(channel_id, f"{username}: {question}")
        history = mem.get(channel_id)
    
        
        await interaction.followup.send(f"**@ChatGPT** {question}\n\n")

        message_buffer = ""
        full_text = ""

        last_message = await interaction.followup.send("…", wait=True)

        async for chunk in stream_msg(history, emit_interval=0.5):
            message_buffer += chunk
            full_text += chunk    

            buffer_len = len(message_buffer)
            if buffer_len > BUFFER_SOFT_CUT and "\n" in chunk or buffer_len > BUFFER_HARD_CUT:
                end_line_index = message_buffer.rfind("\n")
                if end_line_index == -1:
                    end_line_index = message_buffer.rfind(". ") + 1
                    if end_line_index == -1:
                        end_line_index = min(BUFFER_HARD_CUT, buffer_len)  # hard cut-off

                await last_message.edit(content=message_buffer[:end_line_index + 1])
                message_buffer = message_buffer[end_line_index + 1:]
                if not chunk:
                    break
                last_message = await interaction.followup.send(message_buffer, wait=True)
            else:
                await last_message.edit(content=message_buffer)

    
        print(f"Full text -----\n{full_text}\n-----")
        mem.append_assistant(channel_id, full_text)

bot.run(TOKEN)
