from config import CONFIG

TICKET_CONFIG = {
    "log_channel_id": CONFIG["channels"]["log"],
    "panel_channel_id": CONFIG["channels"]["tickets_panel"],
    "panel_message_id": 0,
    "cooldown_seconds": CONFIG["tickets"]["cooldown_seconds"],
    "one_active_per_user": CONFIG["tickets"]["one_active_per_user"],

    "panel": {
        "color": CONFIG["tickets"]["panel_color"],
        "banner_url": CONFIG["tickets"]["banner_url"],
    },

    "types": {
        "complaint": {
            "label": "Жалоба",
            "emoji": "🚨",
            "style": "secondary",
            "description": "Пожаловаться на участника сервера за нарушение правил.",
            "category_id": CONFIG["categories"]["complaints"],
            "name_prefix": "жалоба",
            # DEPRECATED: role_ids теперь управляются через /ticketmod команды
            "role_ids": [CONFIG["roles"]["admin_dept"], CONFIG["roles"]["moderator"]],  # Fallback для миграции
        },
        "appeal": {
            "label": "Обжалование",
            "emoji": "⚖️",
            "style": "secondary",
            "description": "Обжаловать выданное наказание.",
            "category_id": CONFIG["categories"]["appeals"],
            "name_prefix": "обжалование",
            # DEPRECATED: role_ids теперь управляются через /ticketmod команды
            "role_ids": [CONFIG["roles"]["admin_dept"], CONFIG["roles"]["moderator"]],  # Fallback для миграции
        },
        "reschedule": {
            "label": "Перенос времени",
            "emoji": "🕐",
            "style": "secondary",
            "description": "Запросить перенос времени с другого сервера.",
            "category_id": CONFIG["categories"]["general"],
            "name_prefix": "перенос",
            # DEPRECATED: role_ids теперь управляются через /ticketmod команды
            "role_ids": [CONFIG["roles"]["moderator"]],  # Fallback для миграции
        },
        "verify": {
            "label": "Верификация возраста",
            "emoji": "🔞",
            "style": "secondary",
            "description": "Пройти верификацию возраста.",
            "category_id": CONFIG["categories"]["general"],
            "name_prefix": "верификация",
            # DEPRECATED: role_ids теперь управляются через /ticketmod команды
            "role_ids": [CONFIG["roles"]["moderator"]],  # Fallback для миграции
        },
        "other": {
            "label": "Другое",
            "emoji": "📝",
            "style": "secondary",
            "description": "Любой другой вопрос, не подходящий под остальные категории.",
            "category_id": CONFIG["categories"]["general"],
            "name_prefix": "другое",
            # DEPRECATED: role_ids теперь управляются через /ticketmod команды
            "role_ids": [CONFIG["roles"]["moderator"]],  # Fallback для миграции
        },
    }
}