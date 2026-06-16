import discord
import json
import re
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from .config import TICKET_CONFIG
from database import get_ticket_by_channel, sync_active_tickets, next_ticket_id


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

    @app_commands.command(name="sync_tickets", description="Синхронизировать активные тикеты с БД (только для администраторов)")
    @app_commands.default_permissions(administrator=True)
    async def sync_tickets(self, interaction: discord.Interaction):
        """Сканирует каналы и добавляет в БД тикеты которых там нет."""
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        added = []
        skipped = []
        errors = []
        
        # Собираем все префиксы тикетов из конфига
        prefixes = {t_cfg["name_prefix"]: t_type for t_type, t_cfg in TICKET_CONFIG["types"].items()}
        
        for category in guild.categories:
            for channel in category.text_channels:
                # Проверяем имя канала на соответствие шаблону тикета
                match = re.match(rf"^({'|'.join(prefixes.keys())})-(\d+)$", channel.name)
                if not match:
                    continue
                
                ticket_type = prefixes[match.group(1)]
                
                # Проверяем есть ли уже в БД
                existing = get_ticket_by_channel(channel.id)
                if existing:
                    skipped.append(channel.mention)
                    continue
                
                # Пытаемся найти создателя тикета по последним сообщениям
                user_id = guild.owner_id  # Запасной вариант
                created_at = datetime.now().strftime("%d.%m.%Y %H:%M")
                form_data = {}
                
                try:
                    # Берём первое сообщение для определения автора
                    async for msg in channel.history(limit=1, oldest_first=True):
                        user_id = msg.author.id
                        created_at = msg.created_at.strftime("%d.%m.%Y %H:%M")
                        break
                except Exception:
                    pass
                
                # Генерируем ID тикета
                ticket_id = next_ticket_id(ticket_type)
                
                try:
                    if sync_active_tickets(guild.id, channel.id, user_id, ticket_id, ticket_type, created_at, form_data):
                        added.append(f"{channel.mention} (ID: {ticket_id})")
                except Exception as e:
                    errors.append(f"{channel.mention}: {e}")
        
        # Формируем отчёт
        embed = discord.Embed(title="🔄 Синхронизация тикетов", color=discord.Color.green())
        
        if added:
            embed.add_field(name=f"✅ Добавлено ({len(added)})", value="\n".join(added[:10]), inline=False)
            if len(added) > 10:
                embed.add_field(name="...", value=f"и ещё {len(added) - 10}", inline=False)
        
        if skipped:
            embed.add_field(name=f"⏭️ Пропущено ({len(skipped)})", value=f"Уже есть в БД", inline=False)
        
        if errors:
            embed.add_field(name=f"❌ Ошибки ({len(errors)})", value="\n".join(errors[:5]), inline=False)
        
        if not added and not skipped and not errors:
            embed.description = "📭 Активные тикеты не найдены."
            embed.color = discord.Color.orange()
        
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup_admin(bot: commands.Bot):
    await bot.add_cog(TicketsAdmin(bot))
