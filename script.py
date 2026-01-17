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
            cur.execute("""ALTER TABLE driver_stats ADD COLUMN IF NOT EXISTS team1 TEXT DEFAULT 'N/A';
            """)
            cur.execute("""CREATE TABLE IF NOT EXISTS race_starting_grid (
            track TEXT NOT NULL,
            user_id BIGINT NOT NULL,
            start_pos INTEGER,
             time REAL,
             PRIMARY KEY(track, user_id)
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
def update_server(races=0, dnf=0, dns=0, points=0, mvp=None, team=None):
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
            """, (races, dnf, dns, points, mvp, team))
            conn.commit()

@tree.command(name="server_stats", description="Statystyki ligi")
async def server_stats(interaction: discord.Interaction):
    with get_conn() as conn:
        with conn.cursor() as cur:
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
def update_driver_logic(user_id, pos=None, points=0, dnf=False, dns=False):
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
            """, (points, 1 if pos==1 else 0, 1 if pos and pos<=3 else 0,
                  1 if dnf else 0, 1 if dns else 0, pos or 0, user_id))
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

@tree.command(name="update_driver", description="Dodaj punkty do zawodnika")
@app_commands.describe(user="Zawodnik", points="Dodaj punkty", pos="Pozycja", dnf="DNF?", dns="DNS?")
async def update_driver(interaction: discord.Interaction, user:discord.Member, points:int, pos:int=None, dnf:bool=False, dns:bool=False):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Brak uprawnień ❌", ephemeral=True)
        return
    update_driver_logic(user.id, pos=pos, points=points, dnf=dnf, dns=dns)
    await interaction.response.send_message(f"Dodano **{points} pkt** do {user.display_name} ✅", ephemeral=True)

# ================= LIGA TABLE =================
@tree.command(name="liga_table", description="Tabela ligi - wybierz widok")
@app_commands.describe(view="Kierowcy / Drużyny")
@app_commands.choices(view=[app_commands.Choice(name="Kierowcy", value="drivers"),
                             app_commands.Choice(name="Drużyny", value="teams")])
async def liga_table(interaction: discord.Interaction, view: app_commands.Choice[str]):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id, races, points, wins, podiums, dnf, dns, avg_position, team1 FROM driver_stats ORDER BY points DESC")
            drivers = cur.fetchall()
    if not drivers:
        await interaction.response.send_message("Brak danych ❌", ephemeral=True)
        return
    if view.value == "drivers":
        embed = discord.Embed(title="🏎️ Tabela Kierowców", color=discord.Color.blue())
        for i,d in enumerate(drivers,start=1):
            uid,races,points,wins,podiums,dnf,dns,avg,team = d
            member = interaction.guild.get_member(uid)
            nick = member.display_name if member else f"Nieobecny ({uid})"
            team = team if team and team != "N/A" else "N/A"
            value = f"Drużyna: {team}\nWyścigi: {races}, Punkty: {points}, Zwycięstwa: {wins}, Podia: {podiums}, DNF: {dnf}, DNS: {dns}, Śr.pozycja: {round(avg,2)}"
            embed.add_field(name=f"{i}. {nick}", value=value, inline=False)
    else:
        embed = discord.Embed(title="🏁 Tabela Drużyn", color=discord.Color.green())
        teams = {}
        for d in drivers:
            uid,races,points,wins,podiums,dnf,dns,avg,team = d
            member = interaction.guild.get_member(uid)
            nick = member.display_name if member else f"Nieobecny ({uid})"
            team = team if team and team != "N/A" else "N/A"
            if team not in teams:
                teams[team] = {"members":[], "points":0}
            teams[team]["members"].append({"nick":nick,"points":points,"races":races,"dnf":dnf,"dns":dns})
            if team!="N/A":
                teams[team]["points"]+=points
        sorted_teams = sorted(teams.items(), key=lambda x:(-x[1]["points"], x[0]=="N/A"))
        for team_name,data in sorted_teams:
            members = sorted(data["members"], key=lambda x:x["points"], reverse=True)
            value=""
            for i,m in enumerate(members,start=1):
                trophy=" 🏆" if i==1 else ""
                line=f"{i}. {m['nick']}{trophy}: {m['points']} pkt, W {m['races']} wyścigach, DNF {m['dnf']}, DNS {m['dns']}\n"
                if len(value)+len(line)>MAX_FIELD_LENGTH:
                    embed.add_field(name=f"{team_name} ({data['points']} pkt)", value=value, inline=False)
                    value=""
                value+=line
            if value:
                embed.add_field(name=f"{team_name} ({data['points']} pkt)", value=value, inline=False)
    await interaction.response.send_message(embed=embed)

# ================= UPDATE TEAM =================
@tree.command(name="update_team", description="Ustaw drużynę zawodnika")
@app_commands.describe(member="Zawodnik", team="Nazwa drużyny")
async def update_team(interaction: discord.Interaction, member: discord.Member, team: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Brak uprawnień ❌", ephemeral=True)
        return
    team = team.strip() if team else "N/A"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO driver_stats(user_id) VALUES(%s) ON CONFLICT DO NOTHING",(member.id,))
            cur.execute("UPDATE driver_stats SET team1=%s WHERE user_id=%s",(team,member.id))
            conn.commit()
    await interaction.response.send_message(f"Ustawiono drużynę **{team}** dla {member.display_name} ✅", ephemeral=True)

# ================= STARTING GRID =================
@tree.command(name="starting_grid", description="Zapisz tabelę startową")
@app_commands.describe(track="Nazwa toru", times="@gracz czas | @gracz czas ...")
async def starting_grid(interaction: discord.Interaction, track:str, times:str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Brak uprawnień ❌", ephemeral=True)
        return
    rows=[r.strip() for r in times.split("|") if r.strip()]
    grid=[]
    for r in rows:
        try:
            mention,time=r.split()
            member=interaction.guild.get_member(int(mention.replace("<@","").replace(">","")))
            grid.append({"member":member,"time":float(time.replace(",","."))})
        except: continue
    if not grid:
        await interaction.response.send_message("Niepoprawny format danych ❌", ephemeral=True)
        return
    grid.sort(key=lambda x:x["time"])
    with get_conn() as conn:
        with conn.cursor() as cur:
            for pos,entry in enumerate(grid,start=1):
                cur.execute("INSERT INTO race_starting_grid(track,user_id,start_pos,time) VALUES(%s,%s,%s,%s) ON CONFLICT(track,user_id) DO UPDATE SET start_pos=EXCLUDED.start_pos,time=EXCLUDED.time",(track,entry["member"].id,pos,entry["time"]))
            conn.commit()
    embed=discord.Embed(title=f"🏁 Starting Grid: {track}",color=discord.Color.blue())
    for i,entry in enumerate(grid,start=1):
        embed.add_field(name=f"{i}. {entry['member'].display_name}",value=f"Czas: {entry['time']}",inline=False)
    await interaction.response.send_message(embed=embed)

# ================= ENDING GRID =================
# ================= LOGIKA WYŚCIGU =================
async def process_race_results(interaction, track: str, results: str):
    # Parsowanie wyników z opcjonalnym DNF/DNS
    rows = [r.strip() for r in results.split("|") if r.strip()]
    final_grid = []

    for r in rows:
        try:
            mention, result = r.split()
            member = interaction.guild.get_member(int(mention.replace("<@","").replace(">","")))
            if not member:
                continue
            result = result.upper()
            if result == "DNF":
                pos = None
                points = 0
                dnf = True
                dns = False
            elif result == "DNS":
                pos = None
                points = 0
                dnf = False
                dns = True
            else:
                pos = int(result)
                points = max(len(rows) - pos, 0)
                dnf = False
                dns = False
            final_grid.append({"member": member, "pos": pos, "points": points, "dnf": dnf, "dns": dns})
        except:
            continue

    if not final_grid:
        await interaction.response.send_message("Niepoprawny format danych ❌", ephemeral=True)
        return None

    # Pobranie pozycji startowych
    start_pos = {}
    with get_conn() as conn:
        with conn.cursor() as cur:
            for entry in final_grid:
                cur.execute("SELECT start_pos FROM race_starting_grid WHERE track=%s AND user_id=%s",
                            (track, entry["member"].id))
                r = cur.fetchone()
                start_pos[entry["member"].id] = r[0] if r else None

    # Tworzenie embedu wyników
    embed = discord.Embed(title=f"🏆 Wyniki wyścigu: {track}", color=discord.Color.gold())
    total_points = 0
    for entry in final_grid:
        member = entry["member"]
        pos = entry["pos"]
        points = entry["points"]
        dnf = entry["dnf"]
        dns = entry["dns"]

        total_points += points
        update_driver_logic(member.id, pos=pos, points=points, dnf=dnf, dns=dns)

        sp = start_pos.get(member.id)
        if sp:
            delta = f"{'+' if sp - (pos or sp) > 0 else ''}{(sp - (pos or sp))} miejsc" if pos else "—"
        else:
            delta = "—"

        status = "DNF" if dnf else "DNS" if dns else f"Punkty: {points}"
        embed.add_field(name=f"{pos or '—'}. {member.display_name}", value=f"{status}, Przesunięcie: {delta}", inline=False)

    # Aktualizacja statystyki serwera
    update_server(races=1, points=total_points)
    return embed

# ================= ENDING GRID =================
@tree.command(name="ending_grid", description="Zapisz wyniki i pokaż przesunięcia")
@app_commands.describe(track="Nazwa toru", results="@gracz miejsce/DNF/DNS | ...")
async def ending_grid(interaction: discord.Interaction, track:str, results:str):
    embed = await process_race_results(interaction, track, results)
    if embed:
        await interaction.response.send_message(embed=embed)

# ================= RACE ADD =================
@tree.command(name="race_add", description="Dodaj wyścig i zaktualizuj statystyki zawodników")
@app_commands.describe(track="Nazwa toru", results="@gracz miejsce/DNF/DNS | ...")
async def race_add(interaction: discord.Interaction, track:str, results:str):
    embed = await process_race_results(interaction, track, results)
    if embed:
        await interaction.response.send_message(embed=embed)
        await interaction.followup.send("Wyścig dodany ✅")


# ================= PODIUM =================
@tree.command(name="podium", description="Wyświetl podium wybranych zawodników")
@app_commands.describe(drivers="@gracz | @gracz | @gracz")
async def podium(interaction: discord.Interaction, drivers:str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Brak uprawnień ❌", ephemeral=True)
        return
    mentions=[d.strip() for d in drivers.split("|") if d.strip()]
    members=[]
    for m in mentions:
        try: members.append(interaction.guild.get_member(int(m.replace("<@","").replace(">",""))))
        except: continue
    embed=discord.Embed(title="🏆 Podium", color=discord.Color.gold())
    for i,member in enumerate(members,start=1):
        embed.add_field(name=f"{i}. {member.display_name}", value=" ", inline=True)
        embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
    await interaction.response.send_message(embed=embed)

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













