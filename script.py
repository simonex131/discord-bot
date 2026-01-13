import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask
from threading import Thread
import json
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

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# --- AUTO REAKCJE ---
AUTO_CHANNELS = {
    1460369374908125258,  # kanał 1
    1460369400648433806   # kanał 2
}
REACTION = "🤣"

# --- JSON do przechowywania numerów wiadomości ---
JSON_FILE = "messages.json"

if os.path.exists(JSON_FILE):
    with open(JSON_FILE, "r") as f:
        messages = json.load(f)
        # Zamieniamy klucze na int
        messages = {int(k): v for k, v in messages.items()}
else:
    messages = {}

def save_messages():
    with open(JSON_FILE, "w") as f:
        json.dump(messages, f)

# --- EVENTY ---
@bot.event
async def on_ready():
    await tree.sync()
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

# --- FUNKCJE WSPÓLNE ---
async def wyswietl_ping(ctx_or_interaction, ephemeral=False):
    tresc = "Dostępne numery: 2,4,5,8,9,10,16,18,20,23,24,25,27,28,30,32,34,35,36,38,39,40,42,43,45,46,48,49,50,51,52,53,54,55,56,57,58,59,60,62,64,65,66,67,68,69,70,73,74,75,76,78,79,81,82,83,84,85,86,89,90,91,92,93,94,95,96,97,98"
    if isinstance(ctx_or_interaction, discord.Interaction):
        await ctx_or_interaction.response.send_message(tresc, ephemeral=ephemeral)
    else:
        await ctx_or_interaction.send(tresc)

async def wyslij_nowa(channel, tresc):
    numer = max(messages.keys(), default=0) + 1
    wiadomosc = await channel.send(tresc)
    messages[numer] = wiadomosc.id
    save_messages()
    return numer

# --- PING ---
@tree.command(name="ping", description="Wyświetla listę dostępnych numerów")
async def ping(interaction: discord.Interaction):
    await wyswietl_ping(interaction, ephemeral=True)

@bot.command()
async def ping(ctx):
    await wyswietl_ping(ctx)

# --- WYSYŁANIE NOWEJ WIADOMOŚCI ---
@tree.command(name="wyslij", description="Wyślij wiadomość i nadaj numer")
@app_commands.describe(channel="Kanał", tresc="Treść wiadomości")
async def wyslij(interaction: discord.Interaction, channel: discord.TextChannel, tresc: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Brak uprawnień ❌", ephemeral=True)
        return
    numer = await wyslij_nowa(channel, tresc)
    await interaction.response.send_message(f"Wysłano wiadomość! Numer: {numer}", ephemeral=True)

# --- AKTUALIZACJA WIADOMOŚCI PO NUMERZE ---
@tree.command(name="update", description="Edytuj wiadomość bota po numerze")
@app_commands.describe(numer="Numer wiadomości nadany przez bota", nowa_tresc="Nowa treść")
async def update(interaction: discord.Interaction, numer: int, nowa_tresc: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Brak uprawnień ❌", ephemeral=True)
        return
    message_id = messages.get(numer)
    if not message_id:
        await interaction.response.send_message("Nie znaleziono wiadomości o tym numerze ❌", ephemeral=True)
        return
    channel = interaction.channel
    try:
        wiadomosc = await channel.fetch_message(message_id)
        await wiadomosc.edit(content=nowa_tresc)
        await interaction.response.send_message("Wiadomość zaktualizowana ✅", ephemeral=True)
    except discord.NotFound:
        await interaction.response.send_message("Nie znaleziono wiadomości w kanale 😢", ephemeral=True)

# --- START ---
keep_alive()
bot.run(os.getenv("DISCORD_TOKEN"))

