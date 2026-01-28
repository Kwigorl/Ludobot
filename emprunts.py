import discord
from discord.ext import commands
from discord import app_commands
import os
from datetime import datetime, timedelta
from supabase import create_client
import pytz
import traceback
import asyncio

# --------------------------
# CONFIGURATION
# --------------------------
CANAL_ID = int(os.environ["CANAL_ID"])
ROLE_BUREAU_ID = int(os.environ["ROLE_BUREAU_ID"])

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

TIMEZONE = pytz.timezone("Europe/Paris")

# 0=Lundi ... 6=Dimanche
CRENEAUX = [
    {"jour": 2, "start": 15, "end": 24},  # Mercredi
    {"jour": 4, "start": 20, "end": 24},  # Vendredi
    {"jour": 6, "start": 14, "end": 18}   # Dimanche
]

# --------------------------
# OUTILS ASYNC
# --------------------------
async def run_db(func):
    return await asyncio.to_thread(func)

# --------------------------
# FONCTIONS UTILES
# --------------------------
def est_disponible():
    now = datetime.now(TIMEZONE)
    for c in CRENEAUX:
        if c["jour"] == now.weekday() and c["start"] <= now.hour < c["end"]:
            return True
    return False

def normaliser_texte(txt):
    accents = str.maketrans("éèêëàâäùûüôöîïç", "eeeeaaauuuooiic")
    return txt.lower().translate(accents)

def get_jeux_sync():
    return supabase.table("jeux").select("*").order("nom").execute().data

async def get_jeux():
    return await run_db(get_jeux_sync)

def format_liste(jeux, filtre=None):
    lines = []
    index_map = []

    for j in jeux:
        if filtre is not None and j["emprunte"] != filtre:
            continue
        index_map.append(j)

        if j["emprunte"]:
            start = datetime.fromisoformat(j["date_emprunt"]).strftime("%d/%m")
            end = (datetime.fromisoformat(j["date_emprunt"]) + timedelta(days=14)).strftime("%d/%m")
            emprunteur = f"<@{j['emprunteur_id']}>" if j["emprunteur_id"] else j["emprunteur"]
            lines.append(f"**{len(index_map)}.** {j['nom']} ({emprunteur} du {start} au {end})")
        else:
            lines.append(f"**{len(index_map)}.** {j['nom']}")

    return ("\n".join(lines) if lines else "Aucun"), index_map

def user_a_emprunt_sync(user_id):
    return bool(
        supabase.table("jeux")
        .select("id")
        .eq("emprunteur_id", user_id)
        .execute()
        .data
    )

async def user_a_emprunt(user_id):
    return await run_db(lambda: user_a_emprunt_sync(user_id))

def user_a_deja_emprunte_ce_jeu_sync(user_id, jeu_id):
    limite = datetime.now(TIMEZONE) - timedelta(days=30)
    response = supabase.table("historique_emprunts") \
        .select("*") \
        .eq("user_id", user_id) \
        .eq("jeu_id", jeu_id) \
        .execute()

    for e in response.data:
        d = TIMEZONE.localize(datetime.strptime(e["date_emprunt"], "%d/%m/%Y %H:%M"))
        if d >= limite:
            return True
    return False

async def user_a_deja_emprunte_ce_jeu(user_id, jeu_id):
    return await run_db(lambda: user_a_deja_emprunte_ce_jeu_sync(user_id, jeu_id))

# --------------------------
# COG
# --------------------------
class Emprunts(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def update_message(self, channel):
        try:
            jeux = await get_jeux()

            dispo_txt, _ = format_liste(jeux, False)
            emprunt_txt, _ = format_liste(jeux, True)

            content = (
                "## 🎲 Emprunts de jeux\n\n"
                "😊 Un jeu par personne, pour **2 semaines**.\n\n"
                "`/emprunt [numéro]`\n"
                "`/retour [numéro]`\n"
            )

            embeds = [
                discord.Embed(title="✅ Jeux disponibles", description=dispo_txt, color=discord.Color.green()),
                discord.Embed(title="❌ Jeux empruntés", description=emprunt_txt, color=discord.Color.red())
            ]

            async for m in channel.history(limit=20):
                if m.author == self.bot.user:
                    await m.edit(content=content, embeds=embeds)
                    return

            await channel.send(content=content, embeds=embeds)

        except Exception:
            traceback.print_exc()

    # --------------------------
    # /emprunt
    # --------------------------
    @app_commands.command(name="emprunt", description="Emprunte un jeu")
    async def emprunt(self, interaction: discord.Interaction, jeu: str):
        await interaction.response.defer(ephemeral=True)

        try:
            if not est_disponible():
                await interaction.followup.send("⏰ Service fermé.", ephemeral=True)
                return

            jeux = await get_jeux()
            dispo_txt, index_map = format_liste(jeux, False)

            if not jeu.isdigit() or not (1 <= int(jeu) <= len(index_map)):
                await interaction.followup.send("❌ Numéro invalide.", ephemeral=True)
                return

            j = index_map[int(jeu) - 1]

            if await user_a_emprunt(interaction.user.id):
                await interaction.followup.send("❌ Tu as déjà un jeu emprunté.", ephemeral=True)
                return

            if await user_a_deja_emprunte_ce_jeu(interaction.user.id, j["id"]):
                await interaction.followup.send("❌ Emprunt récent de ce jeu.", ephemeral=True)
                return

            now_iso = datetime.now().isoformat()

            await run_db(lambda: supabase.table("jeux").update({
                "emprunte": True,
                "emprunteur": interaction.user.display_name,
                "emprunteur_id": interaction.user.id,
                "date_emprunt": now_iso
            }).eq("id", j["id"]).execute())

            await self.update_message(self.bot.get_channel(CANAL_ID))

            await interaction.followup.send(
                f"✅ **{j['nom']}** emprunté (retour max {(datetime.fromisoformat(now_iso)+timedelta(days=14)).strftime('%d/%m')}).",
                ephemeral=True
            )

        except Exception:
            traceback.print_exc()
            await interaction.followup.send("❌ Erreur interne.", ephemeral=True)

    # --------------------------
    # /retour
    # --------------------------
    @app_commands.command(name="retour", description="Retourne un jeu")
    async def retour(self, interaction: discord.Interaction, jeu: str):
        await interaction.response.defer(ephemeral=True)

        try:
            jeux = await get_jeux()
            _, index_map = format_liste(jeux, True)

            if not jeu.isdigit() or not (1 <= int(jeu) <= len(index_map)):
                await interaction.followup.send("❌ Numéro invalide.", ephemeral=True)
                return

            j = index_map[int(jeu) - 1]

            if j["emprunteur_id"] != interaction.user.id:
                await interaction.followup.send("❌ Ce n’est pas ton emprunt.", ephemeral=True)
                return

            await run_db(lambda: supabase.table("jeux").update({
                "emprunte": False,
                "emprunteur": None,
                "emprunteur_id": None,
                "date_emprunt": None
            }).eq("id", j["id"]).execute())

            await self.update_message(self.bot.get_channel(CANAL_ID))
            await interaction.followup.send(f"✅ **{j['nom']}** retourné.", ephemeral=True)

        except Exception:
            traceback.print_exc()
            await interaction.followup.send("❌ Erreur interne.", ephemeral=True)

# --------------------------
# SETUP
# --------------------------
async def setup(bot):
    await bot.add_cog(Emprunts(bot))
