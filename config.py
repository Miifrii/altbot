import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = os.getenv("PREFIX", "!")

# Централизованная конфигурация всех ID каналов и ролей
CONFIG = {
    # Основные настройки
    "guild_ids": [1348258341658562560, 635506631064551467],
    
    # Каналы
    "channels": {
        "log": 1493654392941973574,
        "reviews": 1398827052047667270,
        "reviews_panel": 1398827052047667270,
        "tickets_panel": 1348258343386349627,
    },
    
    # Роли
    "roles": {
        "superadmin": 1348258341733797910,
        "admin_dept": 1348258341717278739,
        "dev_dept": 1348258341683593280,
        "events_dept": 1387750367122427975,
        
        # Администрация
        "senior_admin": 1348258341717278738,
        "admin": 1348258341717278737,
        "junior_admin": 1351640073908650065,
        
        # Модерация
        "moderator": 1387784581599727727,
        
        # Маппинг
        "senior_mapper": 1348258341683593274,
        "mapper": 1348258341683593273,
        
        # Спрайтинг
        "senior_spriter": 1348258341683593276,
        "spriter": 1348258341683593275,
        
        # Вики
        "wiki_trader": 1348258341683593272,
        "wiki_editor": 1348258341666685078,
        
        # Ивенты
        "chief_event": 1387750246355832922,
        "event": 1348258341717278731,
    },
    
    # Категории для тикетов
    "categories": {
        "complaints": 1348258343629750365,
        "appeals": 1348258343629750367,
        "general": 1348258343629750368,
    },
    
    # Настройки тикетов
    "tickets": {
        "cooldown_seconds": 20,
        "one_active_per_user": True,
        "panel_color": 0x9B59B6,
        "banner_url": "https://cdn.discordapp.com/attachments/1464876491769647277/1493563830712668291/Airbrush-IMAGE-ENHANCER-1776163578743-1776163578743.jpg?ex=69df6d36&is=69de1bb6&hm=eac5c2ee3799cbc19ea3f94ceb99ca9cbb9975916698a6a7ddf6b7524cb040eb&",
    },
    
    # Настройки отзывов
    "reviews": {
        "cooldown_seconds": 60,
    },
}
