import discord
from discord.ext import commands
from discord import app_commands
from .core import _channel_tickets
from .config import TICKET_CONFIG


def _is_ticket_channel(channel: discord.TextChannel) -> bool:
    prefixes = [t["name_prefix"] for t in TICKET_CONFIG["types"].values()]
    return any(channel.name.startswith(p + "-") for p in prefixes)


def _can_manage(member: discord.Member, channel: discord.TextChannel) -> bool:
    """Проверяет что участник может управлять тикетом (администратор или роль из конфига)."""
    if member.guild_permissions.administrator:
        return True
    member_role_ids = {r.id for r in member.roles}
    for t_cfg in TICKET_CONFIG["types"].values():
        if channel.name.startswith(t_cfg["name_prefix"] + "-"):
            role_ids = t_cfg.get("role_ids", [t_cfg.get("role_id", 0)])
            if any(rid in member_role_ids for rid in role_ids):
                return True
    return False


class TicketsAdmin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ticket_add", description="Добавить пользователя в тикет")
    @app_commands.describe(member="Пользователь для добавления")
    async def ticket_add(self, interaction: discord.Interaction, member: discord.Member):
        channel = interaction.channel

        if not _is_ticket_channel(channel):
            return await interaction.response.send_message(
                embed=discord.Embed(description="❌ Эта команда работает только внутри тикета.", color=discord.Color.red()),
                ephemeral=True
            )
        if not _can_manage(interaction.user, channel):
            return await interaction.response.send_message(
                embed=discord.Embed(description="❌ У тебя нет прав управлять этим тикетом.", color=discord.Color.red()),
                ephemeral=True
            )
        if member.bot:
            return await interaction.response.send_message(
                embed=discord.Embed(description="❌ Нельзя добавить бота в тикет.", color=discord.Color.red()),
                ephemeral=True
            )

        await channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)
        await interaction.response.send_message(
            embed=discord.Embed(description=f"✅ {member.mention} добавлен в тикет.", color=discord.Color.green()),
            ephemeral=True
        )

    @app_commands.command(name="ticket_remove", description="Убрать пользователя из тикета")
    @app_commands.describe(member="Пользователь для удаления")
    async def ticket_remove(self, interaction: discord.Interaction, member: discord.Member):
        channel = interaction.channel

        if not _is_ticket_channel(channel):
            return await interaction.response.send_message(
                embed=discord.Embed(description="❌ Эта команда работает только внутри тикета.", color=discord.Color.red()),
                ephemeral=True
            )
        if not _can_manage(interaction.user, channel):
            return await interaction.response.send_message(
                embed=discord.Embed(description="❌ У тебя нет прав управлять этим тикетом.", color=discord.Color.red()),
                ephemeral=True
            )
        if member == interaction.user:
            return await interaction.response.send_message(
                embed=discord.Embed(description="❌ Нельзя убрать себя из тикета.", color=discord.Color.red()),
                ephemeral=True
            )

        await channel.set_permissions(member, overwrite=None)
        await interaction.response.send_message(
            embed=discord.Embed(description=f"✅ {member.mention} убран из тикета.", color=discord.Color.green()),
            ephemeral=True
        )


async def setup_admin(bot: commands.Bot):
    await bot.add_cog(TicketsAdmin(bot))
