import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask
from threading import Thread
import psycopg
import os

# ------------------- KEEP ALIVE -------------------
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    Thread(target=run).start()

# ------------------- BAZA DANYCH -------------------
DATABASE_URL = os.getenv("DATABASE_URL")

def get_conn():
    return psycopg.connect(DATABASE_URL)

def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    numer SERIAL PRIMARY KEY,
                    message_id BIGINT NOT NULL,
                    channel_id BIGINT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

def get_next_number():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(numer) FROM messages")
            result = cur.fetchone()[0]
            return (result or 0) + 1

def save_message(numer, message_id, channel_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO messages (numer, message_id, channel_id) VALUES (%s, %s, %s)",
                (numer, message_id, channel_id)
            )
            conn.commit()

def get_message_id(numer):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT message_id, channel_id FROM messages WHERE numer = %s", (numer,))
            result = cur.fetchone()
            return result if result else None

# ------------------- DISCORD -------------------
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

AUTO_CHANNELS = {
    1460369374908125258,
    1460369400648433806
}
REACTION = "🤣"

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
        except:
            pass
    await bot.process_commands(message)

# ------------------- NUMERY -------------------
NUMERY_TEXT = (
    "Dostępne numery:\n"
    "2,4,5,8,9,10,16,18,20,23,24,25,27,28,30,32,34,35,36,38,39,40,"
    "42,43,45,46,48,49,50,51,52,53,54,55,56,57,58,59,60,62,64,"
    "65,66,67,68,69,70,73,74,75,76,78,79,81,82,83,84,85,86,"
    "89,90,91,92,93,94,95,96,97,98"
)

@tree.command(name="numery", description="Wyświetla listę numerów")
async def numery_slash(interaction: discord.Interaction):
    await interaction.response.send_message(NUMERY_TEXT, ephemeral=True)

@bot.command(name="numery")
async def numery_prefix(ctx):
    await ctx.send(NUMERY_TEXT)

# ------------------- WYSYŁANIE -------------------
@tree.command(name="wyslij", description="Wyślij wiadomość z numerem")
@app_commands.describe(channel="Kanał", tresc="Treść")
async def wyslij(interaction: discord.Interaction, channel: discord.TextChannel, tresc: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Brak uprawnień ❌", ephemeral=True)
        return

    numer = get_next_number()
    msg = await channel.send(tresc)
    nowa_tresc = nowa_tresc.replace("|", "\n")
    await msg.edit(content=nowa_tresc)
    save_message(numer, msg.id, channel.id)
    await interaction.response.send_message(f"Wysłano wiadomość\nNumer: **{numer}**", ephemeral=True)

# ------------------- UPDATE -------------------
@tree.command(name="update", description="Edytuj wiadomość po numerze")
@app_commands.describe(numer="Numer wiadomości", nowa_tresc="Nowa treść")
async def update(interaction: discord.Interaction, numer: int, nowa_tresc: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Brak uprawnień ❌", ephemeral=True)
        return

    result = get_message_id(numer)
    if not result:
        await interaction.response.send_message("Nie ma takiego numeru ❌", ephemeral=True)
        return

    message_id, channel_id = result
    channel = bot.get_channel(channel_id)
    if not channel:
        await interaction.response.send_message("Nie znaleziono kanału ❌", ephemeral=True)
        return

    try:
        msg = await channel.fetch_message(message_id)
# zamiana separatora "|" na nową linię
        nowa_tresc = nowa_tresc.replace("|", "\n")
        await msg.edit(content=nowa_tresc)

        await interaction.response.send_message("Zaktualizowano ✅", ephemeral=True)
    except:
        await interaction.response.send_message("Nie znaleziono wiadomości ❌", ephemeral=True)

# ------------------- START -------------------
init_db()
keep_alive()
bot.run(os.getenv("DISCORD_TOKEN"))


