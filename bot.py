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
    
    # Synchronisation des commandes slash
    try:
        await bot.tree.sync()
        print("Commandes slash synchronisées")
    except Exception as e:
        print(f"Erreur de synchronisation : {e}")

    # Poster le message initial de la liste des jeux
    channel = bot.get_channel(CANAL_ID)
    if channel:
        cog = bot.get_cog("Emprunts")
        if cog:
            await cog.update_message(channel)
            print("Message initial de liste des jeux posté")

    # Démarrer la suppression automatique des messages
    delete_non_command_messages.start()

# ----------------------
# SUPPRESSION DES MESSAGES NON-COMMANDES
# ----------------------
@tasks.loop(seconds=1)
async def delete_non_command_messages():
    channel = bot.get_channel(CANAL_ID)
    if not channel:
        return
    try:
        async for message in channel.history(limit=50):
            if message.author != bot.user and not message.content.startswith("/"):
                try:
                    await message.delete()
                except discord.Forbidden:
                    print(f"⚠️ Impossible de supprimer un message dans #{channel} (permissions manquantes)")
                except Exception as e:
                    print(f"Erreur suppression message : {e}")
    except Exception as e:
        print(f"Erreur boucle suppression messages : {e}")

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
    
    # Charger les cogs et lancer le bot
    asyncio.run(load_cogs())
    bot.run(TOKEN)
