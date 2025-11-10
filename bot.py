import os
import threading
import asyncio
from flask import Flask
import discord
from discord.ext import commands

# Flask pour Render / UptimeRobot
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot Discord actif !", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# Discord bot
intents = discord.Intents.default()
intents.guilds = True
intents.members = True  # nécessaire pour vérifier les rôles Bureau
bot = commands.Bot(command_prefix=None, intents=intents)

async def start_discord_bot():
    TOKEN = os.environ.get("DISCORD_TOKEN")
    await bot.load_extension("emprunts")  # charge ton cog
    await bot.tree.sync()                 # synchronise les slash commands
    await bot.start(TOKEN)

if __name__ == "__main__":
    # Flask dans un thread séparé
    threading.Thread(target=run_flask).start()

    # Bot Discord dans le thread principal
    asyncio.run(start_discord_bot())
