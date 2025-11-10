import discord
from discord.ext import commands
import asyncio
import os

# Import du module d'emprunts
import emprunts

TOKEN = os.getenv("DISCORD_TOKEN")  # ton token Discord sur Render

intents = discord.Intents.default()

bot = commands.Bot(command_prefix=None, intents=intents)

async def main():
    async with bot:
        # Charge le cog d'emprunts
        await bot.load_extension("emprunts")
        await bot.start(TOKEN)

asyncio.run(main())
