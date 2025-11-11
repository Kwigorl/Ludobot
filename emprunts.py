import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
from datetime import datetime
import os

CANAL_ID = int(os.environ["CANAL_ID"])
ROLE_BUREAU_ID = int(os.environ["ROLE_BUREAU_ID"])
DB_PATH = os.path.join("data", "jeux.db")

os.makedirs("data", exist_ok=True)
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS jeux (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT UNIQUE,
    emprunte INTEGER DEFAULT 0,
    emprunteur TEXT,
    date_emprunt TEXT
)
""")
conn.commit()

# Créneaux d'emprunt
CRENEAUX = [
    {"jour": 2, "start": 0, "end": 24},
    {"jour": 4, "start": 0, "end": 24},
    {"jour": 6, "start": 0, "end": 24},
    {"jour": 1, "start": 0, "end": 24},
    {"jour": 3, "start": 0, "end": 24},
    {"jour": 5, "start": 0, "end": 24},
    {"jour": 0, "start": 0, "end": 24},
]

def est_disponible():
    now = datetime.now()
    jour = now.weekday()
    heure = now.hour
    for creneau in CRENEAUX:
        if creneau["jour"] == jour and creneau["start"] <= heure < creneau["end"]:
            return True
    return False

def format_liste(jeux):
    lines = []
    for j in jeux:
        status = "✅" if j[2] == 0 else "❌"
        detail = f" (emprunté par {j[3]} le {j[4]})" if j[2] else ""
        lines.append(f"**{j[0]}.** {status} {j[1]}{detail}")
    return "\n".join(lines)

class Emprunts(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def update_message(self, channel):
        c.execute("SELECT id, nom, emprunte, emprunteur, date_emprunt FROM jeux")
        jeux = c.fetchall()

        msg = None
        async for m in channel.history(limit=50):
            if m.author == self.bot.user and m.pinned:
                msg = m
                break

        intro = "🎲 **Jeux disponibles :**\nUtilisez /emprunte ou /rend pour gérer les jeux.\n\n"
        content = intro + format_liste(jeux)

        if msg:
            await msg.edit(content=content)
        else:
            new_msg = await channel.send(content)
            await new_msg.pin()

    # --------------------------
    # COMMANDES SLASH
    # --------------------------
    @app_commands.command(name="emprunte", description="Emprunte un jeu")
    @app_commands.describe(jeu="Nom ou numéro du jeu")
    async def emprunte(self, interaction: discord.Interaction, jeu: str):
        if not est_disponible():
            await interaction.response.send_message("⏰ Service fermé pour le moment.", ephemeral=True)
            return
        c.execute("SELECT id, nom, emprunte FROM jeux")
        jeux = c.fetchall()
        identifiant = str(jeu).lower()
        j = next((x for x in jeux if str(x[0])==identifiant or identifiant in x[1].lower()), None)
        if not j:
            await interaction.response.send_message("❌ Jeu introuvable.", ephemeral=True)
            return
        if j[2]:
            await interaction.response.send_message(f"❌ {j[1]} est déjà emprunté.", ephemeral=True)
            return
        now = datetime.now().strftime("%d/%m/%Y")
        c.execute("UPDATE jeux SET emprunte=1, emprunteur=?, date_emprunt=? WHERE id=?", (interaction.user.name, now, j[0]))
        conn.commit()
        channel = self.bot.get_channel(CANAL_ID)
        await self.update_message(channel)
        await interaction.response.send_message(f"✅ Tu as emprunté {j[1]} le {now}.", ephemeral=True)

    @app_commands.command(name="rend", description="Rend un jeu")
    @app_commands.describe(jeu="Nom ou numéro du jeu")
    async def rend(self, interaction: discord.Interaction, jeu: str):
        c.execute("SELECT id, nom, emprunte FROM jeux")
        jeux = c.fetchall()
        identifiant = str(jeu).lower()
        j = next((x for x in jeux if str(x[0])==identifiant or identifiant in x[1].lower()), None)
        if not j:
            await interaction.response.send_message("❌ Jeu introuvable.", ephemeral=True)
            return
        if not j[2]:
            await interaction.response.send_message(f"❌ {j[1]} n’est pas emprunté.", ephemeral=True)
            return
        c.execute("UPDATE jeux SET emprunte=0, emprunteur=NULL, date_emprunt=NULL WHERE id=?", (j[0],))
        conn.commit()
        channel = self.bot.get_channel(CANAL_ID)
        await self.update_message(channel)
        await interaction.response.send_message(f"✅ Tu as rendu {j[1]}.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Emprunts(bot))
