import os
import threading
from flask import Flask
import discord
from discord.ext import commands, tasks
import asyncio

# ----------------------
# FLASK pour Render (ping)
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
TOKEN = os.environ["DISCORD_TOKEN"]
APPLICATION_ID = int(os.environ["DISCORD_APPLICATION_ID"])
CANAL_ID = int(os.environ["CANAL_ID"])

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="", intents=intents, application_id=APPLICATION_ID)

# ----------------------
# EVENTS
# ----------------------
@bot.event
async def on_ready():
    print(f"{bot.user} connecté !")

    try:
        await bot.tree.sync()
        print("Commandes slash synchronisées")
    except Exception as e:
        print(f"Erreur de synchronisation : {e}")

    channel = bot.get_channel(CANAL_ID)
    if channel:
        cog = bot.get_cog("Emprunts")
        if cog:
            await cog.update_message(channel)
            print("Message initial de liste des jeux posté")

@bot.event
async def on_message(message):
    if message.channel.id == CANAL_ID and message.author != bot.user:
        try:
            await message.delete()
        except discord.Forbidden:
            print(f"⚠️ Impossible de supprimer un message dans #{message.channel} (permissions manquantes)")
        except Exception as e:
            print(f"Erreur suppression message : {e}")

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
    threading.Thread(target=run_flask).start()
    asyncio.run(load_cogs())
    bot.run(TOKEN)
