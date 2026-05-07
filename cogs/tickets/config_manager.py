"""
Менеджер конфигурации ролей модераторов тикетов и настроек панели.
Обеспечивает централизованное управление правами доступа к тикетам и конфигурацией панели.
"""

import discord
from typing import Optional, Dict, List, Set
from database import (
    add_ticket_moderator_role, remove_ticket_moderator_role,
    get_ticket_moderator_roles, get_all_ticket_moderator_roles,
    cleanup_deleted_roles, migrate_ticket_roles_from_config,
    get_panel_config, update_panel_config, init_default_panel_config
)
from .config import TICKET_CONFIG


class TicketConfigManager:
    """Менеджер конфигурации ролей модераторов тикетов и настроек панели."""
    
    # Кэш ролей: guild_id -> {ticket_type -> set(role_ids)}
    _role_cache: Dict[int, Dict[str, Set[int]]] = {}
    _cache_timestamps: Dict[int, float] = {}
    _cache_ttl = 300  # 5 минут
    
    # Кэш конфигурации панели: guild_id -> config_dict
    _panel_cache: Dict[int, Dict] = {}
    _panel_cache_timestamps: Dict[int, float] = {}
    _panel_cache_ttl = 300  # 5 минут
    
    @classmethod
    async def add_moderator_role(cls, guild: discord.Guild, ticket_type: str, 
                               role: discord.Role, added_by: discord.Member) -> tuple[bool, str]:
        """
        Добавляет роль модератора для типа тикета.
        
        Returns:
            tuple[bool, str]: (успех, сообщение)
        """
        # Проверяем существование типа тикета
        if ticket_type not in TICKET_CONFIG["types"]:
            return False, f"❌ Неизвестный тип тикета: `{ticket_type}`"
        
        # Проверяем права
        if not added_by.guild_permissions.administrator:
            return False, "❌ Только администраторы могут управлять ролями модераторов"
        
        # Добавляем в БД
        success = add_ticket_moderator_role(guild.id, ticket_type, role.id, added_by.id)
        
        if success:
            # Очищаем кэш
            cls._clear_cache(guild.id)
            type_label = TICKET_CONFIG["types"][ticket_type]["label"]
            return True, f"✅ Роль {role.mention} добавлена как модератор для тикетов типа **{type_label}**"
        else:
            return False, f"❌ Роль {role.mention} уже является модератором для этого типа тикетов"
    
    @classmethod
    async def remove_moderator_role(cls, guild: discord.Guild, ticket_type: str, 
                                  role: discord.Role, removed_by: discord.Member) -> tuple[bool, str]:
        """
        Удаляет роль модератора для типа тикета.
        
        Returns:
            tuple[bool, str]: (успех, сообщение)
        """
        # Проверяем существование типа тикета
        if ticket_type not in TICKET_CONFIG["types"]:
            return False, f"❌ Неизвестный тип тикета: `{ticket_type}`"
        
        # Проверяем права
        if not removed_by.guild_permissions.administrator:
            return False, "❌ Только администраторы могут управлять ролями модераторов"
        
        # Удаляем из БД
        success = remove_ticket_moderator_role(guild.id, ticket_type, role.id)
        
        if success:
            # Очищаем кэш
            cls._clear_cache(guild.id)
            type_label = TICKET_CONFIG["types"][ticket_type]["label"]
            return True, f"✅ Роль {role.mention} удалена из модераторов тикетов типа **{type_label}**"
        else:
            return False, f"❌ Роль {role.mention} не является модератором для этого типа тикетов"
    
    @classmethod
    async def get_moderator_roles(cls, guild_id: int, ticket_type: str) -> Set[int]:
        """
        Получает роли модераторов для типа тикета с кэшированием и fallback.
        
        Returns:
            Set[int]: Множество ID ролей модераторов
        """
        import time
        
        # Проверяем кэш
        current_time = time.time()
        if (guild_id in cls._role_cache and 
            guild_id in cls._cache_timestamps and
            current_time - cls._cache_timestamps[guild_id] < cls._cache_ttl):
            
            cached_roles = cls._role_cache[guild_id].get(ticket_type, set())
            if cached_roles:
                return cached_roles
        
        # Загружаем из БД
        db_roles = get_ticket_moderator_roles(guild_id, ticket_type)
        
        # Fallback на старый конфиг если в БД нет ролей
        if not db_roles:
            config_roles = cls._get_fallback_roles(ticket_type)
            if config_roles:
                # Автоматически мигрируем роли в БД
                await cls._migrate_roles_for_guild(guild_id, {ticket_type: config_roles})
                db_roles = config_roles
        
        # Обновляем кэш
        if guild_id not in cls._role_cache:
            cls._role_cache[guild_id] = {}
        cls._role_cache[guild_id][ticket_type] = db_roles
        cls._cache_timestamps[guild_id] = current_time
        
        return db_roles
    
    @classmethod
    async def list_all_moderator_roles(cls, guild: discord.Guild) -> Dict[str, List[Dict]]:
        """
        Получает все роли модераторов для всех типов тикетов.
        
        Returns:
            Dict[str, List[Dict]]: {ticket_type: [{"role": Role, "added_by": Member, "added_at": str}]}
        """
        db_data = get_all_ticket_moderator_roles(guild.id)
        result = {}
        
        for ticket_type, roles_data in db_data.items():
            if ticket_type not in TICKET_CONFIG["types"]:
                continue  # Пропускаем неизвестные типы
                
            result[ticket_type] = []
            for role_data in roles_data:
                role = guild.get_role(role_data["role_id"])
                if role:  # Роль еще существует
                    added_by = guild.get_member(role_data["added_by"])
                    result[ticket_type].append({
                        "role": role,
                        "added_by": added_by,
                        "added_at": role_data["added_at"]
                    })
        
        # Добавляем fallback роли если в БД пусто
        for ticket_type in TICKET_CONFIG["types"]:
            if ticket_type not in result or not result[ticket_type]:
                fallback_roles = cls._get_fallback_roles(ticket_type)
                if fallback_roles:
                    result[ticket_type] = []
                    for role_id in fallback_roles:
                        role = guild.get_role(role_id)
                        if role:
                            result[ticket_type].append({
                                "role": role,
                                "added_by": None,
                                "added_at": "Из конфига"
                            })
        
        return result
    
    @classmethod
    async def cleanup_deleted_roles(cls, guild: discord.Guild) -> int:
        """
        Удаляет роли модераторов, которые больше не существуют на сервере.
        
        Returns:
            int: Количество удаленных ролей
        """
        existing_role_ids = {role.id for role in guild.roles}
        deleted_count = cleanup_deleted_roles(guild.id, existing_role_ids)
        
        if deleted_count > 0:
            cls._clear_cache(guild.id)
        
        return deleted_count
    
    @classmethod
    async def migrate_from_config(cls, guild_id: int) -> int:
        """
        Мигрирует роли из старого конфига в БД.
        
        Returns:
            int: Количество мигрированных ролей
        """
        config_roles = {}
        
        # Собираем роли из старого конфига
        for ticket_type, type_config in TICKET_CONFIG["types"].items():
            role_ids = type_config.get("role_ids", [])
            if role_ids:
                config_roles[ticket_type] = role_ids
        
        if not config_roles:
            return 0
        
        migrated_count = migrate_ticket_roles_from_config(guild_id, config_roles)
        
        if migrated_count > 0:
            cls._clear_cache(guild_id)
        
        return migrated_count
    
    @classmethod
    def _get_fallback_roles(cls, ticket_type: str) -> Set[int]:
        """Получает роли из старого конфига как fallback."""
        type_config = TICKET_CONFIG["types"].get(ticket_type, {})
        role_ids = type_config.get("role_ids", [])
        return set(role_ids)
    
    @classmethod
    async def _migrate_roles_for_guild(cls, guild_id: int, roles_data: Dict[str, Set[int]]) -> None:
        """Автоматически мигрирует роли в БД."""
        config_roles = {ticket_type: list(role_ids) for ticket_type, role_ids in roles_data.items()}
        migrate_ticket_roles_from_config(guild_id, config_roles)
    
    @classmethod
    def _clear_cache(cls, guild_id: int) -> None:
        """Очищает кэш для сервера."""
        cls._role_cache.pop(guild_id, None)
        cls._cache_timestamps.pop(guild_id, None)
    
    @classmethod
    def get_valid_ticket_types(cls) -> List[str]:
        """Возвращает список валидных типов тикетов."""
        return list(TICKET_CONFIG["types"].keys())
    
    @classmethod
    def get_ticket_type_label(cls, ticket_type: str) -> str:
        """Возвращает человекочитаемое название типа тикета."""
        return TICKET_CONFIG["types"].get(ticket_type, {}).get("label", ticket_type)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Методы для работы с конфигурацией панели тикетов
    # ═══════════════════════════════════════════════════════════════════════════
    
    @classmethod
    async def get_panel_config(cls, guild_id: int) -> Dict:
        """
        Получает конфигурацию панели тикетов с кэшированием и автоматической миграцией.
        
        Логика:
        1. Проверяем кэш
        2. Загружаем из БД
        3. Если в БД нет - автоматически импортируем из TICKET_CONFIG
        4. Возвращаем конфиг
        
        Returns:
            Dict: Конфигурация панели
        """
        import time
        
        # Проверяем кэш
        current_time = time.time()
        if (guild_id in cls._panel_cache and 
            guild_id in cls._panel_cache_timestamps and
            current_time - cls._panel_cache_timestamps[guild_id] < cls._panel_cache_ttl):
            return cls._panel_cache[guild_id].copy()
        
        # Загружаем из БД
        db_row = get_panel_config(guild_id)
        
        if db_row:
            # Конвертируем Row в dict
            config = {
                'title': db_row['title'],
                'description': db_row['description'] or '',
                'footer': db_row['footer'] or '',
                'color': db_row['color'],
                'banner_url': db_row['banner_url'] or '',
                'panel_channel_id': db_row['panel_channel_id'] or 0,
                'panel_message_id': db_row['panel_message_id'] or 0,
            }
        else:
            # Автоматическая миграция из старого конфига
            config = cls._get_default_panel_config()
            init_default_panel_config(guild_id, config)
            print(f"[PANEL] Автоматически создан конфиг панели для guild {guild_id}")
        
        # Обновляем кэш
        cls._panel_cache[guild_id] = config.copy()
        cls._panel_cache_timestamps[guild_id] = current_time
        
        return config
    
    @classmethod
    async def update_panel_config(cls, guild_id: int, updated_by: int, **kwargs) -> tuple[bool, str]:
        """
        Обновляет конфигурацию панели тикетов.
        
        Args:
            guild_id: ID сервера
            updated_by: ID пользователя, который обновляет
            **kwargs: Поля для обновления
        
        Returns:
            tuple[bool, str]: (успех, сообщение)
        """
        # Валидация цвета если передан
        if 'color' in kwargs:
            color = kwargs['color']
            if not isinstance(color, int) or color < 0 or color > 0xFFFFFF:
                return False, "❌ Неверный формат цвета. Используйте HEX значение (например, 0x9B59B6)"
        
        # Обновляем в БД
        success = update_panel_config(guild_id, updated_by, **kwargs)
        
        if success:
            # Очищаем кэш
            cls._clear_panel_cache(guild_id)
            return True, "✅ Конфигурация панели обновлена"
        else:
            return False, "❌ Не удалось обновить конфигурацию панели"
    
    @classmethod
    async def get_panel_embed(cls, guild_id: int) -> discord.Embed:
        """
        Генерирует embed панели тикетов на основе конфигурации из БД.
        
        Args:
            guild_id: ID сервера
        
        Returns:
            discord.Embed: Готовый embed панели
        """
        config = await cls.get_panel_config(guild_id)
        
        # Создаем embed
        embed = discord.Embed(
            title=config.get('title', '🎫 Тикеты поддержки'),
            description=config.get('description', '') or (
                "Добро пожаловать в систему обращений.\n"
                "Выбери подходящую категорию и нажми кнопку ниже — "
                "мы постараемся помочь как можно скорее.\n\u200b"
            ),
            color=config.get('color', 10181046)
        )
        
        # Добавляем типы тикетов
        for t_cfg in TICKET_CONFIG["types"].values():
            embed.add_field(
                name=f"{t_cfg['emoji']} {t_cfg['label']}",
                value=t_cfg.get("description", ""),
                inline=False
            )
        
        # Footer
        footer = config.get('footer', '')
        if footer:
            embed.set_footer(text=footer)
        
        return embed
    
    @classmethod
    def _get_default_panel_config(cls) -> Dict:
        """
        Возвращает дефолтную конфигурацию панели из TICKET_CONFIG.
        
        Returns:
            Dict: Дефолтная конфигурация
        """
        old_panel = TICKET_CONFIG.get("panel", {})
        
        return {
            'title': old_panel.get('title', '🎫 Тикеты поддержки'),
            'description': old_panel.get('description', ''),
            'footer': old_panel.get('footer', '⏳ Ответ администрации может занять некоторое время. Спасибо за терпение.'),
            'color': old_panel.get('color', 10181046),  # 0x9B59B6
            'banner_url': old_panel.get('banner_url', ''),
            'panel_channel_id': TICKET_CONFIG.get('panel_channel_id', 0),
            'panel_message_id': TICKET_CONFIG.get('panel_message_id', 0),
        }
    
    @classmethod
    def _clear_panel_cache(cls, guild_id: int) -> None:
        """Очищает кэш конфигурации панели для сервера."""
        cls._panel_cache.pop(guild_id, None)
        cls._panel_cache_timestamps.pop(guild_id, None)