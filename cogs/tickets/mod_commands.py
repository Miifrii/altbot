"""
Slash команды для управления ролями модераторов тикетов.
Команды: /ticketmod add, /ticketmod remove, /ticketmod list
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Literal

from .config_manager import TicketConfigManager
from .permissions import TicketPermissions


class TicketModCommands(commands.Cog):
    """Команды управления ролями модераторов тикетов."""
    
    def __init__(self, bot):
        self.bot = bot
    
    ticketmod = app_commands.Group(
        name="ticketmod", 
        description="Управление ролями модераторов тикетов"
    )
    
    @ticketmod.command(name="add", description="Добавить роль модератора для типа тикетов")
    @app_commands.describe(
        ticket_type="Тип тикетов для модерации",
        role="Роль, которая получит права модератора"
    )
    async def add_moderator_role(
        self, 
        interaction: discord.Interaction,
        ticket_type: Literal["complaint", "appeal", "reschedule", "verify", "other"],
        role: discord.Role
    ):
        """Добавляет роль модератора для типа тикетов."""
        await interaction.response.defer(ephemeral=True)
        
        # Проверяем права
        if not await TicketPermissions.can_manage_ticket_config(interaction.user):
            embed = discord.Embed(
                title="❌ Недостаточно прав",
                description="Только администраторы могут управлять ролями модераторов тикетов.",
                color=discord.Color.red()
            )
            return await interaction.followup.send(embed=embed)
        
        # Проверяем, что роль не @everyone
        if role.is_default():
            embed = discord.Embed(
                title="❌ Недопустимая роль",
                description="Нельзя назначить роль @everyone модератором тикетов.",
                color=discord.Color.red()
            )
            return await interaction.followup.send(embed=embed)
        
        # Проверяем, что роль не выше роли бота
        if role >= interaction.guild.me.top_role:
            embed = discord.Embed(
                title="❌ Роль слишком высокая",
                description="Роль бота должна быть выше назначаемой роли модератора.",
                color=discord.Color.red()
            )
            return await interaction.followup.send(embed=embed)
        
        # Добавляем роль
        success, message = await TicketConfigManager.add_moderator_role(
            interaction.guild, ticket_type, role, interaction.user
        )
        
        # Создаем embed ответ
        color = discord.Color.green() if success else discord.Color.red()
        embed = discord.Embed(
            title="🎫 Управление модераторами тикетов",
            description=message,
            color=color
        )
        
        if success:
            type_label = TicketConfigManager.get_ticket_type_label(ticket_type)
            embed.add_field(
                name="📋 Детали",
                value=f"**Тип тикетов:** {type_label}\n**Роль:** {role.mention}\n**Добавил:** {interaction.user.mention}",
                inline=False
            )
        
        await interaction.followup.send(embed=embed)
    
    @ticketmod.command(name="remove", description="Удалить роль модератора для типа тикетов")
    @app_commands.describe(
        ticket_type="Тип тикетов",
        role="Роль для удаления из модераторов"
    )
    async def remove_moderator_role(
        self, 
        interaction: discord.Interaction,
        ticket_type: Literal["complaint", "appeal", "reschedule", "verify", "other"],
        role: discord.Role
    ):
        """Удаляет роль модератора для типа тикетов."""
        await interaction.response.defer(ephemeral=True)
        
        # Проверяем права
        if not await TicketPermissions.can_manage_ticket_config(interaction.user):
            embed = discord.Embed(
                title="❌ Недостаточно прав",
                description="Только администраторы могут управлять ролями модераторов тикетов.",
                color=discord.Color.red()
            )
            return await interaction.followup.send(embed=embed)
        
        # Удаляем роль
        success, message = await TicketConfigManager.remove_moderator_role(
            interaction.guild, ticket_type, role, interaction.user
        )
        
        # Создаем embed ответ
        color = discord.Color.green() if success else discord.Color.red()
        embed = discord.Embed(
            title="🎫 Управление модераторами тикетов",
            description=message,
            color=color
        )
        
        if success:
            type_label = TicketConfigManager.get_ticket_type_label(ticket_type)
            embed.add_field(
                name="📋 Детали",
                value=f"**Тип тикетов:** {type_label}\n**Роль:** {role.mention}\n**Удалил:** {interaction.user.mention}",
                inline=False
            )
        
        await interaction.followup.send(embed=embed)
    
    @ticketmod.command(name="list", description="Показать список ролей модераторов тикетов")
    @app_commands.describe(
        ticket_type="Тип тикетов (необязательно, по умолчанию все типы)"
    )
    async def list_moderator_roles(
        self, 
        interaction: discord.Interaction,
        ticket_type: Optional[Literal["complaint", "appeal", "reschedule", "verify", "other"]] = None
    ):
        """Показывает список ролей модераторов тикетов."""
        await interaction.response.defer(ephemeral=True)
        
        # Проверяем права (список могут смотреть все администраторы)
        if not await TicketPermissions.can_manage_ticket_config(interaction.user):
            embed = discord.Embed(
                title="❌ Недостаточно прав",
                description="Только администраторы могут просматривать конфигурацию модераторов тикетов.",
                color=discord.Color.red()
            )
            return await interaction.followup.send(embed=embed)
        
        # Получаем данные
        all_roles = await TicketConfigManager.list_all_moderator_roles(interaction.guild)
        
        # Создаем embed
        embed = discord.Embed(
            title="🎫 Роли модераторов тикетов",
            color=discord.Color.blurple()
        )
        
        # Фильтруем по типу если указан
        if ticket_type:
            all_roles = {ticket_type: all_roles.get(ticket_type, [])}
        
        # Добавляем информацию о ролях
        if not all_roles or not any(all_roles.values()):
            embed.description = "❌ Роли модераторов не настроены.\nИспользуйте `/ticketmod add` для добавления ролей."
        else:
            for t_type, roles_data in all_roles.items():
                if not roles_data:
                    continue
                
                type_label = TicketConfigManager.get_ticket_type_label(t_type)
                
                role_lines = []
                for role_info in roles_data:
                    role = role_info["role"]
                    added_by = role_info["added_by"]
                    added_at = role_info["added_at"]
                    
                    if added_by:
                        role_lines.append(f"• {role.mention} (добавил {added_by.mention}, {added_at})")
                    else:
                        role_lines.append(f"• {role.mention} ({added_at})")
                
                if role_lines:
                    embed.add_field(
                        name=f"🏷️ {type_label}",
                        value="\n".join(role_lines),
                        inline=False
                    )
        
        # Добавляем footer с подсказками
        embed.set_footer(
            text="💡 Используйте /ticketmod add или /ticketmod remove для управления ролями"
        )
        
        await interaction.followup.send(embed=embed)
    
    @ticketmod.command(name="cleanup", description="Удалить несуществующие роли из конфигурации")
    async def cleanup_roles(self, interaction: discord.Interaction):
        """Удаляет роли модераторов, которые больше не существуют на сервере."""
        await interaction.response.defer(ephemeral=True)
        
        # Проверяем права
        if not await TicketPermissions.can_manage_ticket_config(interaction.user):
            embed = discord.Embed(
                title="❌ Недостаточно прав",
                description="Только администраторы могут управлять конфигурацией тикетов.",
                color=discord.Color.red()
            )
            return await interaction.followup.send(embed=embed)
        
        # Выполняем очистку
        deleted_count = await TicketConfigManager.cleanup_deleted_roles(interaction.guild)
        
        # Создаем ответ
        if deleted_count > 0:
            embed = discord.Embed(
                title="🧹 Очистка завершена",
                description=f"✅ Удалено {deleted_count} несуществующих ролей из конфигурации.",
                color=discord.Color.green()
            )
        else:
            embed = discord.Embed(
                title="🧹 Очистка завершена",
                description="✅ Все роли в конфигурации актуальны, удаление не требуется.",
                color=discord.Color.green()
            )
        
        await interaction.followup.send(embed=embed)
    
    @ticketmod.command(name="migrate", description="Мигрировать роли из старого конфига в БД")
    async def migrate_config(self, interaction: discord.Interaction):
        """Мигрирует роли модераторов из старого конфига в базу данных."""
        await interaction.response.defer(ephemeral=True)
        
        # Проверяем права
        if not await TicketPermissions.can_manage_ticket_config(interaction.user):
            embed = discord.Embed(
                title="❌ Недостаточно прав",
                description="Только администраторы могут выполнять миграцию.",
                color=discord.Color.red()
            )
            return await interaction.followup.send(embed=embed)
        
        # Выполняем миграцию
        migrated_count = await TicketConfigManager.migrate_from_config(interaction.guild.id)
        
        # Создаем ответ
        if migrated_count > 0:
            embed = discord.Embed(
                title="📦 Миграция завершена",
                description=f"✅ Мигрировано {migrated_count} ролей из старого конфига в базу данных.",
                color=discord.Color.green()
            )
            embed.add_field(
                name="💡 Что дальше?",
                value="Теперь вы можете управлять ролями через команды `/ticketmod add` и `/ticketmod remove`",
                inline=False
            )
        else:
            embed = discord.Embed(
                title="📦 Миграция завершена",
                description="ℹ️ Роли уже мигрированы или отсутствуют в старом конфиге.",
                color=discord.Color.blue()
            )
        
        await interaction.followup.send(embed=embed)


async def setup(bot):
    """Загружает cog с командами управления модераторами тикетов."""
    await bot.add_cog(TicketModCommands(bot))