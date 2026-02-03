import discord
from discord.ext import commands
from discord import app_commands
import psycopg
from datetime import datetime, timedelta
import os
from flask import Flask
from threading import Thread

TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ===== Flask dla uptime ====
app = Flask("")

@app.route("/")
def home():
    return "Bot działa ✅"

def keep_alive():
    port = int(os.environ.get("PORT", 8080))  # Render wymaga PORT
    Thread(target=lambda: app.run(host="0.0.0.0", port=port)).start()

def get_conn():
    return psycopg.connect(DATABASE_URL)
# ================== DB ==================
conn = psycopg.connect(DATABASE_URL)
conn.autocommit = True
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS drivers (
    user_id BIGINT PRIMARY KEY,
    roblox TEXT,
    team TEXT,
    DSQ INT DEFAULT 0,
    DNF INT DEFAULT 0,
    DNS INT DEFAULT 0,
    PKT INT DEFAULT 0,
    RCS INT DEFAULT 0,
    PP INT DEFAULT 0,
    FL INT DEFAULT 0,
    SP REAL DEFAULT 0
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS server_stats (
    id INT PRIMARY KEY,
    DSQ INT DEFAULT 0,
    DNF INT DEFAULT 0,
    DNS INT DEFAULT 0,
    PKT INT DEFAULT 0,
    RCS INT DEFAULT 0,
    last_mvp BIGINT,
    last_race TEXT,
    top_driver BIGINT,
    top_team TEXT
)
""")

cur.execute("INSERT INTO server_stats (id) VALUES (1) ON CONFLICT DO NOTHING")

cur.execute("""
CREATE TABLE IF NOT EXISTS races (
    track TEXT PRIMARY KEY,
    date TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS grids (
    track TEXT,
    user_id BIGINT,
    position INT,
    type TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS mvp_votes (
    voter BIGINT,
    target BIGINT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS warns (
    user_id BIGINT,
    reason TEXT,
    time TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS mvp_votes (
    voter_id BIGINT PRIMARY KEY,
    target_id BIGINT NOT NULL
)
""")

# ================== READY ==================
@bot.event
async def on_ready():
    await tree.sync()
    print("BOT ONLINE (DATABASE_URL)")

# ================== ADMIN CHECK ==================
def is_admin(interaction: discord.Interaction):
    return interaction.user.guild_permissions.administrator

# ================== LINK ROBLOX ==================
@tree.command(name="link_roblox")
async def link_roblox(interaction: discord.Interaction, nick: str):
    cur.execute("""
    INSERT INTO drivers (user_id, roblox)
    VALUES (%s,%s)
    ON CONFLICT (user_id) DO UPDATE SET roblox=EXCLUDED.roblox
    """,(interaction.user.id,nick))
    await interaction.user.edit(nick=f"{interaction.user.name}({nick})")
    await interaction.response.send_message("✅ Roblox podpięty")

# ================== DRIVER STATS ==================
@tree.command(name="driver_stats")
async def driver_stats(interaction: discord.Interaction, user: discord.Member):
    cur.execute("SELECT * FROM drivers WHERE user_id=%s",(user.id,))
    d = cur.fetchone()
    if not d:
        await interaction.response.send_message("Brak danych")
        return

    embed = discord.Embed(title=f"📊 {user}", color=discord.Color.red())
    labels = ["Roblox","Team","DSQ","DNF","DNS","PKT","RCS","PP","FL","ŚP"]
    for i,l in enumerate(labels, start=1):
        embed.add_field(name=l, value=d[i])
    await interaction.response.send_message(embed=embed)

# ================== UPDATE DRIVER ==================
@tree.command(name="update_driver")
@app_commands.check(is_admin)
async def update_driver(interaction: discord.Interaction, user: discord.Member,
                        dsq:int=0, dnf:int=0, dns:int=0,
                        pkt:int=0, rcs:int=0, pp:int=0, fl:int=0):
    cur.execute("INSERT INTO drivers (user_id) VALUES (%s) ON CONFLICT DO NOTHING",(user.id,))
    cur.execute("""
    UPDATE drivers SET
    DSQ=DSQ+%s, DNF=DNF+%s, DNS=DNS+%s,
    PKT=PKT+%s, RCS=RCS+%s, PP=PP+%s, FL=FL+%s
    WHERE user_id=%s
    """,(dsq,dnf,dns,pkt,rcs,pp,fl,user.id))
    await interaction.response.send_message("✅ Zaktualizowano drivera")

# ================== MVP ==================
@tree.command(name="mvp_start")
@app_commands.check(is_admin)
async def mvp_start(interaction: discord.Interaction):
    cur.execute("DELETE FROM mvp_votes")
    await interaction.response.send_message("@everyone 🏆 **MVP – głosowanie START**")

@tree.command(name="mvp_vote", description="Oddaj głos na MVP")
async def mvp_vote(interaction: discord.Interaction, target: discord.Member):
    with get_conn() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "INSERT INTO mvp_votes (voter_id, target_id) VALUES (%s,%s)",
                    (interaction.user.id, target.id)
                )
                conn.commit()
            except psycopg.errors.UniqueViolation:
                await interaction.response.send_message(
                    "❌ Już oddałeś głos na MVP",
                    ephemeral=True
                )
                return

    await interaction.response.send_message("🗳️ Głos oddany", ephemeral=True)

@tree.command(name="mvp_end", description="Zakończ głosowanie MVP")
@app_commands.check(is_admin)
async def mvp_end(interaction: discord.Interaction):
    with get_conn() as conn:
        with conn.cursor() as cur:

            cur.execute("""
            SELECT target_id, COUNT(*) 
            FROM mvp_votes
            GROUP BY target_id
            ORDER BY COUNT(*) DESC
            LIMIT 1
            """)
            r = cur.fetchone()

            if not r:
                await interaction.response.send_message("❌ Brak głosów")
                return

            mvp_id = r[0]

            # zapis MVP do statystyk serwera
            cur.execute(
                "UPDATE server_stats SET last_mvp=%s WHERE id=1",
                (mvp_id,)
            )

            # 🔥 USUNIĘCIE WSZYSTKICH GŁOSÓW (RESET GŁOSOWANIA)
            cur.execute("DELETE FROM mvp_votes")

            conn.commit()

    await interaction.response.send_message(f"🏆 **MVP wyścigu:** <@{mvp_id}>")


# ================== WYŚCIG ==================
@tree.command(name="race_add")
@app_commands.check(is_admin)
async def race_add(interaction: discord.Interaction, track: str, date: str):
    cur.execute("INSERT INTO races VALUES (%s,%s) ON CONFLICT DO NOTHING",(track,date))
    await interaction.response.send_message("🏁 Wyścig dodany")

@tree.command(name="starting_grid")
@app_commands.check(is_admin)
async def starting_grid(interaction: discord.Interaction, track: str, drivers: str):
    cur.execute("DELETE FROM grids WHERE track=%s AND type='start'",(track,))
    for i,uid in enumerate(drivers.replace("<@","").replace(">","").split()):
        cur.execute("INSERT INTO grids VALUES (%s,%s,%s,'start')",(track,int(uid),i+1))
    await interaction.response.send_message("📋 Grid startowy zapisany")

@tree.command(name="ending_grid")
@app_commands.check(is_admin)
async def ending_grid(interaction: discord.Interaction, track: str, drivers: str):
    cur.execute("DELETE FROM grids WHERE track=%s AND type='end'",(track,))
    for i,uid in enumerate(drivers.replace("<@","").replace(">","").split()):
        uid=int(uid)
        cur.execute("INSERT INTO grids VALUES (%s,%s,%s,'end')",(track,uid,i+1))
        cur.execute("UPDATE drivers SET PKT=PKT+%s WHERE user_id=%s",(max(0,25-i*2),uid))
    await interaction.response.send_message("🏁 Wyniki zapisane")

# ================== PODIUM ==================
@tree.command(name="podium")
async def podium(interaction: discord.Interaction, track: str):
    cur.execute("""
    SELECT user_id FROM grids
    WHERE track=%s AND type='end'
    ORDER BY position LIMIT 3
    """,(track,))
    p = cur.fetchall()
    embed = discord.Embed(title=f"🏆 Podium – {track}", color=discord.Color.gold())
    for m,u in zip(["🥇","🥈","🥉"],p):
        embed.add_field(name=m, value=f"<@{u[0]}>")
    await interaction.response.send_message(embed=embed)

# ================== WARN / MUTE ==================
from datetime import datetime

@tree.command(name="admin_warn", description="Nadaj warna użytkownikowi")
@app_commands.check(is_admin)
async def admin_warn(
    interaction: discord.Interaction,
    user: discord.Member,
    reason: str
):
    with get_conn() as conn:
        with conn.cursor() as cur:
            # dodaj warn
            cur.execute(
                "INSERT INTO warns (user_id, reason, created_at) VALUES (%s,%s,%s)",
                (user.id, reason, datetime.utcnow())
            )

            # policz warny
            cur.execute(
                "SELECT COUNT(*) FROM warns WHERE user_id=%s",
                (user.id,)
            )
            warn_count = cur.fetchone()[0]

            conn.commit()

    await interaction.response.send_message(
        f"⚠️ **Warn nadany** — to jest **{warn_count}. warn** tej osoby."
    )

@tree.command(name="admin_warns", description="Sprawdź warny użytkownika")
@app_commands.check(is_admin)
async def admin_warns(
    interaction: discord.Interaction,
    user: discord.Member
):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT reason, created_at FROM warns WHERE user_id=%s ORDER BY created_at",
                (user.id,)
            )
            rows = cur.fetchall()

    if not rows:
        await interaction.response.send_message(
            f"✅ {user.mention} nie ma żadnych warnów."
        )
        return

    embed = discord.Embed(
        title=f"⚠️ Warny użytkownika: {user.display_name}",
        description=f"Łącznie: **{len(rows)}**",
        color=discord.Color.orange()
    )

  for i, (reason, date) in enumerate(rows, start=1):
    embed.add_field(
        name=f"Warn #{i}",
        value=f"📄 {reason}\n🕒 {date}",  # <--- używasz stringa bez .strftime
        inline=False
    )

    await interaction.response.send_message(embed=embed)

@tree.command(name="admin_mute")
@app_commands.check(is_admin)
async def admin_mute(interaction: discord.Interaction, user: discord.Member, minutes: int):
    await user.timeout(datetime.utcnow()+timedelta(minutes=minutes))
    await interaction.response.send_message("🔇 Mute nadany")

# ================== TEAM ==================
@tree.command(name="add_team")
@app_commands.check(is_admin)
async def add_team(interaction: discord.Interaction, user: discord.Member, team: str):
    cur.execute("UPDATE drivers SET team=%s WHERE user_id=%s",(team,user.id))
    await interaction.response.send_message("🏎️ Team ustawiony")

# ================== LIGA ==================
@tree.command(name="liga_table")
async def liga_table(interaction: discord.Interaction, view: str):
    if view=="kierowcy":
        cur.execute("SELECT user_id, PKT FROM drivers ORDER BY PKT DESC")
        rows=cur.fetchall()
        text="\n".join([f"{i+1}. <@{r[0]}> – {r[1]} pkt" for i,r in enumerate(rows)])
    else:
        cur.execute("SELECT team, SUM(PKT) FROM drivers GROUP BY team ORDER BY 2 DESC")
        rows=cur.fetchall()
        text="\n".join([f"{i+1}. {r[0]} – {r[1]} pkt" for i,r in enumerate(rows)])
    await interaction.response.send_message(embed=discord.Embed(title="📊 Liga",description=text))

# ================= MANUAL CONTENT =================

NUMERY_TEXT = """
5,7,9,10,18,20,28,30,31,32,34,35,36,38,39,40,42,43,45,46,48,49,50,51,52,53,54,55,56,57,58,59,60,62,64,65,66,68,69,70,73,74,75,76,78,79,81,82,83,84,85,86,89,90,91,92,93,94,95,96,97,98,99
"""

WYS_CIG_TEXT = """
🏁 Następny wyścig:
📍 Tor: Silverstone
📅 Data: 07.02.2026
⏰ Godzina: 18:00
"""

# ================= /numery =================
@tree.command(name="numery", description="Lista dostępnych numerów")
async def numery_slash(interaction: discord.Interaction):
    await interaction.response.send_message(NUMERY_TEXT)

# ================= !numery =================
@bot.command(name="numery")
async def numery_prefix(ctx: commands.Context):
    await ctx.send(NUMERY_TEXT)

# ================= /wyscig =================
@tree.command(name="wyscig", description="Informacje o wyścigu")
async def wyscig_slash(interaction: discord.Interaction):
    await interaction.response.send_message(WYS_CIG_TEXT)

# ================= !wyscig =================
@bot.command(name="wyscig")
async def wyscig_prefix(ctx: commands.Context):
    await ctx.send(WYS_CIG_TEXT)

keep_alive()
bot.run(TOKEN)










