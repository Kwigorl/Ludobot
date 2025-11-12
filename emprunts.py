import discord
from discord.ext import commands
from discord import app_commands
import os
from datetime import datetime, timedelta
import psycopg2

# --------------------------
# CONFIGURATION via variables d'environnement
# --------------------------
CANAL_ID = int(os.environ["CANAL_ID"])
ROLE_BUREAU_ID = int(os.environ["ROLE_BUREAU_ID"])

DB_HOST = os.environ["DB_HOST"]
DB_PORT = os.environ["DB_PORT"]
DB_NAME = os.environ["DB_NAME"]
DB_USER = os.environ["DB_USER"]
DB_PASSWORD = os.environ["DB_PASSWORD"]

# --------------------------
# CRÉNEAUX D'EMPRUNT
# --------------------------
CRENEAUX = [
    {"jour": i, "start": 0, "end": 24} for i in range(7)
]

# --------------------------
# FONCTIONS DB
# --------------------------
def get_conn():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )

def est_disponible():
    now = datetime.now()
    jour = now.weekday()
    heure = now.hour
    for creneau in CRENEAUX:
        if creneau["jour"] == jour and creneau["start"] <= heure < creneau["end"]:
            return True
    return False

def get_jeux():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, nom, emprunte, emprunteur, emprunteur_id, date_emprunt FROM jeux ORDER BY nom COLLATE NOCASE")
    jeux = cur.fetchall()
    cur.close()
    conn.close()
    return jeux

def format_liste(jeux):
    lines = []
    for idx, j in enumerate(jeux, start=1):
        if j[2]:  # emprunté
            start_date = j[5].strftime("%d/%m") if j[5] else "??/??"
            end_date = (j[5] + timedelta(days=14)).strftime("%d/%m") if j[5] else "??/??"
            if j[4]:
                lines.append(f"> **{idx}.** {j[1]} *(emprunté par <@{j[4]}> du {start_date} au {end_date})*")
            else:
                lines.append(f"> **{idx}.** {j[1]} *(emprunté par {j[3]} du {start_date} au {end_date})*")
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
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM jeux WHERE emprunteur_id=%s", (user_id,))
    result = cur.fetchone()[0] > 0
    cur.close()
    conn.close()
    return result

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

        now = datetime.now()
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "UPDATE jeux SET emprunte=TRUE, emprunteur=%s, emprunteur_id=%s, date_emprunt=%s WHERE id=%s",
            (display_name, user_id, now, j[0])
        )
        conn.commit()
        cur.close()
        conn.close()

        channel = self.bot.get_channel(CANAL_ID)
        await self.update_message(channel)
        await interaction.response.send_message(
            f"✅ Tu as emprunté {j[1]} du {now.strftime('%d/%m')} au {(now + timedelta(days=14)).strftime('%d/%m')}.",
            ephemeral=True
        )

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

        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "UPDATE jeux SET emprunte=FALSE, emprunteur=NULL, emprunteur_id=NULL, date_emprunt=NULL WHERE id=%s",
            (j[0],)
        )
        conn.commit()
        cur.close()
        conn.close()

        channel = self.bot.get_channel(CANAL_ID)
        await self.update_message(channel)
        await interaction.response.send_message(f"✅ Tu as rendu {j[1]}.", ephemeral=True)

    @app_commands.command(name="ajout", description="Ajoute un jeu (Bureau)")
    @app_commands.describe(jeu="Nom du jeu à ajouter")
    async def ajout(self, interaction: discord.Interaction, jeu: str):
        if ROLE_BUREAU_ID not in [r.id for r in interaction.user.roles]:
            await interaction.response.send_message("❌ Tu n'as pas la permission.", ephemeral=True)
            return

        conn = get_conn()
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO jeux(nom) VALUES(%s)", (jeu,))
            conn.commit()
        except psycopg2.errors.UniqueViolation:
            await interaction.response.send_message("❌ Ce jeu existe déjà.", ephemeral=True)
            cur.close()
            conn.close()
            return
        cur.close()
        conn.close()

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

        conn = get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM jeux WHERE id=%s", (j[0],))
        conn.commit()
        cur.close()
        conn.close()

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
