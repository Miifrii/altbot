import asyncio
import discord
from discord.ext import commands
from config import TOKEN, PREFIX

COGS = [
    "cogs.notes",
    "cogs.roles",
]

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)


@bot.event
async def on_ready():
    print(f"Бот запущен как {bot.user} (ID: {bot.user.id})")
    synced = await bot.tree.sync()
    print(f"Синхронизировано slash-команд: {len(synced)}")


async def main():
    async with bot:
        for cog in COGS:
            await bot.load_extension(cog)
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
