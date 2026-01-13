import os
import discord
from discord.ext import commands
from flask import Flask
from threading import Thread

# ------------------- KEEP ALIVE -------------------
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ------------------- DISCORD BOT -------------------
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --- Ustaw ID kanałów i reakcje ---
CHANNEL1_ID = 1460369374908125258  # Wstaw ID pierwszego kanału
CHANNEL2_ID = 1460369400648433806  # Wstaw ID drugiego kanału

REACTION1 = "🤣"
REACTION2 = "🤣"

@bot.event
async def on_ready():
    print(f"Zalogowany jako {bot.user}")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if message.channel.id == CHANNEL1_ID:
        await message.add_reaction(REACTION1)
    elif message.channel.id == CHANNEL2_ID:
        await message.add_reaction(REACTION2)

    await bot.process_commands(message)

# --- START ---
keep_alive()
bot.run(os.getenv("DISCORD_TOKEN"))
