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
                t_cfg = TICKET_CONFIG["types"].get(ticket_type, {})
                
                # Проверяем есть ли уже в БД
                existing = get_ticket_by_channel(channel.id)
                if existing:
                    skipped.append(channel.mention)
                    continue
                
                # Пытаемся извлечь данные из закреплённого сообщения
                user_id = guild.owner_id
                created_at = datetime.now().strftime("%d.%m.%Y %H:%M")
                form_data = {}
                ticket_id = 0
                
                try:
                    # Получаем закреплённые сообщения
                    pinned = await channel.pins()
                    if pinned:
                        msg = pinned[0]  # Первое закреплённое (создание тикета)
                        user_id = msg.author.id
                        created_at = msg.created_at.strftime("%d.%m.%Y %H:%M")
                        
                        # Парсим embed'ы для извлечения данных тикета
                        for embed in msg.embeds:
                            # Ищем поле "Тип" чтобы подтвердить тип тикета
                            for field in embed.fields:
                                if field.name == "Тип":
                                    ticket_type_from_embed = field.value
                                    # Пытаемся найти соответствующий тип в конфиге
                                    for tt, tc in TICKET_CONFIG["types"].items():
                                        if tc.get("label") == ticket_type_from_embed:
                                            ticket_type = tt
                                            t_cfg = tc
                                            break
                                
                                # Извлекаем form_fields из embed
                                if field.name in t_cfg.get("form_fields", []):
                                    form_data[field.name] = field.value
                                elif field.name == "Описание" and field.value and field.value != "\u200b":
                                    form_data["description"] = field.value
                                elif field.name == "Ваш CKEY":
                                    form_data["Ваш CKEY"] = field.value
                                elif field.name == "Количество часов":
                                    form_data["Количество часов"] = field.value
                                elif field.name == "Игровое имя / логин нарушителя в SS14":
                                    form_data["Игровое имя / логин нарушителя в SS14"] = field.value
                                elif field.name == "Ваш игровой логин SS14":
                                    form_data["Ваш игровой логин SS14"] = field.value
                                elif field.name == "ID раунда или примерное время события":
                                    form_data["ID раунда или примерное время события"] = field.value
                                elif field.name == "Номера нарушенных правил":
                                    form_data["Номера нарушенных правил"] = field.value
                                elif field.name == "Содержание жалобы":
                                    form_data["Содержание жалобы"] = field.value
                                elif field.name == "Тип наказания (перма, джоб, мут и т.д.)":
                                    form_data["Тип наказания"] = field.value
                                elif field.name == "Дата / время или ID бана":
                                    form_data["Дата бана"] = field.value
                                elif field.name == "Причина бана":
                                    form_data["Причина бана"] = field.value
                                elif field.name == "Текст обжалования":
                                    form_data["Текст обжалования"] = field.value
                                elif field.name == "Суть обращения":
                                    form_data["Суть обращения"] = field.value
                                elif field.name == "Ваш возраст":
                                    form_data["Ваш возраст"] = field.value
                        
                        # Извлекаем ID тикета из заголовка embed "🎫 Тикет #X"
                        main_embed = msg.embeds[0] if msg.embeds else None
                        if main_embed and main_embed.title:
                            import re as re2
                            id_match = re2.search(r"#(\d+)", main_embed.title)
                            if id_match:
                                ticket_id = int(id_match.group(1))
                        
                        # Если не нашли ID в embed, используем из имени канала
                        if ticket_id == 0:
                            ticket_id = int(match.group(2))
                    else:
                        # Нет закреплённых - берём из первого сообщения
                        async for m in channel.history(limit=1, oldest_first=True):
                            user_id = m.author.id
                            created_at = m.created_at.strftime("%d.%m.%Y %H:%M")
                            ticket_id = int(match.group(2))
                except Exception as e:
                    errors.append(f"{channel.mention}: Ошибка парсинга: {e}")
                    ticket_id = int(match.group(2))  # Fallback
                
                # Если form_data пустой, добавляем минимальные данные
                if not form_data:
                    form_data = {"description": f"Тикет синхронизирован {datetime.now().strftime('%d.%m.%Y')}"}
                
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

    @app_commands.command(name="clear_tickets_db", description="Очистить таблицу tickets (ОСТОРОЖНО! Только для администраторов)")
    @app_commands.default_permissions(administrator=True)
    async def clear_tickets_db(self, interaction: discord.Interaction):
        """Удаляет все записи из таблицы tickets. Используйте перед повторной синхронизацией."""
        from database import get_conn

        view = ClearConfirmView()
        await interaction.response.send_message(
            embed=discord.Embed(
                description="⚠️ **Вы уверены?** Это удалит ВСЕ записи о тикетах из базы данных!\n\nЭто действие нельзя отменить.",
                color=discord.Color.red()
            ),
            view=view,
            ephemeral=True
        )


class ClearConfirmView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)
    
    @discord.ui.button(label="✅ Подтвердить очистку", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        from database import get_conn
        try:
            with get_conn() as conn:
                conn.execute("DELETE FROM tickets")
                conn.execute("DELETE FROM ticket_actions")
            await interaction.response.edit_message(
                embed=discord.Embed(description="✅ База данных очищена. Теперь запустите `/sync_tickets`", color=discord.Color.green()),
                view=None
            )
        except Exception as e:
            await interaction.response.edit_message(
                embed=discord.Embed(description=f"❌ Ошибка: {e}", color=discord.Color.red()),
                view=None
            )
    
    @discord.ui.button(label="❌ Отмена", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=discord.Embed(description="Операция отменена.", color=discord.Color.light_grey()),
            view=None
        )


async def setup_admin(bot: commands.Bot):
    await bot.add_cog(TicketsAdmin(bot))
