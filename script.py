import discord
from discord import app_commands
from discord.ext import commands, tasks
from flask import Flask
from threading import Thread
import psycopg
import os
import asyncio

# ================= KEEP ALIVE =================
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive"

def keep_alive():
    Thread(target=lambda: app.run(host="0.0.0.0", port=8080)).start()

# ================= DATABASE =================
DATABASE_URL = os.getenv("DATABASE_URL")

def get_conn():
    return psycopg.connect(DATABASE_URL)

def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            # statystyki serwera
            cur.execute("""
            CREATE TABLE IF NOT EXISTS server_stats (
                id INTEGER PRIMARY KEY DEFAULT 1,
                races INTEGER DEFAULT 0,
                total_points INTEGER DEFAULT 0,
                total_dnf INTEGER DEFAULT 0,
                total_dns INTEGER DEFAULT 0,
                last_mvp BIGINT,
                last_best_team TEXT
            );
            INSERT INTO server_stats (id) VALUES (1)
            ON CONFLICT (id) DO NOTHING;
            """)
            # statystyki zawodników
            cur.execute("""
            CREATE TABLE IF NOT EXISTS driver_stats (
                user_id BIGINT PRIMARY KEY,
                races INTEGER DEFAULT 0,
                points INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                podiums INTEGER DEFAULT 0,
                dnf INTEGER DEFAULT 0,
                dns INTEGER DEFAULT 0,
                avg_position REAL DEFAULT 0
            );
            """)
            # wiadomości z numerami
            cur.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                numer SERIAL PRIMARY KEY,
                message_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            conn.commit()

# ================= DISCORD =================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # <-- to jest kluczowe
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

AUTO_CHANNELS = {1460369374908125258, 1460369400648433806}
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

# ================= NUMERY =================
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
    
# ================= WYŚCIG =================
WYSCIG_TEXT = "Następny wyścig: Australia"
@tree.command(name="wyscig", description="Pokazuje, gdzie odbędzie się następny wyścig.")
async def wyscig(interaction: discord.Interaction):
    await interaction.response.send_message(WYSCIG_TEXT, ephemeral=True)

@bot.command(name="wyscig")
async def wyscig_prefix(ctx):
    await ctx.send(WYSCIG_TEXT)

