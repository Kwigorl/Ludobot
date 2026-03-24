import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import json
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta
import pytz
import traceback
import openpyxl
import tempfile
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# --------------------------
# CONFIGURATION via variables d'environnement
# --------------------------
CANAL_ID = int(os.environ["CANAL_ID"])
ROLE_BUREAU_ID = int(os.environ["ROLE_BUREAU_ID"])
DATABASE_URL = os.environ["DATABASE_URL"]
GOOGLE_CREDENTIALS_JSON = os.environ["GOOGLE_CREDENTIALS_JSON"]
DRIVE_FOLDER_ID = "1_d2ecAAyx5xc6bxJl2oDUDDBywa00Okj"

TIMEZONE = pytz.timezone("Europe/Paris")

# --------------------------
# CRÉNEAUX D'EMPRUNT
# --------------------------
# 0=Lundi ... 6=Dimanche
CRENEAUX = [
    {"jour": 2, "start": 20, "end": 24},  # Mercredi 20h-24h
    {"jour": 4, "start": 20, "end": 24},  # Vendredi 20h-24h
    {"jour": 6, "start": 14, "end": 18},  # Dimanche 14h-18h
    {"jour": 1, "start": 10, "end": 22}   # Pour test, à supprimer
]

# --------------------------
# CONNEXION BDD
# --------------------------
def get_conn():
    return psycopg2.connect(DATABASE_URL)

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
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM jeux ORDER BY nom")
            return cur.fetchall()

def format_liste(jeux, filtre=None):
    lines = []
    for idx, j in enumerate(jeux, start=1):
        if filtre is not None and j["emprunte"] != filtre:
            continue
        if j["emprunte"]:
            start = j["date_emprunt"].strftime("%d/%m")
            end = (j["date_emprunt"] + timedelta(days=14)).strftime("%d/%m")
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
    if user_input.isdigit():
        idx = int(user_input) - 1
        if 0 <= idx < len(jeux):
            return jeux[idx]
    search = normaliser_texte(user_input)
    for j in jeux:
        if search in normaliser_texte(j["nom"]):
            return j
    return None

def user_a_emprunt(user_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM jeux WHERE emprunteur_id = %s", (user_id,))
            return bool(cur.fetchone())

def user_a_deja_emprunte_ce_jeu(user_id, jeu_id):
    try:
        limite = datetime.now(TIMEZONE) - timedelta(days=30)
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM historique_emprunts WHERE user_id = %s AND jeu_id = %s",
                    (user_id, jeu_id)
                )
                rows = cur.fetchall()
        for e in rows:
            d = TIMEZONE.localize(datetime.strptime(e["date_emprunt"], "%d/%m/%Y %H:%M"))
            if d >= limite:
                return True
        return False
    except Exception:
        return False

# --------------------------
# EXPORT GOOGLE DRIVE
# --------------------------
def get_drive_service():
    creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://www.googleapis.com/auth/drive.file"]
    )
    return build("drive", "v3", credentials=creds)

