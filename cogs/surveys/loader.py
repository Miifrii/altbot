"""
Загрузчик всех cogs системы опросов.
"""
from discord.ext import commands


async def setup(bot: commands.Bot):
    """Загружает все cogs системы опросов."""
    # Загружаем основной cog (он инициализирует БД)
    await bot.load_extension("cogs.surveys.core")
    
    # Загружаем админ-команды
    await bot.load_extension("cogs.surveys.admin")
    
    # Загружаем статистику
    await bot.load_extension("cogs.surveys.stats")
    
    print("[SURVEYS] Система опросов загружена.")
