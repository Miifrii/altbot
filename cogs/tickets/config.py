from config import CONFIG

TICKET_CONFIG = {
    "log_channel_id": CONFIG["channels"]["log"],
    "panel_channel_id": CONFIG["channels"]["tickets_panel"],
    "panel_message_id": 0,
    "cooldown_seconds": CONFIG["tickets"]["cooldown_seconds"],
    "one_active_per_user": CONFIG["tickets"]["one_active_per_user"],
    "transcript_limit": CONFIG["tickets"].get("transcript_limit", 1000),

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
            "role_ids": [CONFIG["roles"]["admin_dept"], CONFIG["roles"]["moderator"]],
            "name_prefix": "жалоба",
        },
        "appeal": {
            "label": "Обжалование",
            "emoji": "⚖️",
            "style": "secondary",
            "description": "Обжаловать выданное наказание.",
            "category_id": CONFIG["categories"]["appeals"],
            "role_ids": [CONFIG["roles"]["admin_dept"], CONFIG["roles"]["moderator"]],
            "name_prefix": "обжалование",
        },
        "reschedule": {
            "label": "Перенос времени",
            "emoji": "🕐",
            "style": "secondary",
            "description": "Запросить перенос времени с другого сервера.",
            "category_id": CONFIG["categories"]["general"],
            "role_ids": [CONFIG["roles"]["moderator"]],
            "name_prefix": "перенос",
        },
        "verify": {
            "label": "Верификация возраста",
            "emoji": "🔞",
            "style": "secondary",
            "description": "Пройти верификацию возраста.",
            "category_id": CONFIG["categories"]["general"],
            "role_ids": [CONFIG["roles"]["moderator"]],
            "name_prefix": "верификация",
        },
        "other": {
            "label": "Другое",
            "emoji": "📝",
            "style": "secondary",
            "description": "Любой другой вопрос, не подходящий под остальные категории.",
            "category_id": CONFIG["categories"]["general"],
            "role_ids": [CONFIG["roles"]["moderator"]],
            "name_prefix": "другое",
        },
    }
}