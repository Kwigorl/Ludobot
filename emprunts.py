import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
from datetime import datetime
import os

# --------------------------
# CONFIGURATION via variables d'environnement
# --------------------------
CANAL_ID = int(os.environ["CANAL_ID"])
ROLE_BUREAU_ID = int(os.environ["ROLE_BUREAU_ID"])
DB_PATH = os.path.join("data", "jeux.db")

# --------------------------
# CRÉNEAUX D'EMPRUNT
# --------------------------
CRENEAUX = [
    {"jour": 0, "start": 0, "end": 24},
    {"jour": 1, "start": 0, "end": 24},
    {"jour": 2, "start": 0, "end": 24},
    {"jour": 3, "start": 0, "end": 24},
    {"jour": 4, "start": 0, "end": 24},
    {"jour": 5, "start": 0, "end": 24},
    {"jour": 6, "start": 0, "end": 24},
]

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
    emprunteur_id INTEGER,
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

def get_jeux():
    c.execute("SELECT id, nom, emprunte, emprunteur, emprunteur_id, date_emprunt FROM jeux ORDER BY nom COLLATE NOCASE")
    return c.fetchall()

def format_liste(jeux):
    lines = []
    for idx, j in enumerate(jeux, start=1):
        if j[2]:  # emprunté
            # si on a un ID utilisateur, on l’affiche comme mention Discord
            if j[4]:
                lines.append(f"> **{idx}.** {j[1]} *(emprunté par <@{j[4]}> le {j[5]})*")
            else:
                lines.append(f"> **{idx}.** {j[1]} *(emprunté par {j[3]} le {j[5]})*")
        else:  # disponible
            lines.append(f"> **{idx}.** {j[1]}")
    return "\n".join(lines)

def find_jeu(user_input):
    jeux = get_jeux()
    if user_input.isdigit():
        idx = int(user_input) - 1
        if 0 <= idx < len(jeux):
            return jeux[idx]
    user_input = user_input.lower()
    for j in jeux:
        if user_input in j[1].lower():
            return j
    return None

def user_a_emprunt(user_id):
    c.execute("SELECT COUNT(*) FROM jeux WHERE emprunteur_id=?", (user_id,))
    return c.fetchone()[0] > 0

# --------------------------
# COG
# --------------------------
class Emprunts(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def update_message(self, channel):
        jeux = get_jeux()
        content = (
            "\n"
            "😊 Vous souhaitez repartir d'une séance avec un jeu de l'asso ?\n\n"
            "📆 Vous pouvez en emprunter 1 par utilisateur·rice Discord, pendant 2 semaines.\n\n"
            "📤 Quand vous l'empruntez : tapez ici `/emprunt [numéro du jeu]` (ex : `/emprunt 3`).\n"
            "📥 Quand vous le retournez : tapez ici `/retour [numéro du jeu]` (ex : `/retour 3`).\n\n"
            "🎲 Jeux disponibles :\n\n"
            + format_liste(jeux)
        )

        msg = None
        async for m in channel.history(limit=50):
            if m.author == self.bot.user:
                msg = m
                break
        if msg:
            await msg.edit(content=content)
        else:
            await channel.send(content)

    # --- Commandes ---
    @app_commands.command(name="emprunt", description="Emprunte un jeu")
    @app_commands.describe(jeu="Nom ou numéro du jeu")
    async def emprunte(self, interaction: discord.Interaction, jeu: str):
        if not est_disponible():
            await interaction.response.send_message("⏰ Service fermé pour le moment.", ephemeral=True)
            return

        user_id = interaction.user.id
        display_name = interaction.user.display_name

        if user_a_emprunt(user_id):
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
            "UPDATE jeux SET emprunte=1, emprunteur=?, emprunteur_id=?, date_emprunt=? WHERE id=?",
            (display_name, user_id, now, j[0])
        )
        conn.commit()

        channel = self.bot.get_channel(CANAL_ID)
        await self.update_message(channel)
        await interaction.response.send_message(f"✅ Tu as emprunté {j[1]} le {now}.", ephemeral=True)

    @app_commands.command(name="retour", description="Rend un jeu")
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

        c.execute("UPDATE jeux SET emprunte=0, emprunteur=NULL, emprunteur_id=NULL, date_emprunt=NULL WHERE id=?", (j[0],))
        conn.commit()

        channel = self.bot.get_channel(CANAL_ID)
        await self.update_message(channel)
        await interaction.response.send_message(f"✅ Tu as rendu {j[1]}.", ephemeral=True)

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

        channel = self.bot.get_channel(CANAL_ID)
        await self.update_message(channel)
        await interaction.response.send_message(f"✅ {jeu} ajouté.", ephemeral=True)

    @app_commands.command(name="retrait", description="Retire un jeu (Bureau)")
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

        channel = self.bot.get_channel(CANAL_ID)
        await self.update_message(channel)
        await interaction.response.send_message(f"✅ {j[1]} retiré.", ephemeral=True)

    @app_commands.command(name="liste", description="Met à jour la liste des jeux")
    async def liste(self, interaction: discord.Interaction):
        channel = self.bot.get_channel(CANAL_ID)
        await self.update_message(channel)
        await interaction.response.send_message("✅ Liste mise à jour.", ephemeral=True)


# --------------------------
# SETUP
# --------------------------
async def setup(bot):
    await bot.add_cog(Emprunts(bot))