# ================= SERVER STATS =================
def update_server(races=0,dnf=0,dns=0,points=0,mvp=None,team=None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            UPDATE server_stats SET
                races = races + %s,
                total_dnf = total_dnf + %s,
                total_dns = total_dns + %s,
                total_points = total_points + %s,
                last_mvp = COALESCE(%s,last_mvp),
                last_best_team = COALESCE(%s,last_best_team)
            WHERE id=1
            """,(races,dnf,dns,points,mvp,team))
            conn.commit()

@tree.command(name="server_stats", description="Statystyki ligi")
async def server_stats(interaction: discord.Interaction):
    with get_conn() as conn:
        with conn.cursor() as cur:
            # SELECT w określonej kolejności, żeby liczby się zgadzały
            cur.execute("""
                SELECT races, total_dnf, total_dns, total_points, last_mvp, last_best_team
                FROM server_stats
                WHERE id=1
            """)
            r = cur.fetchone()

    embed = discord.Embed(title="📊 Statystyki ligi")
    embed.add_field(name="Wyścigi", value=r[0])
    embed.add_field(name="DNF", value=r[1])
    embed.add_field(name="DNS", value=r[2])
    embed.add_field(name="Punkty łącznie", value=r[3])
    embed.add_field(name="Ostatni MVP", value=f"<@{r[4]}>" if r[4] else "—")
    embed.add_field(name="Najlepsza drużyna", value=r[5] or "—")

    await interaction.response.send_message(embed=embed)

@tree.command(name="update_server_stats", description="Aktualizuj statystyki serwera")
@app_commands.describe(
    races="Ilość wyścigów", total_points="Łączne punkty", total_dnf="Łączne DNF",
    total_dns="Łączne DNS", last_mvp="MVP", last_best_team="Najlepsza drużyna"
)
async def update_server_stats(interaction: discord.Interaction, races:int,total_points:int,
                              total_dnf:int,total_dns:int,last_mvp:discord.Member,last_best_team:str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Brak uprawnień ❌", ephemeral=True)
        return
    update_server(races,total_dnf,total_dns,total_points,last_mvp.id,last_best_team)
    await interaction.response.send_message("Statystyki serwera zaktualizowane ✅", ephemeral=True)

# ================= DRIVER STATS =================
def update_driver(user_id, pos=None, points=0,dnf=False,dns=False):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO driver_stats(user_id) VALUES(%s) ON CONFLICT DO NOTHING",(user_id,))
            cur.execute("""
            UPDATE driver_stats SET
                races = races + 1,
                points = points + %s,
                wins = wins + %s,
                podiums = podiums + %s,
                dnf = dnf + %s,
                dns = dns + %s,
                avg_position = ((avg_position*(races-1)) + %s)/races
            WHERE user_id=%s
            """,(points, 1 if pos==1 else 0,1 if pos and pos<=3 else 0,1 if dnf else 0,
                 1 if dns else 0,pos or 0,user_id))
            conn.commit()

@tree.command(name="driver_stats", description="Statystyki zawodnika")
async def driver_stats(interaction: discord.Interaction, driver:discord.Member=None):
    user = driver or interaction.user
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM driver_stats WHERE user_id=%s",(user.id,))
            r = cur.fetchone()
    if not r:
        await interaction.response.send_message("Brak statów ❌", ephemeral=True)
        return
    embed = discord.Embed(title=f"🏎️ Statystyki: {user.display_name}")
    embed.add_field(name="Wyścigi", value=r[1])
    embed.add_field(name="Punkty", value=r[2])
    embed.add_field(name="Zwycięstwa", value=r[3])
    embed.add_field(name="Podia", value=r[4])
    embed.add_field(name="DNF", value=r[5])
    embed.add_field(name="DNS", value=r[6])
    embed.add_field(name="Śr. pozycja", value=round(r[7],2))
    await interaction.response.send_message(embed=embed)

@tree.command(name="update_driver", description="Aktualizuj statystyki zawodnika")
@app_commands.describe(
    user="Zawodnik", races="Wyścigi", points="Punkty", wins="Wygrane",
    podiums="Podia", dnf="DNF", dns="DNS", avg_position="Średnia pozycja"
)
async def update_driver(interaction: discord.Interaction, user: discord.Member, races: int, points: int, wins: int,
                        podiums: int, dnf: int, dns: int, avg_position: float):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Brak uprawnień ❌", ephemeral=True)
        return

    with get_conn() as conn:
        with conn.cursor() as cur:
            # Tworzymy wpis jeśli nie istnieje
            cur.execute("INSERT INTO driver_stats(user_id) VALUES(%s) ON CONFLICT DO NOTHING", (user.id,))
            
            # Pobieramy aktualne wartości
            cur.execute("SELECT races, points, wins, podiums, dnf, dns, avg_position FROM driver_stats WHERE user_id=%s", (user.id,))
            r = cur.fetchone()
            if r:
                curr_races, curr_points, curr_wins, curr_podiums, curr_dnf, curr_dns, curr_avg = r
            else:
                curr_races = curr_points = curr_wins = curr_podiums = curr_dnf = curr_dns = curr_avg = 0

            # Obliczamy nową średnią pozycję
            total_races = curr_races + races
            if total_races > 0:
                new_avg = ((curr_avg * curr_races) + (avg_position * races)) / total_races
            else:
                new_avg = 0

            # Aktualizujemy wartości w bazie dodając do obecnych
            cur.execute("""
                UPDATE driver_stats SET
                    races = races + %s,
                    points = points + %s,
                    wins = wins + %s,
                    podiums = podiums + %s,
                    dnf = dnf + %s,
                    dns = dns + %s,
                    avg_position = %s
                WHERE user_id = %s
            """, (races, points, wins, podiums, dnf, dns, new_avg, user.id))
            conn.commit()

    await interaction.response.send_message(f"Zaktualizowano staty **{user.display_name}** ✅", ephemeral=True)

# ================= LIGA TABLE & UPDATE TEAM (team1) =================
from discord import app_commands
from discord.ext import commands
import discord

MAX_FIELD_LENGTH = 1024

# ----------------- /liga_table -----------------
@tree.command(name="liga_table", description="Tabela ligi - wybierz widok")
@app_commands.describe(view="Wybierz typ tabeli")
@app_commands.choices(view=[
    app_commands.Choice(name="Kierowcy", value="drivers"),
    app_commands.Choice(name="Drużyny", value="teams")
])
async def liga_table(interaction: discord.Interaction, view: app_commands.Choice[str]):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id, races, points, wins, podiums, dnf, dns, avg_position, team1 FROM driver_stats ORDER BY points DESC")
            drivers = cur.fetchall()

    if not drivers:
        await interaction.response.send_message("Brak danych o zawodnikach ❌", ephemeral=True)
        return

    if view.value == "drivers":
        embed = discord.Embed(title="🏎️ Tabela Kierowców", color=discord.Color.blue())
        for i, d in enumerate(drivers, start=1):
            user_id, races, points, wins, podiums, dnf, dns, avg_pos, team_name = d
            member = interaction.guild.get_member(user_id)
            nick = member.display_name if member else f"Nieobecny ({user_id})"
            team_name = team_name if team_name and team_name != 'N/A' else 'N/A'
            value = (f"Drużyna: {team_name}\n"
                     f"Wyścigi: {races}, Punkty: {points}, Zwycięstwa: {wins}, "
                     f"Podia: {podiums}, DNF: {dnf}, DNS: {dns}, Śr.pozycja: {round(avg_pos,2)}")
            embed.add_field(name=f"{i}. {nick}", value=value, inline=False)

    else:  # teams view
        embed = discord.Embed(title="🏁 Tabela Drużyn", color=discord.Color.green())
        teams = {}
        for d in drivers:
            user_id, races, points, wins, podiums, dnf, dns, avg_pos, team_name = d
            member = interaction.guild.get_member(user_id)
            nick = member.display_name if member else f"Nieobecny ({user_id})"
            team_name = team_name if team_name and team_name != 'N/A' else 'N/A'

            if team_name not in teams:
                teams[team_name] = {"members": [], "total_points": 0}

            teams[team_name]["members"].append({
                "nick": nick,
                "points": points,
                "races": races,
                "dnf": dnf,
                "dns": dns
            })
            if team_name != 'N/A':
                teams[team_name]["total_points"] += points

        # sortowanie drużyn po punktach malejąco, N/A na końcu
        sorted_teams = sorted(teams.items(), key=lambda x: (-x[1]["total_points"], x[0]=='N/A'))

        for team_name, team_data in sorted_teams:
            members = sorted(team_data["members"], key=lambda x: x["points"], reverse=True)
            value = ""
            for i, m in enumerate(members, start=1):
                trophy = " 🏆" if i == 1 else ""
                line = f"{i}. {m['nick']}{trophy}: {m['points']} pkt, W {m['races']} wyścigach, DNF {m['dnf']}, DNS {m['dns']}\n"
                if len(value) + len(line) > MAX_FIELD_LENGTH:
                    embed.add_field(name=f"{team_name} ({team_data['total_points']} pkt)", value=value, inline=False)
                    value = ""
                value += line
            if value:
                embed.add_field(name=f"{team_name} ({team_data['total_points']} pkt)", value=value, inline=False)

    await interaction.response.send_message(embed=embed)


# ----------------- /update_team -----------------
@tree.command(name="update_team", description="Ustaw drużynę zawodnika (team1)")
@app_commands.describe(member="Zawodnik", team="Nazwa drużyny")
async def update_team(interaction: discord.Interaction, member: discord.Member, team: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Brak uprawnień ❌", ephemeral=True)
        return

    team = team.strip() if team else 'N/A'
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO driver_stats(user_id)
                VALUES (%s)
                ON CONFLICT (user_id) DO NOTHING
            """, (member.id,))
            cur.execute("""
                UPDATE driver_stats
                SET team1 = %s
                WHERE user_id = %s
            """, (team, member.id))
            conn.commit()

    await interaction.response.send_message(f"Ustawiono drużynę **{team}** dla {member.display_name} ✅", ephemeral=True)

