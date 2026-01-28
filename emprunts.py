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
# Jours: 0=Lundi, 1=Mardi, 2=Mercredi, 3=Jeudi, 4=Vendredi, 5=Samedi, 6=Dimanche
CRENEAUX = [
    {"jour": 2, "start": 20, "end": 24},  # Mercredi 20h-minuit
    {"jour": 4, "start": 20, "end": 24},  # Vendredi 20h-minuit
    {"jour": 6, "start": 14, "end": 18}   # Dimanche 14h-18h
]

# Fuseau horaire (Europe/Paris = UTC+1 en hiver, UTC+2 en été)
import pytz
TIMEZONE = pytz.timezone('Europe/Paris')

# --------------------------
# FONCTIONS UTILES
# --------------------------
def est_disponible():
    """Vérifie si le service est disponible selon les créneaux définis (fuseau Europe/Paris)"""
    now = datetime.now(TIMEZONE)
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

def normaliser_texte(texte):
    """Normalise le texte pour la recherche (minuscules, sans accents)"""
    # Mapping simple des accents courants
    accents = {
        'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
        'à': 'a', 'â': 'a', 'ä': 'a',
        'ù': 'u', 'û': 'u', 'ü': 'u',
        'ô': 'o', 'ö': 'o',
        'î': 'i', 'ï': 'i',
        'ç': 'c',
        'É': 'E', 'È': 'E', 'Ê': 'E', 'Ë': 'E',
        'À': 'A', 'Â': 'A', 'Ä': 'A',
        'Ù': 'U', 'Û': 'U', 'Ü': 'U',
        'Ô': 'O', 'Ö': 'O',
        'Î': 'I', 'Ï': 'I',
        'Ç': 'C'
    }
    texte_normalise = texte.lower()
    for accent, sans_accent in accents.items():
        texte_normalise = texte_normalise.replace(accent, sans_accent)
    return texte_normalise

def find_jeu(user_input):
    """Trouve un jeu par numéro ou par nom (recherche insensible aux accents)"""
    jeux = get_jeux()
    
    # Recherche par numéro
    if user_input.isdigit():
        idx = int(user_input) - 1
        if 0 <= idx < len(jeux):
            return jeux[idx]
    
    # Recherche par nom (insensible aux accents)
    user_input_normalise = normaliser_texte(user_input)
    for j in jeux:
        if user_input_normalise in normaliser_texte(j["nom"]):
            return j
    
    return None

def user_a_emprunt(user_id):
    response = supabase.table("jeux").select("*").eq("emprunteur_id", user_id).execute()
    return len(response.data) > 0

