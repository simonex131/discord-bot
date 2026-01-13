import discord
from discord.ext import commands
from flask import Flask
from threading import Thread
import os

# --- KEEP ALIVE ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- INTENTS ---
intents = discord.Intents.default()
intents.message_content = True

# --- BOT ---
bot = commands.Bot(command_prefix="!", intents=intents)

# --- ID KANAŁÓW (TU WPISZ SWOJE) ---
AUTO_CHANNELS = {
    1460369374908125258,  # kanał 1
    1460369400648433806   # kanał 2
}

# --- REAKCJA ---
REACTION = "👍"

@bot.event
async def on_ready():
    print(f"Zalogowano jako {bot.user}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.channel.id in AUTO_CHANNELS:
        try:
            await message.add_reaction(REACTION)
        except discord.Forbidden:
            print("❌ Brak permisji do reakcji")

    await bot.process_commands(message)

# --- START ---
bot.run(os.getenv("DISCORD_TOKEN"))
