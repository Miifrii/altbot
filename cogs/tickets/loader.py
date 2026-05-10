from discord.ext import commands
from .core import setup_core
from .admin import setup_admin
import discord
from database import get_conn, create_ticket
from config import CONFIG


async def sync_existing_tickets(bot: commands.Bot):
    """
    Синхронизирует существующие тикет-каналы с БД при запуске бота.
    Находит каналы тикетов и добавляет их в БД если их там нет.
    """
    print("[TICKETS] Начинается синхронизация тикетов...")
    
    synced_count = 0
    skipped_count = 0
    
    for guild in bot.guilds:
        # Получаем категорию тикетов из конфига
        ticket_category_id = CONFIG.get("ticket_category_id")
        if not ticket_category_id:
            continue
        
        category = guild.get_channel(ticket_category_id)
        if not category or not isinstance(category, discord.CategoryChannel):
            continue
        
        # Проходим по всем каналам в категории
        for channel in category.channels:
            if not isinstance(channel, discord.TextChannel):
                continue
            
            # Проверяем формат имени канала (ticket-XXXX или тикет-XXXX)
            channel_name = channel.name.lower()
            if not (channel_name.startswith("ticket-") or channel_name.startswith("тикет-")):
                continue
            
            # Извлекаем ID тикета из имени
            try:
                ticket_id_str = channel_name.split("-")[1]
                ticket_id = int(ticket_id_str)
            except (IndexError, ValueError):
                continue
            
            # Проверяем есть ли тикет в БД
            with get_conn() as conn:
                existing = conn.execute(
                    "SELECT id FROM tickets WHERE id=? OR channel_id=?",
                    (ticket_id, channel.id)
                ).fetchone()
                
                if existing:
                    skipped_count += 1
                    continue
            
            # Пытаемся определить владельца тикета из permissions
            owner_id = None
            for overwrite in channel.overwrites:
                if isinstance(overwrite, discord.Member):
                    # Проверяем что у пользователя есть доступ к каналу
                    perms = channel.overwrites_for(overwrite)
                    if perms.view_channel:
                        owner_id = overwrite.id
                        break
            
            if not owner_id:
                # Если не нашли владельца, пропускаем
                print(f"[TICKETS] Пропущен канал {channel.name} - не найден владелец")
                continue
            
            # Определяем тип тикета (по умолчанию "general")
            ticket_type = "general"
            
            # Пытаемся определить тип по топику канала
            if channel.topic:
                topic_lower = channel.topic.lower()
                if "жалоба" in topic_lower or "complaint" in topic_lower:
                    ticket_type = "complaint"
                elif "вопрос" in topic_lower or "question" in topic_lower:
                    ticket_type = "question"
                elif "предложение" in topic_lower or "suggestion" in topic_lower:
                    ticket_type = "suggestion"
            
            # Добавляем тикет в БД
            try:
                create_ticket(
                    ticket_id=ticket_id,
                    guild_id=guild.id,
                    channel_id=channel.id,
                    user_id=owner_id,
                    ticket_type=ticket_type,
                    form_data={"synced": True, "note": "Автоматически синхронизирован при запуске бота"}
                )
                synced_count += 1
                print(f"[TICKETS] Синхронизирован тикет #{ticket_id} (канал: {channel.name}, владелец: {owner_id})")
            except Exception as e:
                print(f"[TICKETS] Ошибка синхронизации тикета #{ticket_id}: {e}")
    
    if synced_count > 0 or skipped_count > 0:
        print(f"[TICKETS] Синхронизация завершена: добавлено {synced_count}, пропущено {skipped_count}")
    else:
        print("[TICKETS] Синхронизация завершена: новых тикетов не найдено")


async def setup(bot: commands.Bot):
    await setup_core(bot)
    await setup_admin(bot)
    
    # Синхронизируем существующие тикеты при запуске
    await sync_existing_tickets(bot)