# ================= RACE & GRID =================

from discord import app_commands
import datetime

# ----------------- /starting_grid -----------------
@tree.command(name="starting_grid", description="Ustaw starting grid wyścigu")
@app_commands.describe(track="Nazwa toru", results="Lista zawodników i czasów w formacie: @gracz 1:23.456 | @gracz 2 1:24.000")
async def starting_grid(interaction: discord.Interaction, track:str, results:str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Brak uprawnień ❌", ephemeral=True)
        return

    # Parsowanie wyników
    rows = [r.strip() for r in results.split("|") if r.strip()]
    grid = []
    for r in rows:
        parts = r.split()
        member = interaction.guild.get_member(int(parts[0].replace("<@","").replace(">","")))
        time = parts[1]
        if member:
            grid.append((member, time))
    
    # Sortowanie po czasie (domyślnie zakładamy, że podajesz w kolejności)
    embed = discord.Embed(title=f"🏁 Starting Grid: {track}", color=discord.Color.orange())
    for i, (member, time) in enumerate(grid, start=1):
        embed.add_field(name=f"{i}. {member.display_name}", value=f"Czas: {time}", inline=False)

    await interaction.response.send_message(embed=embed)

# ----------------- /ending_grid -----------------
@tree.command(name="ending_grid", description="Zapisz wyniki wyścigu i zaktualizuj statystyki")
@app_commands.describe(track="Nazwa toru", results="Lista zawodników i miejsc w formacie: @gracz 1 | @gracz 2")
async def ending_grid(interaction: discord.Interaction, track:str, results:str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Brak uprawnień ❌", ephemeral=True)
        return

    rows = [r.strip() for r in results.split("|") if r.strip()]
    grid = []
    for r in rows:
        member = interaction.guild.get_member(int(r.replace("<@","").replace(">","")))
        if member:
            grid.append(member)

    embed = discord.Embed(title=f"🏆 Wyniki wyścigu: {track}", color=discord.Color.gold())
    for i, member in enumerate(grid, start=1):
        embed.add_field(name=f"{i}. {member.display_name}", value=f"Miejsce: {i}", inline=False)
        # Aktualizacja statystyk zawodnika
        points = max(len(grid) - i, 0)  # np. prosty system punktów malejąco
        update_driver(member.id, pos=i, points=points)

    # Aktualizacja statystyki serwera
    update_server(races=1, points=sum(max(len(grid)-i,0) for i in range(len(grid))), last_best_team=None)

    await interaction.response.send_message(embed=embed)

# ----------------- /podium -----------------
@tree.command(name="podium", description="Pokaż podium wyścigu z awatarami")
@app_commands.describe(first="1. miejsce", second="2. miejsce", third="3. miejsce")
async def podium(interaction: discord.Interaction, first:discord.Member, second:discord.Member, third:discord.Member):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Brak uprawnień ❌", ephemeral=True)
        return

    embed = discord.Embed(title="🥇 Podium Wyścigu 🏆", color=discord.Color.gold())
    embed.add_field(name="🥇 1. miejsce", value=first.display_name, inline=True)
    embed.add_field(name="🥈 2. miejsce", value=second.display_name, inline=True)
    embed.add_field(name="🥉 3. miejsce", value=third.display_name, inline=True)
    embed.set_thumbnail(url=first.avatar.url if first.avatar else None)
    await interaction.response.send_message(embed=embed)

# ----------------- /race_add -----------------
@tree.command(name="race_add", description="Dodaj wyścig i zaktualizuj statystyki zawodników")
@app_commands.describe(track="Nazwa toru", results="Lista zawodników i miejsc w formacie: @gracz 1 | @gracz 2")
async def race_add(interaction: discord.Interaction, track:str, results:str):
    await ending_grid(interaction, track, results)
    await interaction.followup.send("Wyścig dodany ✅")

# ----------------- /season_reset -----------------
@tree.command(name="season_reset", description="Reset sezonu - statystyki serwera i zawodników")
async def season_reset(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Brak uprawnień ❌", ephemeral=True)
        return

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE driver_stats SET races=0, points=0, wins=0, podiums=0, dnf=0, dns=0, avg_position=0")
            cur.execute("UPDATE server_stats SET races=0, total_points=0, total_dnf=0, total_dns=0, last_mvp=NULL, last_best_team=NULL")
            conn.commit()

    await interaction.response.send_message("Sezon zresetowany ✅", ephemeral=True)


# ================= MVP VOTE =================
@tree.command(name="mvp_vote", description="Głosowanie na zawodnika dnia")
@app_commands.describe(candidates="Pinguj zawodników (max 20) oddzielając spacją)")
async def mvp_vote(interaction: discord.Interaction, *, candidates:str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Brak uprawnień ❌", ephemeral=True)
        return
    mentions = [s.strip() for s in candidates.split()][:20]
    content = "@everyone\nGłosowanie na MVP dnia:\n"
    reactions = []
    for i,m in enumerate(mentions):
        content += f"{i+1} - {m}\n"
        reactions.append(str(i+1)+"️⃣")
    msg = await interaction.channel.send(content)
    for r in reactions:
        await msg.add_reaction(r)
    await interaction.response.send_message("Głosowanie uruchomione ✅", ephemeral=True)
    await asyncio.sleep(1200)  # 20 minut
    msg = await interaction.channel.fetch_message(msg.id)
    counts = {}
    for i,r in enumerate(reactions):
        for react in msg.reactions:
            if str(react.emoji)==r:
                counts[i+1] = react.count-1
    res_text = "Wyniki MVP dnia:\n"
    for i,m in enumerate(mentions):
        res_text += f"{i+1} - {m}: {counts.get(i+1,0)} głosów\n"
    await interaction.channel.send("@everyone\n"+res_text)

# ================= LINK ROBLOX =================
@tree.command(name="link_roblox", description="Połącz nick Discord z Roblox")
@app_commands.describe(roblox_nick="Nick w Roblox")
async def link_roblox(interaction: discord.Interaction, roblox_nick:str):
    try:
        await interaction.user.edit(nick=f"{interaction.user.name} ({roblox_nick})")
        await interaction.response.send_message(f"Połączono z Roblox: **{roblox_nick}** ✅", ephemeral=True)
    except:
        await interaction.response.send_message("Nie mogę zmienić nicku ❌ (brak uprawnień)", ephemeral=True)

# ================= START =================
init_db()
keep_alive()
bot.run(os.getenv("DISCORD_TOKEN"))











