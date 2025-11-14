import discord
from discord.ext import commands
from discord import app_commands
import os
from datetime import datetime, timedelta
from supabase import create_client

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
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

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
    response = supabase.table("jeux").select("*").order("nom", desc=False).execute()
    return response.data

def format_liste(jeux, filtre=None):
    """
    jeux : liste complète
    filtre : None pour tous, True pour empruntés, False pour disponibles
    """
    lines = []
    for idx, j in enumerate(jeux, start=1):
        if filtre is not None and j["emprunte"] != filtre:
            continue

        if j["emprunte"]:
            start_date = datetime.fromisoformat(j["date_emprunt"]).strftime("%d/%m") if j["date_emprunt"] else "??/??"
            end_date = (datetime.fromisoformat(j["date_emprunt"]) + timedelta(days=14)).strftime("%d/%m") if j["date_emprunt"] else "??/??"
            emprunteur_tag = f"<@{j['emprunteur_id']}>" if j["emprunteur_id"] else j["emprunteur"]
            lines.append(f"**{idx}.** {j['nom']} ({emprunteur_tag} du {start_date} au {end_date})")
        else:
            lines.append(f"**{idx}.** {j['nom']}")
    return "\n".join(lines) if lines else "Aucun"

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

    # --------------------------
    # UPDATE MESSAGE
    # --------------------------
    async def update_message(self, channel):
        jeux = get_jeux()

        text_info = (
                "**Emprunts de jeux** \n\n"
                "😊 Vous souhaitez repartir d'une séance avec un jeu de l'asso ?\n\n"
                "📆 Vous pouvez en emprunter **1** par utilisateur·rice Discord, pendant **2 semaines**.\n\n"
                "📤 Pour emprunter : `/emprunt [numéro]` (ex : `/emprunt 3`).\n"
                "📥 Pour retourner : `/retour [numéro]` (ex : `/retour 3`)."
        )

        embed_dispo = discord.Embed(
            title="✅ Jeux disponibles",
            description=format_liste(jeux, filtre=False),
            color=discord.Color.green()
        )

        embed_empruntes = discord.Embed(
            title="❌ Jeux empruntés",
            description=format_liste(jeux, filtre=True),
            color=discord.Color.red()
        )

        # Cherche un message déjà envoyé par le bot
        msg = None
        async for m in channel.history(limit=50):
            if m.author == self.bot.user:
                msg = m
                break

        # Édite ou envoie
        if msg:
            await msg.edit(embeds=[embed_info, embed_dispo, embed_empruntes])
        else:
            await channel.send(embeds=[embed_info, embed_dispo, embed_empruntes])

    # --------------------------
    # COMMANDES
    # --------------------------
    @app_commands.command(name="emprunt", description="Emprunte un jeu")
    @app_commands.describe(jeu="Nom ou numéro du jeu")
    async def emprunte(self, interaction: discord.Interaction, jeu: str):
        await interaction.response.defer(ephemeral=True)

        if not est_disponible():
            await interaction.followup.send("⏰ Service fermé pour le moment.", ephemeral=True)
            return

        user_id = interaction.user.id
        display_name = interaction.user.display_name

        if user_a_emprunt(user_id):
            response = supabase.table("jeux").select("*").eq("emprunteur_id", user_id).execute()
            jeu_emprunte = response.data[0] if response.data else None

            if jeu_emprunte:
                jeux = get_jeux()
                numero = next((i+1 for i, j in enumerate(jeux) if j["id"] == jeu_emprunte["id"]), "?")
                await interaction.followup.send(
                    f"❌ Tu as déjà emprunté **{jeu_emprunte['nom']}** (jeu n°**{numero}**).",
                    ephemeral=True
                )
            else:
                await interaction.followup.send("❌ Tu as déjà un jeu emprunté.", ephemeral=True)
            return

        j = find_jeu(jeu)
        if not j:
            await interaction.followup.send("❌ Jeu introuvable.", ephemeral=True)
            return
        if j["emprunte"]:
            await interaction.followup.send(f"❌ **{j['nom']}** est déjà emprunté.", ephemeral=True)
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
        await interaction.followup.send(
            f"✅ Tu as emprunté **{j['nom']}**. Date de retour max : {(datetime.fromisoformat(now) + timedelta(days=14)).strftime('%d/%m')}.",
            ephemeral=True
        )

    @app_commands.command(name="retour", description="Rend un jeu que tu as emprunté")
    @app_commands.describe(jeu="Nom ou numéro du jeu")
    async def rend(self, interaction: discord.Interaction, jeu: str):
        await interaction.response.defer(ephemeral=True)

        j = find_jeu(jeu)
        if not j:
            await interaction.followup.send("❌ Jeu introuvable.", ephemeral=True)
            return
        if not j["emprunte"]:
            await interaction.followup.send(f"❌ {j['nom']} n’est pas emprunté.", ephemeral=True)
            return

        if j["emprunteur_id"] != interaction.user.id:
            emprunteur_tag = f"<@{j['emprunteur_id']}>" if j["emprunteur_id"] else j["emprunteur"]
            await interaction.followup.send(
                f"❌ **{j['nom']}** est emprunté par {emprunteur_tag}, tu ne peux pas le retourner.",
                ephemeral=True
            )
            return

        supabase.table("jeux").update({
            "emprunte": False,
            "emprunteur": None,
            "emprunteur_id": None,
            "date_emprunt": None
        }).eq("id", j["id"]).execute()

        channel = self.bot.get_channel(CANAL_ID)
        await self.update_message(channel)
        await interaction.followup.send(f"✅ Tu as retourné **{j['nom']}**.", ephemeral=True)

    @app_commands.command(name="ajout", description="Ajoute un jeu (Bureau)")
    @app_commands.describe(jeu="Nom du jeu à ajouter")
    async def ajout(self, interaction: discord.Interaction, jeu: str):
        await interaction.response.defer(ephemeral=True)

        if ROLE_BUREAU_ID not in [r.id for r in interaction.user.roles]:
            await interaction.followup.send("❌ Tu n'as pas la permission.", ephemeral=True)
            return

        supabase.table("jeux").insert({"nom": jeu}).execute()

        channel = self.bot.get_channel(CANAL_ID)
        await self.update_message(channel)
        await interaction.followup.send(f"✅ {jeu} ajouté.", ephemeral=True)

    @app_commands.command(name="retrait", description="Retire un jeu (Bureau)")
    @app_commands.describe(jeu="Nom ou numéro du jeu à retirer")
    async def retire(self, interaction: discord.Interaction, jeu: str):
        await interaction.response.defer(ephemeral=True)

        if ROLE_BUREAU_ID not in [r.id for r in interaction.user.roles]:
            await interaction.followup.send("❌ Tu n'as pas la permission.", ephemeral=True)
            return

        j = find_jeu(jeu)
        if not j:
            await interaction.followup.send("❌ Jeu introuvable.", ephemeral=True)
            return

        supabase.table("jeux").delete().eq("id", j["id"]).execute()

        channel = self.bot.get_channel(CANAL_ID)
        await self.update_message(channel)
        await interaction.followup.send(f"✅ {j['nom']} retiré.", ephemeral=True)

    @app_commands.command(name="liste", description="Met à jour la liste des jeux")
    async def liste(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        channel = self.bot.get_channel(CANAL_ID)
        await self.update_message(channel)
        await interaction.followup.send("✅ Liste mise à jour.", ephemeral=True)

# --------------------------
# SETUP
# --------------------------
async def setup(bot):
    await bot.add_cog(Emprunts(bot))
