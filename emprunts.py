import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
from datetime import datetime
import os

# --------------------------
# CONFIGURATION via variables d'environnement
# --------------------------
CANAL_ID = int(os.environ["CANAL_ID"])             # ID du canal Discord
ROLE_BUREAU_ID = int(os.environ["ROLE_BUREAU_ID"]) # ID du rôle Bureau
DB_PATH = os.path.join("data", "jeux.db")         # chemin vers la base SQLite

# --------------------------
# CRÉNEAUX D'EMPRUNT
# --------------------------
CRENEAUX = [{"jour": i, "start": 0, "end": 24} for i in range(7)]

# --------------------------
# INITIALISATION DB
# --------------------------
os.makedirs("data", exist_ok=True)
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute('''
CREATE TABLE IF NOT EXISTS jeux (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT UNIQUE,
    emprunte INTEGER DEFAULT 0,
    emprunteur TEXT,
    date_emprunt TEXT
)
''')
conn.commit()

# --------------------------
# FONCTIONS UTILES
# --------------------------
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
    for idx, j in enumerate(jeux, start=1):
        status = "✅" if j[2] == 0 else "❌"
        detail = f" (emprunté par {j[3]} le {j[4]})" if j[2] else ""
        lines.append(f"**{idx}.** {status} {j[1]}{detail}")
    return "\n".join(lines)

def find_jeu(identifiant):
    c.execute("SELECT id, nom, emprunte, emprunteur, date_emprunt FROM jeux")
    jeux = c.fetchall()
    identifiant = str(identifiant).lower()
    # On compare avec le numéro affiché (index) ou le nom
    for idx, j in enumerate(jeux, start=1):
        if str(idx) == identifiant or identifiant in j[1].lower():
            return j
    return None

def nb_emprunts_utilisateur(user_name):
    c.execute("SELECT COUNT(*) FROM jeux WHERE emprunteur=?", (user_name,))
    return c.fetchone()[0]

# --------------------------
# COG
# --------------------------
class Emprunts(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # --- FONCTION DE MISE À JOUR DU MESSAGE ---
    async def update_message(self, channel):
        c.execute("SELECT id, nom, emprunte, emprunteur, date_emprunt FROM jeux")
        jeux = c.fetchall()
        msg = None
        async for m in channel.history(limit=50):
            if m.author == self.bot.user and m.pinned:
                msg = m
                break
        content = "🎲 **Jeux disponibles :**\n\n" + format_liste(jeux)
        if msg:
            await msg.edit(content=content)
        else:
            await channel.send(content)  # pas d'épinglage

    # --- COMMANDES SLASH ---
    @app_commands.command(name="emprunte", description="Emprunte un jeu")
    @app_commands.describe(jeu="Nom ou numéro du jeu")
    async def emprunte(self, interaction: discord.Interaction, jeu: str):
        if not est_disponible():
            await interaction.response.send_message("⏰ Service fermé pour le moment.", ephemeral=True)
            return

        emprunteur = interaction.user.display_name if hasattr(interaction.user, "display_name") else interaction.user.name
        if nb_emprunts_utilisateur(emprunteur) >= 1:
            await interaction.response.send_message("❌ Tu as déjà un jeu emprunté.", ephemeral=True)
            return

        j = find_jeu(jeu)
        if not j:
            await interaction.response.send_message("❌ Jeu introuvable.", ephemeral=True)
            return
        if j[2]:
            await interaction.response.send_message(f"❌ {j[1]} est déjà emprunté.", ephemeral=True)
            return

        now = datetime.now().strftime("%d/%m/%Y")
        c.execute(
            "UPDATE jeux SET emprunte=1, emprunteur=?, date_emprunt=? WHERE id=?",
            (emprunteur, now, j[0])
        )
        conn.commit()

        # Réponse immédiate à l'utilisateur
        await interaction.response.send_message(f"✅ Tu as emprunté {j[1]} le {now}.", ephemeral=True)

        # Puis mise à jour du message du canal
        channel = self.bot.get_channel(CANAL_ID)
        await self.update_message(channel)

    @app_commands.command(name="rend", description="Rend un jeu")
    @app_commands.describe(jeu="Nom ou numéro du jeu")
    async def rend(self, interaction: discord.Interaction, jeu: str):
        if not est_disponible():
            await interaction.response.send_message("⏰ Service fermé pour le moment.", ephemeral=True)
            return
        j = find_jeu(jeu)
        if not j:
            await interaction.response.send_message("❌ Jeu introuvable.", ephemeral=True)
            return
        if not j[2]:
            await interaction.response.send_message(f"❌ {j[1]} n’est pas emprunté.", ephemeral=True)
            return

        c.execute("UPDATE jeux SET emprunte=0, emprunteur=NULL, date_emprunt=NULL WHERE id=?", (j[0],))
        conn.commit()

        await interaction.response.send_message(f"✅ Tu as rendu {j[1]}.", ephemeral=True)

        channel = self.bot.get_channel(CANAL_ID)
        await self.update_message(channel)

    @app_commands.command(name="ajout", description="Ajoute un jeu (Bureau)")
    @app_commands.describe(jeu="Nom du jeu à ajouter")
    async def ajout(self, interaction: discord.Interaction, jeu: str):
        if ROLE_BUREAU_ID not in [r.id for r in interaction.user.roles]:
            await interaction.response.send_message("❌ Tu n'as pas la permission.", ephemeral=True)
            return
        try:
            c.execute("INSERT INTO jeux(nom) VALUES(?)", (jeu,))
            conn.commit()
        except sqlite3.IntegrityError:
            await interaction.response.send_message("❌ Ce jeu existe déjà.", ephemeral=True)
            return

        await interaction.response.send_message(f"✅ {jeu} ajouté.", ephemeral=True)

        channel = self.bot.get_channel(CANAL_ID)
        await self.update_message(channel)

    @app_commands.command(name="retire", description="Retire un jeu (Bureau)")
    @app_commands.describe(jeu="Nom ou numéro du jeu à retirer")
    async def retire(self, interaction: discord.Interaction, jeu: str):
        if ROLE_BUREAU_ID not in [r.id for r in interaction.user.roles]:
            await interaction.response.send_message("❌ Tu n'as pas la permission.", ephemeral=True)
            return
        j = find_jeu(jeu)
        if not j:
            await interaction.response.send_message("❌ Jeu introuvable.", ephemeral=True)
            return

        c.execute("DELETE FROM jeux WHERE id=?", (j[0],))
        conn.commit()

        await interaction.response.send_message(f"✅ {j[1]} retiré.", ephemeral=True)

        channel = self.bot.get_channel(CANAL_ID)
        await self.update_message(channel)

    @app_commands.command(name="liste", description="Met à jour la liste des jeux")
    async def liste(self, interaction: discord.Interaction):
        await interaction.response.send_message("✅ Liste mise à jour.", ephemeral=True)
        channel = self.bot.get_channel(CANAL_ID)
        await self.update_message(channel)

# --------------------------
# SETUP
# --------------------------
async def setup(bot):
    await bot.add_cog(Emprunts(bot))
