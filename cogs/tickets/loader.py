from discord.ext import commands
from .core import setup_core
from .admin import setup_admin


async def setup(bot: commands.Bot):
    await setup_core(bot)
    await setup_admin(bot)
