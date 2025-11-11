import os
import threading
import asyncio
from flask import Flask
import discord
from discord.ext import commands

# ----------------------
# FLASK pour Render / UptimeRobot
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
intents = discord.Intents.default()
intents.guilds = True
intents.members = True  # nécessaire pour vérifier les rôles Bureau
bot = commands.Bot(command_prefix=None, intents=intents)

async def start_discord_bot():
    TOKEN = os.environ.get("DISCORD_TOKEN")
    if not TOKEN:
        print("Erreur : DISCORD_TOKEN manquant")
        return
    # Charge le cog
    await bot.load_extension("emprunts")
    # Synchronise les slash commands
    await bot.tree.sync()
    print("Bot Discord démarré, commandes slash synchronisées.")
    await bot.start(TOKEN)

if __name__ == "__main__":
    # Flask dans un thread séparé
    threading.Thread(target=run_flask).start()
    # Bot Discord dans le thread principal
    asyncio.run(start_discord_bot())
