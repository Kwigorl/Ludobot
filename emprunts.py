import discord
from discord.ext import commands
from discord import app_commands
import os
from datetime import datetime, timedelta
from supabase import create_client, Client

# --------------------------
# CONFIGURATION via variables d'environnement
# --------------------------
CANAL_ID = int(os.environ["CANAL_ID"])
ROLE_BUREAU_ID = int(os.environ["ROLE_BUREAU_ID"])

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

# --------------------------
# INITIALISATION SUPABASE
# --------------------------
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --------------------------
# CRÉNEAUX D'EMPRUNT
# --------------------------
CRENEAUX = [{"jour": i, "start": 0, "end": 24} for i in range(7)]

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
    response = supabase.table("jeux").select("*").order("nom", ascending=True).execute()
    return response.data

def format_liste(jeux):
    lines = []
    for idx, j in enumerate(jeux, start=1):
        if j["emprunte"]:  # emprunté
            start_date = datetime.fromisoformat(j["date_emprunt"]).strftime("%d/%m") if j["date_emprunt"] else "??/??"
            end_date = (datetime.fromisoformat(j["date_emprunt"]) + timedelta(days=14)).strftime("%d/%m") if j["date_emprunt"] else "??/??"
            if j["emprunteur_id"]:
                lines.append(f"> **{idx}.** {j['nom']} *(emprunté par <@{j['emprunteur_id']}> du {start_date} au {end_date})*")
            else:
                lines.append(f"> **{idx}.** {j['nom']} *(emprunté par {j['emprunteur']} du {start_date} au {end_date})*")
        else:
            lines.append(f"> **{idx}.** {j['nom']}")
    return "\n".join(lines)

def find_jeu(user_input):
    jeux = get_jeux()
    if user_input.isdigit():
        idx = int(user_input) - 1
        if 0 <= idx < len(jeux):
            return jeux[idx]
    user_input = user_input.lower()
    for j in jeux:
        if user_input in j["nom"].lower():
            return j
    return None

def user_a_emprunt(user_id):
    response = supabase.table("jeux").select("*").eq("emprunteur_id", user_id).execute()
    return len(response.data) > 0

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
        if j["emprunte"]:
            await interaction.response.send_message(f"❌ {j['nom']} est déjà emprunté.", ephemeral=True)
            return

        now = datetime.now().isoformat()
        supabase.table("jeux").update({
            "emprunte": True,
            "emprunteur": display_name,
            "emprunteur_id": user_id,
            "date_emprunt": now
        }).eq("id", j["id"]).execute()

        channel = self.bot.get_channel(CANAL_ID)
        await self.update_message(channel)
        await interaction.response.send_message(
            f"✅ Tu as emprunté {j['nom']} du {datetime.fromisoformat(now).strftime('%d/%m')} au {(datetime.fromisoformat(now) + timedelta(days=14)).strftime('%d/%m')}.",
            ephemeral=True
        )

    @app_commands.command(name="retour", description="Rend un jeu")
    @app_commands.describe(jeu="Nom ou numéro du jeu")
    async def rend(self, interaction: discord.Interaction, jeu: str):
        j = find_jeu(jeu)
        if not j:
            await interaction.response.send_message("❌ Jeu introuvable.", ephemeral=True)
            return
        if not j["emprunte"]:
            await interaction.response.send_message(f"❌ {j['nom']} n’est pas emprunté.", ephemeral=True)
            return

        supabase.table("jeux").update({
            "emprunte": False,
            "emprunteur": None,
            "emprunteur_id": None,
            "date_emprunt": None
        }).eq("id", j["id"]).execute()

        channel = self.bot.get_channel(CANAL_ID)
        await self.update_message(channel)
        await interaction.response.send_message(f"✅ Tu as rendu {j['nom']}.", ephemeral=True)

    @app_commands.command(name="ajout", description="Ajoute un jeu (Bureau)")
    @app_commands.describe(jeu="Nom du jeu à ajouter")
    async def ajout(self, interaction: discord.Interaction, jeu: str):
        if ROLE_BUREAU_ID not in [r.id for r in interaction.user.roles]:
            await interaction.response.send_message("❌ Tu n'as pas la permission.", ephemeral=True)
            return

        supabase.table("jeux").insert({"nom": jeu}).execute()

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

        supabase.table("jeux").delete().eq("id", j["id"]).execute()

        channel = self.bot.get_channel(CANAL_ID)
        await self.update_message(channel)
        await interaction.response.send_message(f"✅ {j['nom']} retiré.", ephemeral=True)

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