def user_a_deja_emprunte_ce_jeu(user_id, jeu_id):
    """Vérifie si l'utilisateur a emprunté ce jeu dans les 30 derniers jours"""
    try:
        # Calculer la date d'il y a 30 jours
        il_y_a_30_jours = datetime.now(TIMEZONE) - timedelta(days=30)
        
        # Récupérer tous les emprunts de cet utilisateur pour ce jeu
        response = supabase.table("historique_emprunts") \
            .select("*") \
            .eq("user_id", user_id) \
            .eq("jeu_id", jeu_id) \
            .execute()
        
        # Vérifier manuellement si un emprunt a eu lieu dans les 30 derniers jours
        for emprunt in response.data:
            try:
                # Parser la date au format "JJ/MM/AAAA HH:MM"
                date_emprunt = datetime.strptime(emprunt["date_emprunt"], "%d/%m/%Y %H:%M")
                # Rendre la date "aware" du fuseau horaire
                date_emprunt = TIMEZONE.localize(date_emprunt)
                
                # Si l'emprunt est dans les 30 derniers jours, on bloque
                if date_emprunt >= il_y_a_30_jours:
                    return True
            except Exception as e:
                print(f"⚠️ Erreur parsing date : {e}")
                continue
        
        return False
    except Exception as e:
        print(f"⚠️ Erreur vérification dernier emprunt : {e}")
        return False  # En cas d'erreur, on autorise l'emprunt

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
        try:
            jeux = get_jeux()

            text_info = (
                "## Emprunts de jeux \n"
                "\u200B \n"
                "😊 Vous souhaitez repartir d'une séance avec un jeu de l'asso ?\n\n"
                "📆 Vous pouvez en emprunter 1 par utilisateur·rice Discord, pendant 2 semaines.\n\n"
                "📤 Pour emprunter, tapez ici la commande :\n"
                "`/emprunt [n° du jeu]` (ex : `/emprunt 3`).\n"
                "📥 Pour retourner, tapez ici la commande :\n"
                "`/retour [n° du jeu]` (ex : `/retour 3`).\n"
                "\u200B \n"
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

            msg = None
            async for m in channel.history(limit=50):
                if m.author == self.bot.user:
                    msg = m
                    break

            if msg:
                await msg.edit(content=text_info, embeds=[embed_dispo, embed_empruntes])
            else:
                await channel.send(content=text_info, embeds=[embed_dispo, embed_empruntes])
        
        except Exception as e:
            print(f"❌ Erreur update_message : {e}")

    # --------------------------
    # COMMANDES
    # --------------------------
    @app_commands.command(name="emprunt", description="Emprunte un jeu")
    @app_commands.describe(jeu="Numéro du jeu")
    async def emprunte(self, interaction: discord.Interaction, jeu: str):
        # Vérifier la disponibilité AVANT le defer pour répondre rapidement
        if not est_disponible():
            await interaction.response.send_message("⏰ Service fermé pour le moment.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)

        try:
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
            
            # Vérifier si l'utilisateur a emprunté ce jeu dans le dernier mois
            if user_a_deja_emprunte_ce_jeu(user_id, j["id"]):
                await interaction.followup.send(
                    f"❌ Tu as déjà emprunté **{j['nom']}** ce dernier mois. Tu pourras le réemprunter dans 30 jours après ton dernier emprunt.",
                    ephemeral=True
                )
                return

            now = datetime.now().isoformat()
            now_paris = datetime.now(TIMEZONE)
            supabase.table("jeux").update({
                "emprunte": True,
                "emprunteur": display_name,
                "emprunteur_id": user_id,
                "date_emprunt": now
            }).eq("id", j["id"]).execute()
            
            # Enregistrer dans l'historique
            try:
                historique_data = {
                    "user_id": user_id,
                    "user_pseudo": display_name,
                    "jeu_id": j["id"],
                    "jeu_nom": j["nom"],
                    "date_emprunt": now_paris.strftime("%d/%m/%Y %H:%M"),
                    "date_retour": None
                }
                print(f"📝 Tentative d'enregistrement historique : {historique_data}")
                result = supabase.table("historique_emprunts").insert(historique_data).execute()
                print(f"✅ Historique enregistré : {result.data}")
            except Exception as e:
                print(f"❌ Erreur enregistrement historique : {e}")
                import traceback
                traceback.print_exc()

            channel = self.bot.get_channel(CANAL_ID)
            await self.update_message(channel)
            await interaction.followup.send(
                f"✅ Tu as emprunté **{j['nom']}**. Date de retour max : {(datetime.fromisoformat(now) + timedelta(days=14)).strftime('%d/%m')}.",
                ephemeral=True
            )
        
        except Exception as e:
            print(f"❌ Erreur commande /emprunt : {e}")
            await interaction.followup.send(
                "❌ Une erreur s'est produite. Réessaye plus tard ou contacte un membre du bureau.",
                ephemeral=True
            )

    @app_commands.command(name="retour", description="Rend un jeu que tu as emprunté")
    @app_commands.describe(jeu="Numéro du jeu")
    async def rend(self, interaction: discord.Interaction, jeu: str):
        # Vérifier la disponibilité AVANT le defer pour répondre rapidement
        if not est_disponible():
            await interaction.response.send_message("⏰ Service fermé pour le moment.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)

        try:
            j = find_jeu(jeu)
            if not j:
                await interaction.followup.send("❌ Jeu introuvable.", ephemeral=True)
                return
            if not j["emprunte"]:
                await interaction.followup.send(f"❌ {j['nom']} n'est pas emprunté.", ephemeral=True)
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
            
            # Mettre à jour l'historique avec la date de retour
            try:
                now_paris = datetime.now(TIMEZONE)
                # Trouver l'emprunt en cours pour cet utilisateur et ce jeu
                response = supabase.table("historique_emprunts") \
                    .select("*") \
                    .eq("user_id", interaction.user.id) \
                    .eq("jeu_id", j["id"]) \
                    .is_("date_retour", "null") \
                    .order("id", desc=True) \
                    .limit(1) \
                    .execute()
                
                if response.data:
                    supabase.table("historique_emprunts").update({
                        "date_retour": now_paris.strftime("%d/%m/%Y %H:%M")
                    }).eq("id", response.data[0]["id"]).execute()
            except Exception as e:
                print(f"⚠️ Erreur mise à jour historique retour : {e}")

            channel = self.bot.get_channel(CANAL_ID)
            await self.update_message(channel)
            await interaction.followup.send(f"✅ Tu as retourné **{j['nom']}**.", ephemeral=True)
        
        except Exception as e:
            print(f"❌ Erreur commande /retour : {e}")
            await interaction.followup.send(
                "❌ Une erreur s'est produite. Réessaye plus tard ou contacte un membre du bureau.",
                ephemeral=True
            )

    @app_commands.command(name="ajout", description="Ajoute un jeu (Bureau)")
    @app_commands.describe(jeu="Nom du jeu à ajouter")
    async def ajout(self, interaction: discord.Interaction, jeu: str):
        await interaction.response.defer(ephemeral=True)

        try:
            if ROLE_BUREAU_ID not in [r.id for r in interaction.user.roles]:
                await interaction.followup.send("❌ Tu n'as pas la permission.", ephemeral=True)
                return

            supabase.table("jeux").insert({"nom": jeu}).execute()

            channel = self.bot.get_channel(CANAL_ID)
            await self.update_message(channel)
            await interaction.followup.send(f"✅ {jeu} ajouté.", ephemeral=True)
        
        except Exception as e:
            print(f"❌ Erreur commande /ajout : {e}")
            await interaction.followup.send(
                "❌ Une erreur s'est produite. Réessaye plus tard.",
                ephemeral=True
            )

    @app_commands.command(name="retrait", description="Retire un jeu (Bureau)")
    @app_commands.describe(jeu="Numéro du jeu à retirer")
    async def retire(self, interaction: discord.Interaction, jeu: str):
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

            channel = self.bot.get_channel(CANAL_ID)
            await self.update_message(channel)
            await interaction.followup.send(f"✅ {j['nom']} retiré.", ephemeral=True)
        
        except Exception as e:
            print(f"❌ Erreur commande /retrait : {e}")
            await interaction.followup.send(
                "❌ Une erreur s'est produite. Réessaye plus tard.",
                ephemeral=True
            )

    @app_commands.command(name="liste", description="Met à jour la liste des jeux")
    async def liste(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            channel = self.bot.get_channel(CANAL_ID)
            await self.update_message(channel)
            await interaction.followup.send("✅ Liste mise à jour.", ephemeral=True)
        
        except Exception as e:
            print(f"❌ Erreur commande /liste : {e}")
            await interaction.followup.send(
                "❌ Une erreur s'est produite. Réessaye plus tard.",
                ephemeral=True
            )

# --------------------------
# SETUP
# --------------------------
async def setup(bot):
    await bot.add_cog(Emprunts(bot))
