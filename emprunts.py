import os
import asyncio
from flask import Flask
import discord
from discord.ext import commands

# ----------------------
# FLASK (pour Render / UptimeRobot)
# ----------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot Discord actif !", 200

# ----------------------
# DISCORD BOT
# ----------------------
intents = discord.Intents.default()
intents.guilds = True
intents.members = True  # nécessaire pour vérifier les rôles Bureau
bot = commands.Bot(command_prefix=None, intents=intents)

# ----------------------
# LANCEMENT DU BOT
# ----------------------
async def start_discord_bot():
    TOKEN = os.environ.get("DISCORD_TOKEN")
    if not TOKEN:
        print("Erreur : DISCORD_TOKEN non défini dans les variables d'environnement !")
        return

    # Chargement du cog emprunts
    try:
        print("Chargement du cog emprunts...")
        await bot.load_extension("emprunts")  # emprunts.py doit être dans le même dossier
        print("Cog emprunts chargé !")
    except Exception as e:
        print(f"Erreur lors du chargement du cog : {e}")

    # Synchronisation des slash commands
    try:
        synced = await bot.tree.sync()
        print(f"{len(synced)} commandes slash synchronisées.")
    except Exception as e:
        print(f"Erreur de synchronisation des commandes : {e}")

    # Démarrage du bot
    try:
        await bot.start(TOKEN)
    except Exception as e:
        print(f"Erreur lors du démarrage du bot : {e}")

# ----------------------
# LANCEMENT FLASK + BOT
# ----------------------
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(start_discord_bot())  # lance le bot en tâche async

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
