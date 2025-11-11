import os
import threading
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
CANAL_ID = int(os.environ.get("CANAL_ID"))
ROLE_BUREAU_ID = int(os.environ.get("ROLE_BUREAU_ID"))

intents = discord.Intents.default()
intents.guilds = True
intents.members = True  # nécessaire pour vérifier les rôles

bot = commands.Bot(command_prefix=None, intents=intents)

# ----------------------
# EVENTS
# ----------------------
@bot.event
async def on_ready():
    print(f"{bot.user} connecté !")

    # Charge le cog
    try:
        if "Emprunts" not in bot.cogs:
            await bot.load_extension("emprunts")
            print("Cog 'emprunts' chargé !")
    except Exception as e:
        print(f"Erreur chargement cog : {e}")

    # Synchronisation des slash commands
    try:
        synced = await bot.tree.sync()
        print(f"{len(synced)} commandes slash synchronisées")
    except Exception as e:
        print(f"Erreur de synchronisation : {e}")

    # Poste le message initial de la liste
    try:
        channel = bot.get_channel(CANAL_ID)
        if channel:
            for cog in bot.cogs.values():
                if hasattr(cog, "update_message"):
                    await cog.update_message(channel, bot)
                    print("Message initial de liste des jeux posté")
        else:
            print(f"Impossible de trouver le channel avec ID {CANAL_ID}")
    except Exception as e:
        print(f"Erreur en postant le message initial : {e}")

# ----------------------
# LANCEMENT
# ----------------------
if __name__ == "__main__":
    # Flask dans un thread séparé
    threading.Thread(target=run_flask).start()
    # Bot Discord
    bot.run(TOKEN)
