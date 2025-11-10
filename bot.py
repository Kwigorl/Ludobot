import os
import threading
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
intents = discord.Intents.default()  # pas besoin de message_content pour slash commands
bot = commands.Bot(command_prefix=None, intents=intents)

# Cog d'emprunts
async def start_bot():
    TOKEN = os.environ["DISCORD_TOKEN"]
    async with bot:
        await bot.load_extension("emprunts")  # ton cog avec /emprunte, /rend, etc.
        await bot.start(TOKEN)

# Lancer le bot Discord dans un thread séparé
threading.Thread(target=lambda: asyncio.run(start_bot())).start()

# ----------------------
# LANCEMENT FLASK
# ----------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
