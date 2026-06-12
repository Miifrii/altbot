import asyncio
import discord
from discord.ext import commands
from config import TOKEN, PREFIX, CONFIG
from database import init_db, migrate_from_json, init_departments

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
    
    # Синхронизация команд для настроенных серверов
    for guild_id in CONFIG["guild_ids"]:
        guild = discord.Object(id=guild_id)
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        print(f"Синхронизировано {len(synced)} команд для сервера {guild_id}")

    # Регистрируем persistent view для тикетов (данные загрузятся из БД при использовании)
    bot.add_view(TicketControlView(None))


async def main():
    async with bot:
        init_db()
        init_departments()  # Инициализируем отделы и роли
        migrate_from_json()
        for cog in COGS:
            await bot.load_extension(cog)
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
