import os
import asyncio
import discord
from discord.ext import commands

# Intents pour slash commands et vérifier rôles
intents = discord.Intents.default()
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix=None, intents=intents)

# Evenement pour vérifier que le bot se connecte
@bot.event
async def on_ready():
    print(f"{bot.user} est connecté !")

async def main():
    TOKEN = os.environ.get("DISCORD_TOKEN")
    if not TOKEN:
        print("Erreur : DISCORD_TOKEN manquant")
        return
    await bot.start(TOKEN)

asyncio.run(main())