def export_historique_vers_drive(mois: int, annee: int):
    if mois == 12:
        fin_dt = datetime(annee + 1, 1, 1, tzinfo=TIMEZONE)
    else:
        fin_dt = datetime(annee, mois + 1, 1, tzinfo=TIMEZONE)
    debut_dt = datetime(annee, mois, 1, tzinfo=TIMEZONE)

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT user_pseudo, jeu_nom, date_emprunt, date_retour
                FROM historique_emprunts
                ORDER BY date_emprunt
            """)
            rows = cur.fetchall()

    mois_rows = []
    for r in rows:
        try:
            d = TIMEZONE.localize(datetime.strptime(r["date_emprunt"], "%d/%m/%Y %H:%M"))
            if debut_dt <= d < fin_dt:
                mois_rows.append(r)
        except Exception:
            continue

    wb = openpyxl.Workbook()
    ws = wb.active
    mois_noms = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
                 "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
    ws.title = mois_noms[mois - 1]
    ws.append(["Pseudo", "Jeu", "Date d'emprunt", "Date de retour"])
    for r in mois_rows:
        ws.append([
            r["user_pseudo"],
            r["jeu_nom"],
            r["date_emprunt"],
            r["date_retour"] or "Non retourné"
        ])

    nom_fichier = f"Emprunts_{mois_noms[mois - 1]}_{annee}.xlsx"
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp_path = tmp.name
    wb.save(tmp_path)

    service = get_drive_service()
    file_metadata = {
        "name": nom_fichier,
        "parents": [DRIVE_FOLDER_ID]
    }
    media = MediaFileUpload(tmp_path, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    service.files().create(body=file_metadata, media_body=media, fields="id").execute()
    os.remove(tmp_path)
    print(f"✅ Export Drive : {nom_fichier}")

# --------------------------
# COG
# --------------------------
class Emprunts(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.export_mensuel.start()

    async def update_message(self, channel):
        try:
            jeux = get_jeux()
            text = (
                "## Emprunts de jeux\n"
                "\u200B\n"
                "🙋 Chaque utilisateur·rice Discord peut emprunter **1 jeu à la fois**, **pour 2 semaines max**, et pas deux fois de suite le même jeu.\n\n"
                "📋 Vous trouverez la liste des jeux empruntables ci-dessous.\n\n"
                "📱 Quand vous prenez ou reposez un jeu dans le placard, indiquez-le **immédiatement** ici à l'aide de ces commandes :\n\n"
                "📤 Pour emprunter :\n"
                "`/emprunt <n° du jeu>`, (ex : `/emprunt 3`).\n"
                "📥 Pour retourner :\n"
                "`/retour <n° du jeu>`, (ex : `/retour 3`).\n\n"
                "⚠️ Ces commandes fonctionnent **uniquement sur les horaires des séances ludiques**. Pensez donc à les faire **sur le moment**, depuis Discord sur votre smartphone.\n"
                "\u200B\n"
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
    # EXPORT MENSUEL AUTOMATIQUE
    # --------------------------
    @tasks.loop(hours=1)
    async def export_mensuel(self):
        now = datetime.now(TIMEZONE)
        if now.day == 1 and now.hour == 3:
            mois_precedent = now.month - 1 if now.month > 1 else 12
            annee = now.year if now.month > 1 else now.year - 1
            try:
                export_historique_vers_drive(mois_precedent, annee)
            except Exception as e:
                print(f"❌ Export mensuel échoué : {e}")

    @export_mensuel.before_loop
    async def before_export(self):
        await self.bot.wait_until_ready()

    # --------------------------
    # /emprunt
    # --------------------------
    @app_commands.command(name="emprunt", description="Emprunte un jeu")
    async def emprunt(self, interaction: discord.Interaction, jeu: str):
        await interaction.response.defer(ephemeral=True)
        try:
            if not est_disponible():
                await interaction.followup.send("⏰ Emprunts et retours impossibles en dehors des horaires des séances ludiques.", ephemeral=True)
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
            now = datetime.now()
            now_paris = datetime.now(TIMEZONE)
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE jeux SET emprunte = TRUE, emprunteur = %s,
                        emprunteur_id = %s, date_emprunt = %s WHERE id = %s
                    """, (display, user_id, now, j["id"]))
                    cur.execute("""
                        INSERT INTO historique_emprunts
                        (user_id, user_pseudo, jeu_id, jeu_nom, date_emprunt, date_retour)
                        VALUES (%s, %s, %s, %s, %s, NULL)
                    """, (user_id, display, j["id"], j["nom"], now_paris.strftime("%d/%m/%Y %H:%M")))
                conn.commit()
            await self.update_message(self.bot.get_channel(CANAL_ID))
            await interaction.followup.send(
                f"✅ **{j['nom']}** emprunté (retour max {(now + timedelta(days=14)).strftime('%d/%m')}).",
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
                await interaction.followup.send("⏰ Emprunts et retours impossibles en dehors des horaires des séances ludiques.", ephemeral=True)
                return
            j = find_jeu(jeu)
            if not j:
                await interaction.followup.send("❌ Jeu introuvable.", ephemeral=True)
                return
            if not j["emprunte"] or j["emprunteur_id"] != interaction.user.id:
                await interaction.followup.send("❌ Retour impossible : tu n'as pas ce jeu en ta possession.", ephemeral=True)
                return
            now_paris = datetime.now(TIMEZONE)
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE jeux SET emprunte = FALSE, emprunteur = NULL,
                        emprunteur_id = NULL, date_emprunt = NULL WHERE id = %s
                    """, (j["id"],))
                    cur.execute("""
                        UPDATE historique_emprunts SET date_retour = %s
                        WHERE jeu_id = %s AND user_id = %s AND date_retour IS NULL
                    """, (now_paris.strftime("%d/%m/%Y %H:%M"), j["id"], interaction.user.id))
                conn.commit()
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
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("INSERT INTO jeux (nom) VALUES (%s)", (jeu,))
                conn.commit()
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
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM jeux WHERE id = %s", (j["id"],))
                conn.commit()
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
