import asyncio
import discord
from discord.ext import commands
from config import TOKEN, PREFIX
from database import init_db, migrate_from_json

COGS = [
    "cogs.roles",
    "cogs.tickets.loader",
    "cogs.utils",
    "cogs.reviews",
]

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)


@bot.event
async def on_ready():
    print(f"Бот запущен как {bot.user} (ID: {bot.user.id})")
    # Добавь сюда ID своего второго сервера
    for guild_id in [1348258341658562560, 635506631064551467]:  # ← добавь свой ID сюда
        guild = discord.Object(id=guild_id)
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        print(f"Синхронизировано {len(synced)} команд для сервера {guild_id}")


async def main():
    async with bot:
        init_db()
        migrate_from_json()
        for cog in COGS:
            await bot.load_extension(cog)
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
