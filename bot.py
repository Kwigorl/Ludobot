import os
import asyncio
from flask import Flask
import discord
from discord.ext import commands

# ----------------------
# FLASK (pour Render)
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

async def start_discord_bot():
    TOKEN = os.environ["DISCORD_TOKEN"]

    # Chargement du cog
    try:
        print("Chargement du cog emprunts...")
        await bot.load_extension("emprunts")  # emprunts.py dans le même dossier
        print("Cog emprunts chargé !")
    except Exception as e:
        print(f"Erreur lors du chargement du cog : {e}")

    # Synchronisation des slash commands
    try:
        synced = await bot.tree.sync()
        print(f"{len(synced)} commandes slash synchronisées.")
    except Exception as e:
        print(f"Erreur de synchronisation des commandes : {e}")

    await bot.start(TOKEN)

# ----------------------
# LANCEMENT FLASK + BOT
# ----------------------
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(start_discord_bot())  # lance le bot en tâche async

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
