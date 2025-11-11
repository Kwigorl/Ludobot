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
# EVENTS
# ----------------------
@bot.event
async def on_ready():
    print(f"{bot.user} connecté !")
    try:
        # Synchronisation des commandes slash
        await bot.tree.sync()
        print("Commandes slash synchronisées")
    except Exception as e:
        print(f"Erreur de synchronisation : {e}")

    # Poste le message initial de la liste des jeux
    channel = bot.get_channel(CANAL_ID)
    if channel:
        # Appelle la fonction update_message du cog
        for cog in bot.cogs.values():
            if hasattr(cog, "update_message"):
                await cog.update_message(channel)
                print("Message initial de liste des jeux posté")

# ----------------------
# COGS
# ----------------------
async def load_cogs():
    await bot.load_extension("emprunts")
    print("Cog 'emprunts' chargé !")

# ----------------------
# LANCEMENT
# ----------------------
if __name__ == "__main__":
    # Flask dans un thread séparé
    threading.Thread(target=run_flask).start()
    # Bot Discord
    asyncio.run(load_cogs())
    bot.run(TOKEN)
