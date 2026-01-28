import discord
from discord.ext import commands
from discord import app_commands
import os
from datetime import datetime, timedelta
from supabase import create_client
import pytz
import traceback

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
# 0=Lundi ... 6=Dimanche
CRENEAUX = [
    {"jour": 2, "start": 15, "end": 24},  # Mercredi 15h-24h
    {"jour": 4, "start": 20, "end": 24},  # Vendredi 20h-24h
    {"jour": 6, "start": 14, "end": 18}   # Dimanche 14h-18h
]

TIMEZONE = pytz.timezone("Europe/Paris")

# --------------------------
# FONCTIONS UTILES
# --------------------------
def est_disponible():
    now = datetime.now(TIMEZONE)
    for c in CRENEAUX:
        if c["jour"] == now.weekday() and c["start"] <= now.hour < c["end"]:
            return True
    return False

def get_jeux():
    return supabase.table("jeux").select("*").order("nom").execute().data

def format_liste(jeux, filtre=None):
    lines = []
    for idx, j in enumerate(jeux, start=1):
        if filtre is not None and j["emprunte"] != filtre:
            continue
        if j["emprunte"]:
            start = datetime.fromisoformat(j["date_emprunt"]).strftime("%d/%m")
            end = (datetime.fromisoformat(j["date_emprunt"]) + timedelta(days=14)).strftime("%d/%m")
            emprunteur = f"<@{j['emprunteur_id']}>" if j["emprunteur_id"] else j["emprunteur"]
            lines.append(f"**{idx}.** {j['nom']} ({emprunteur} du {start} au {end})")
        else:
            lines.append(f"**{idx}.** {j['nom']}")
    return "\n".join(lines) if lines else "Aucun"

def normaliser_texte(txt):
    accents = str.maketrans(
        "éèêëàâäùûüôöîïç",
        "eeeeaaauuuooiic"
    )
    return txt.lower().translate(accents)

def find_jeu(user_input):
    jeux = get_jeux()
    # Recherche par numéro
    if user_input.isdigit():
        idx = int(user_input) - 1
        if 0 <= idx < len(jeux):
            return jeux[idx]
    # Recherche par nom insensible aux accents
    search = normaliser_texte(user_input)
    for j in jeux:
        if search in normaliser_texte(j["nom"]):
            return j
    return None

def user_a_emprunt(user_id):
    return bool(
        supabase.table("jeux")
        .select("id")
        .eq("emprunteur_id", user_id)
        .execute()
        .data
    )

def user_a_deja_emprunte_ce_jeu(user_id, jeu_id):
    try:
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
    except Exception:
        return False

