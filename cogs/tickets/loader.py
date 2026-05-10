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
    error_count = 0
    
    for guild in bot.guilds:
        # Получаем категорию тикетов из конфига
        ticket_category_id = CONFIG.get("ticket_category_id")
        if not ticket_category_id:
            print(f"[TICKETS] Пропущен сервер {guild.name} - не указана категория тикетов")
            continue
        
        category = guild.get_channel(ticket_category_id)
        if not category or not isinstance(category, discord.CategoryChannel):
            print(f"[TICKETS] Пропущен сервер {guild.name} - категория не найдена")
            continue
        
        print(f"[TICKETS] Сканирование категории '{category.name}' на сервере {guild.name}")
        
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
                print(f"[TICKETS] Пропущен канал {channel.name} - неверный формат имени")
                error_count += 1
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
            
            # Способ 1: Ищем пользователя с явными permissions
            for overwrite_target, overwrite in channel.overwrites.items():
                if isinstance(overwrite_target, discord.Member):
                    # Проверяем что у пользователя есть доступ к каналу
                    if overwrite.view_channel:
                        owner_id = overwrite_target.id
                        print(f"[TICKETS] Найден владелец тикета #{ticket_id}: {overwrite_target.name} (ID: {owner_id})")
                        break
            
            # Способ 2: Если не нашли, пытаемся извлечь из истории сообщений
            if not owner_id:
                try:
                    async for message in channel.history(limit=100, oldest_first=True):
                        # Ищем первое сообщение от пользователя (не бота)
                        if not message.author.bot:
                            owner_id = message.author.id
                            print(f"[TICKETS] Владелец тикета #{ticket_id} определен из истории: {message.author.name} (ID: {owner_id})")
                            break
                except Exception as e:
                    print(f"[TICKETS] Ошибка чтения истории канала {channel.name}: {e}")
            
            if not owner_id:
                # Если не нашли владельца, пропускаем
                print(f"[TICKETS] ⚠️ Пропущен канал {channel.name} - не найден владелец")
                error_count += 1
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
                elif "другое" in topic_lower or "other" in topic_lower:
                    ticket_type = "other"
            
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
                print(f"[TICKETS] ✅ Синхронизирован тикет #{ticket_id} (тип: {ticket_type}, владелец: {owner_id})")
            except Exception as e:
                print(f"[TICKETS] ❌ Ошибка синхронизации тикета #{ticket_id}: {e}")
                error_count += 1
    
    print(f"[TICKETS] Синхронизация завершена:")
    print(f"  ✅ Добавлено: {synced_count}")
    print(f"  ⏭️  Пропущено (уже в БД): {skipped_count}")
    if error_count > 0:
        print(f"  ⚠️  Ошибок: {error_count}")


async def setup(bot: commands.Bot):
    await setup_core(bot)
    await setup_admin(bot)
    
    # Синхронизируем существующие тикеты при запуске
    await sync_existing_tickets(bot)
