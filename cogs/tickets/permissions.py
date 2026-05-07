"""
Система проверки прав доступа к тикетам.
Заменяет хардкод ролей на динамическую проверку из БД.
"""

import discord
from typing import Optional
from .config_manager import TicketConfigManager


class TicketPermissions:
    """Класс для проверки прав доступа к тикетам."""
    
    @staticmethod
    async def has_ticket_access(member: discord.Member, ticket_type: str) -> bool:
        """
        Проверяет, имеет ли пользователь доступ к тикетам определенного типа.
        
        Args:
            member: Участник сервера
            ticket_type: Тип тикета (complaint, appeal, etc.)
            
        Returns:
            bool: True если имеет доступ, False если нет
        """
        # Администраторы всегда имеют доступ
        if member.guild_permissions.administrator:
            return True
        
        # Получаем роли модераторов для этого типа тикета
        moderator_roles = await TicketConfigManager.get_moderator_roles(
            member.guild.id, ticket_type
        )
        
        # Проверяем пересечение ролей пользователя с модераторскими
        member_role_ids = {role.id for role in member.roles}
        return bool(member_role_ids & moderator_roles)
    
    @staticmethod
    async def can_manage_ticket_config(member: discord.Member) -> bool:
        """
        Проверяет, может ли пользователь управлять конфигурацией тикетов.
        
        Args:
            member: Участник сервера
            
        Returns:
            bool: True если может управлять, False если нет
        """
        return member.guild_permissions.administrator
    
    @staticmethod
    async def validate_role_exists(guild: discord.Guild, role_id: int) -> Optional[discord.Role]:
        """
        Проверяет, существует ли роль на сервере.
        
        Args:
            guild: Сервер
            role_id: ID роли
            
        Returns:
            Optional[discord.Role]: Роль если существует, None если нет
        """
        return guild.get_role(role_id)
    
    @staticmethod
    async def get_ticket_access_summary(member: discord.Member) -> dict[str, bool]:
        """
        Получает сводку прав доступа пользователя ко всем типам тикетов.
        
        Args:
            member: Участник сервера
            
        Returns:
            dict[str, bool]: {ticket_type: has_access}
        """
        result = {}
        ticket_types = TicketConfigManager.get_valid_ticket_types()
        
        for ticket_type in ticket_types:
            result[ticket_type] = await TicketPermissions.has_ticket_access(member, ticket_type)
        
        return result


# Функция-обертка для обратной совместимости
async def is_ticket_moderator(interaction: discord.Interaction, ticket_data: dict = None) -> bool:
    """
    Обертка для старой функции _is_mod() с новой системой прав.
    
    Args:
        interaction: Discord interaction
        ticket_data: Данные тикета (может содержать тип)
        
    Returns:
        bool: True если пользователь может модерировать тикет
    """
    member = interaction.user
    
    # Администраторы всегда имеют доступ
    if member.guild_permissions.administrator:
        return True
    
    # Определяем тип тикета
    ticket_type = None
    if ticket_data:
        ticket_type = ticket_data.get("type")
    
    # Если тип не определен, проверяем доступ ко всем типам
    if not ticket_type:
        access_summary = await TicketPermissions.get_ticket_access_summary(member)
        return any(access_summary.values())
    
    # Проверяем доступ к конкретному типу
    return await TicketPermissions.has_ticket_access(member, ticket_type)