# --------------------------
# COG
# --------------------------
class Emprunts(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def update_message(self, channel):
        try:
            jeux = get_jeux()
            text = (
                "## 🎲 Emprunts de jeux\n\n"
                "😊 Un jeu par personne, pour **2 semaines**.\n\n"
                "`/emprunt [numéro]`\n"
                "`/retour [numéro]`\n\n"
            )
            embeds = [
                discord.Embed(
                    title="✅ Jeux disponibles",
                    description=format_liste(jeux, False),
                    color=discord.Color.green()
                ),
                discord.Embed(
                    title="❌ Jeux empruntés",
                    description=format_liste(jeux, True),
                    color=discord.Color.red()
                )
            ]
            async for m in channel.history(limit=20):
                if m.author == self.bot.user:
                    await m.edit(content=text, embeds=embeds)
                    return
            await channel.send(content=text, embeds=embeds)
        except Exception as e:
            print("❌ update_message:", e)

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
            user_id = interaction.user.id
            display = interaction.user.display_name
            if user_a_emprunt(user_id):
                await interaction.followup.send("❌ Tu as déjà un jeu emprunté.", ephemeral=True)
                return
            j = find_jeu(jeu)
            if not j:
                await interaction.followup.send("❌ Jeu introuvable.", ephemeral=True)
                return
            if j["emprunte"]:
                await interaction.followup.send("❌ Jeu déjà emprunté.", ephemeral=True)
                return
            if user_a_deja_emprunte_ce_jeu(user_id, j["id"]):
                await interaction.followup.send("❌ Tu as déjà emprunté ce jeu récemment.", ephemeral=True)
                return
            now_iso = datetime.now().isoformat()
            now_paris = datetime.now(TIMEZONE)
            supabase.table("jeux").update({
                "emprunte": True,
                "emprunteur": display,
                "emprunteur_id": user_id,
                "date_emprunt": now_iso
            }).eq("id", j["id"]).execute()
            supabase.table("historique_emprunts").insert({
                "user_id": user_id,
                "user_pseudo": display,
                "jeu_id": j["id"],
                "jeu_nom": j["nom"],
                "date_emprunt": now_paris.strftime("%d/%m/%Y %H:%M"),
                "date_retour": None
            }).execute()
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
            if not est_disponible():
                await interaction.followup.send("⏰ Service fermé.", ephemeral=True)
                return
            j = find_jeu(jeu)
            if not j or not j["emprunte"]:
                await interaction.followup.send("❌ Jeu invalide.", ephemeral=True)
                return
            if j["emprunteur_id"] != interaction.user.id:
                await interaction.followup.send("❌ Ce n’est pas ton emprunt.", ephemeral=True)
                return
            supabase.table("jeux").update({
                "emprunte": False,
                "emprunteur": None,
                "emprunteur_id": None,
                "date_emprunt": None
            }).eq("id", j["id"]).execute()
            supabase.table("historique_emprunts").update({
                "date_retour": datetime.now(TIMEZONE).strftime("%d/%m/%Y %H:%M")
            }).eq("jeu_id", j["id"]).eq("user_id", interaction.user.id).is_("date_retour", "null").execute()
            await self.update_message(self.bot.get_channel(CANAL_ID))
            await interaction.followup.send(f"✅ **{j['nom']}** retourné.", ephemeral=True)
        except Exception:
            traceback.print_exc()
            await interaction.followup.send("❌ Erreur interne.", ephemeral=True)

    # --------------------------
    # /ajout (Bureau)
    # --------------------------
    @app_commands.command(name="ajout", description="Ajoute un jeu (Bureau)")
    async def ajout(self, interaction: discord.Interaction, jeu: str):
        await interaction.response.defer(ephemeral=True)
        try:
            if ROLE_BUREAU_ID not in [r.id for r in interaction.user.roles]:
                await interaction.followup.send("❌ Tu n'as pas la permission.", ephemeral=True)
                return
            # Ajouter le jeu
            supabase.table("jeux").insert({"nom": jeu}).execute()
            await self.update_message(self.bot.get_channel(CANAL_ID))
            await interaction.followup.send(f"✅ {jeu} ajouté.", ephemeral=True)
        except Exception:
            traceback.print_exc()
            await interaction.followup.send("❌ Erreur interne.", ephemeral=True)

    # --------------------------
    # /retrait (Bureau)
    # --------------------------
    @app_commands.command(name="retrait", description="Retire un jeu (Bureau)")
    async def retrait(self, interaction: discord.Interaction, jeu: str):
        await interaction.response.defer(ephemeral=True)
        try:
            if ROLE_BUREAU_ID not in [r.id for r in interaction.user.roles]:
                await interaction.followup.send("❌ Tu n'as pas la permission.", ephemeral=True)
                return
            j = find_jeu(jeu)
            if not j:
                await interaction.followup.send("❌ Jeu introuvable.", ephemeral=True)
                return
            supabase.table("jeux").delete().eq("id", j["id"]).execute()
            await self.update_message(self.bot.get_channel(CANAL_ID))
            await interaction.followup.send(f"✅ {j['nom']} retiré.", ephemeral=True)
        except Exception:
            traceback.print_exc()
            await interaction.followup.send("❌ Erreur interne.", ephemeral=True)

# --------------------------
# SETUP
# --------------------------
async def setup(bot):
    await bot.add_cog(Emprunts(bot))
