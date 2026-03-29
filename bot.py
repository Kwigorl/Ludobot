import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.environ["DISCORD_TOKEN"]
APPLICATION_ID = int(os.environ["APPLICATION_ID"])
CANAL_ID = int(os.environ["CANAL_ID"])

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="", intents=intents, application_id=APPLICATION_ID)

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

async def load_cogs():
    await bot.load_extension("emprunts")
    print("Cog 'emprunts' chargé !")

if __name__ == "__main__":
    asyncio.run(load_cogs())
    bot.run(TOKEN)
