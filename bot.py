import os
import threading
import asyncio
from flask import Flask
import discord
from discord.ext import commands

# ----------------------
# FLASK pour Render
# ----------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot Discord actif !", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# ----------------------
# DISCORD BOT
# ----------------------
TOKEN = os.environ.get("DISCORD_TOKEN")
APPLICATION_ID = int(os.environ.get("DISCORD_APPLICATION_ID"))
CANAL_ID = int(os.environ.get("CANAL_ID"))

intents = discord.Intents.default()
intents.guilds = True
intents.members = True  # nécessaire pour vérifier les rôles

bot = commands.Bot(command_prefix=None, intents=intents, application_id=APPLICATION_ID)

# ----------------------
# COGS
# ----------------------
async def load_cogs():
    try:
        await bot.load_extension("emprunts")
        print("Cog 'emprunts' chargé !")
    except Exception as e:
        print(f"Erreur lors du chargement du cog : {e}")

# ----------------------
# EVENTS
# ----------------------
@bot.event
async def on_ready():
    print(f"{bot.user} connecté !")

    # Synchronisation des slash commands
    try:
        synced = await bot.tree.sync()
        print(f"{len(synced)} commandes slash synchronisées")
    except Exception as e:
        print(f"Erreur de synchronisation : {e}")

    # Poste le message initial de la liste des jeux
    try:
        channel = bot.get_channel(CANAL_ID)
        if channel is None:
            print(f"ERREUR : impossible de trouver le canal avec ID {CANAL_ID}")
        else:
            print(f"Channel trouvé : {channel.name}")
            # Cherche le cog emprunts
            cog = bot.get_cog("Emprunts")
            if cog is None:
                print("ERREUR : le cog 'Emprunts' n'est pas chargé")
            elif not hasattr(cog, "update_message"):
                print("ERREUR : la fonction update_message n'existe pas dans le cog")
            else:
                await cog.update_message(channel, bot)
                print("Message initial de la liste des jeux posté !")
    except Exception as e:
        print(f"ERREUR lors du post du message initial : {e}")

# ----------------------
# LANCEMENT
# ----------------------
if __name__ == "__main__":
    # Flask dans un thread séparé
    threading.Thread(target=run_flask).start()
    # Charge les cogs et démarre le bot
    asyncio.run(load_cogs())
    bot.run(TOKEN)
