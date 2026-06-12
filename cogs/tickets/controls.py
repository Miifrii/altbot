import discord
import json
from .transcript import generate_transcript
from .config import TICKET_CONFIG
from database import claim_ticket as db_claim_ticket, close_ticket as db_close_ticket, get_ticket_by_channel


# ── Embed helpers ────────────────────────────────────────────────────────────

def _truncate(text: str, limit: int) -> str:
    """Обрезает текст до лимита с добавлением '...'."""
    if not text:
        return text
    if len(text) <= limit:
        return text
    return text[:limit - 3] + "..."


def _build_base_embed(ticket_data: dict, status: str, assignee: discord.Member = None) -> discord.Embed:
    """Создаёт основной embed с базовой информацией."""
    colors = {"открыт": discord.Color.purple(), "в работе": discord.Color.yellow(), "закрыт": discord.Color.red()}
    embed = discord.Embed(title=f"🎫 Тикет #{ticket_data['id']}", color=colors.get(status, discord.Color.blurple()))
    embed.add_field(name="Тип",    value=ticket_data["type_label"], inline=True)
    embed.add_field(name="Статус", value=status,                    inline=True)
    embed.add_field(name="Автор",  value=ticket_data["author"],     inline=True)
    
    if ticket_data.get("description"):
        embed.add_field(name="Описание", value=_truncate(ticket_data["description"], 1024), inline=False)
    if ticket_data.get("details"):
        embed.add_field(name="Детали", value=_truncate(ticket_data["details"], 1024), inline=False)
    
    if assignee:
        embed.add_field(name="Ответственный", value=assignee.mention, inline=True)
    if ticket_data.get("avatar_url"):
        embed.set_thumbnail(url=ticket_data["avatar_url"])
    embed.set_footer(text=f"Создан: {ticket_data['created_at']}")
    return embed


def _add_fields_to_embed(embed: discord.Embed, fields: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Добавляет поля в embed пока не достигнет лимита.
    Возвращает оставшиеся поля которые не влезли."""
    remaining = []
    for label, value in fields:
        if len(embed.fields) >= 25:
            remaining.append((label, value))
            continue
        embed.add_field(name=_truncate(label, 256), value=_truncate(value, 1024), inline=False)
    return remaining


def build_ticket_embeds(ticket_data: dict, status: str, assignee: discord.Member = None) -> list[discord.Embed]:
    """Создаёт список embed'ов для тикета, разбивая поля на несколько embed'ов при необходимости."""
    # Основной embed
    base_embed = _build_base_embed(ticket_data, status, assignee)
    
    # Собираем form_fields
    form_fields = []
    for label, value in ticket_data.get("form_fields", {}).items():
        if value:
            form_fields.append((label, value))
    
    if not form_fields:
        return [base_embed]
    
    # Пытаемся добавить form_fields в основной embed
    remaining = _add_fields_to_embed(base_embed, form_fields)
    
    embeds = [base_embed]
    
    # Если остались поля - создаём дополнительные embed'ы (макс. 10 на сообщение)
    while remaining and len(embeds) < 10:
        extra_embed = discord.Embed(
            title=f"🎫 Тикет #{ticket_data['id']} (продолжение)",
            color=base_embed.color
        )
        remaining = _add_fields_to_embed(extra_embed, remaining)
        embeds.append(extra_embed)

    return embeds


async def send_ticket_embeds(
    channel: discord.TextChannel,
    ticket_data: dict,
    status: str,
    assignee: discord.Member = None,
    view: discord.ui.View = None
) -> discord.Message:
    """Отправляет embed'ы тикета в канал. Возвращает основное сообщение (с view)."""
    embeds = build_ticket_embeds(ticket_data, status, assignee)
    
    # Первое сообщение с view
    main_msg = await channel.send(embeds=embeds[:1], view=view)
    
    # Если есть доп. embed'ы - отправляем их отдельными сообщениями
    for extra_embed in embeds[1:]:
        await channel.send(embed=extra_embed)
    
    return main_msg


async def edit_ticket_embeds(
    channel: discord.TextChannel,
    ticket_data: dict,
    status: str,
    assignee: discord.Member = None,
    main_msg: discord.Message = None
) -> None:
    """Редактирует все embed'ы тикета в канале."""
    embeds = build_ticket_embeds(ticket_data, status, assignee)
    
    # Определяем основное сообщение
    if main_msg and main_msg.author == channel.guild.me:
        # Используем переданное сообщение как основное
        await main_msg.edit(embeds=embeds[:1])
        target_main_id = main_msg.id
    else:
        # Ищем первое сообщение бота с embed в канале
        target_main_id = None
        async for msg in channel.history(limit=20, oldest_first=True):
            if msg.author == channel.guild.me and msg.embeds:
                await msg.edit(embeds=embeds[:1])
                target_main_id = msg.id
                break
    
    # Собираем все остальные сообщения бота с embed (кроме основного)
    bot_messages = []
    async for msg in channel.history(limit=20, oldest_first=True):
        if msg.author == channel.guild.me and msg.embeds and msg.id != target_main_id:
            bot_messages.append(msg)
    
    # Удаляем старые дополнительные сообщения
    for msg in bot_messages:
        try:
            await msg.delete()
        except discord.NotFound:
            pass

    # Отправляем новые дополнительные embed'ы если есть
    for extra_embed in embeds[1:]:
        await channel.send(embed=extra_embed)


def _is_mod(interaction: discord.Interaction, ticket_data: dict = None) -> bool:
    """Администратор — полный доступ. Иначе проверяем role_ids из конфига тикета."""
    member = interaction.user
    if member.guild_permissions.administrator:
        return True
    if ticket_data:
        t_type = ticket_data.get("type", "")
        t_cfg = TICKET_CONFIG.get("types", {}).get(t_type, {})
        role_ids = t_cfg.get("role_ids", [t_cfg.get("role_id", 0)])
        member_role_ids = {r.id for r in member.roles}
        if any(rid in member_role_ids for rid in role_ids):
            return True
    return False


class CloseModal(discord.ui.Modal, title="Закрытие тикета"):
    reason = discord.ui.TextInput(label="Причина закрытия", style=discord.TextStyle.paragraph, max_length=500)

    def __init__(self, ticket_data: dict, assignee: discord.Member = None):
        super().__init__()
        self.ticket_data = ticket_data
        self.assignee = assignee

    async def on_submit(self, interaction: discord.Interaction):
        view = ConfirmCloseView(self.ticket_data, self.reason.value, self.assignee)
        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"Закрыть тикет?\nПричина: **{self.reason.value}**",
                color=discord.Color.orange()
            ),
            view=view, ephemeral=True
        )


class ConfirmCloseView(discord.ui.View):
    def __init__(self, ticket_data: dict, reason: str, assignee: discord.Member = None):
        super().__init__(timeout=30)
        self.ticket_data = ticket_data
        self.reason = reason
        self.assignee = assignee
        self._closing = False

    @discord.ui.button(label="Подтвердить", style=discord.ButtonStyle.danger, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._closing:
            return await interaction.response.defer()
        self._closing = True

        await interaction.response.defer(ephemeral=True)
        channel = interaction.channel
        log_channel_id = TICKET_CONFIG.get("log_channel_id", 0)

        try:
            transcript = await generate_transcript(channel)
        except Exception:
            transcript = None

        # Получаем актуальные данные тикета из БД
        ticket_id = self.ticket_data.get("id", 0)
        type_label = self.ticket_data.get("type_label", "—")
        author_id = self.ticket_data.get("author_id")
        author_mention = self.ticket_data.get("author", "—")
        
        try:
            row = get_ticket_by_channel(channel.id)
            if row:
                ticket_id = row["id"]
                t_type = row["type"]
                user_id = row["user_id"]
                
                # Получаем конфиг типа тикета
                t_cfg = TICKET_CONFIG.get("types", {}).get(t_type, {})
                type_label = t_cfg.get("label", t_type)
                
                # Получаем пользователя
                author = interaction.guild.get_member(user_id)
                author_mention = author.mention if author else f"<@{user_id}>"
                
                print(f"[LOG] Данные тикета из БД: ID={ticket_id}, тип={type_label}, автор={author_mention}")
            else:
                print(f"[LOG] Тикет не найден в БД для канала {channel.id}, используем данные из ticket_data")
                # Fallback на данные из ticket_data - они уже должны быть заполнены
                if author_id:
                    author = interaction.guild.get_member(author_id)
                    if author:
                        author_mention = author.mention
                print(f"[LOG] Fallback данные: ID={ticket_id}, тип={type_label}, автор={author_mention}")
        except Exception as e:
            print(f"[LOG] Ошибка получения данных тикета: {e}")
            # Оставляем данные из ticket_data
            if author_id:
                try:
                    author = interaction.guild.get_member(author_id)
                    if author:
                        author_mention = author.mention
                except Exception:
                    pass
            print(f"[LOG] Fallback после ошибки: ID={ticket_id}, тип={type_label}, автор={author_mention}")

        if log_channel_id:
            log_channel = interaction.guild.get_channel(log_channel_id)
            if log_channel:
                embed = discord.Embed(title=f"📋 Тикет #{ticket_id} закрыт", color=discord.Color.red())
                embed.add_field(name="Тип",     value=type_label,               inline=True)
                embed.add_field(name="Автор",   value=author_mention,           inline=True)
                embed.add_field(name="Закрыл",  value=interaction.user.mention, inline=True)
                embed.add_field(name="Причина", value=self.reason,              inline=False)
                try:
                    if transcript:
                        await log_channel.send(embed=embed, file=transcript)
                    else:
                        await log_channel.send(embed=embed)
                    print(f"[LOG] Лог отправлен: Тикет #{ticket_id}, тип={type_label}")
                except Exception as e:
                    print(f"[LOG] Ошибка отправки лога: {e}")

        try:
            row = get_ticket_by_channel(channel.id)
            if row:
                db_close_ticket(row["id"], interaction.user.id, self.reason)
        except Exception as e:
            print(f"[DB] Ошибка close_ticket: {e}")

        # Уведомление автору в ЛС
        author_id = self.ticket_data.get("author_id")
        if author_id:
            author = interaction.guild.get_member(author_id)
            if author:
                try:
                    embed_dm = discord.Embed(
                        title="📋 Твой тикет закрыт",
                        color=discord.Color.red()
                    )
                    embed_dm.add_field(name="Тип", value=self.ticket_data.get("type_label", "—"), inline=True)
                    embed_dm.add_field(name="Закрыл", value=interaction.user.mention, inline=True)
                    embed_dm.add_field(name="Причина", value=self.reason, inline=False)
                    embed_dm.set_footer(text=interaction.guild.name)
                    await author.send(embed=embed_dm)
                except discord.Forbidden:
                    pass  # ЛС закрыты

        try:
            await channel.delete(reason=f"Тикет закрыт: {self.reason}")
        except discord.NotFound:
            pass

    @discord.ui.button(label="Отмена", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=discord.Embed(description="Закрытие отменено.", color=discord.Color.light_grey()),
            view=None
        )


class TransferSelect(discord.ui.UserSelect):
    def __init__(self, ticket_data: dict, control_view: "TicketControlView"):
        super().__init__(placeholder="Выбери модератора...")
        self.ticket_data = ticket_data
        self.control_view = control_view

    async def callback(self, interaction: discord.Interaction):
        new_assignee = self.values[0]
        if new_assignee.bot:
            return await interaction.response.send_message(
                embed=discord.Embed(description="❌ Нельзя передать тикет боту.", color=discord.Color.red()),
                ephemeral=True
            )
        
        # Загружаем свежие данные из БД
        try:
            row = get_ticket_by_channel(interaction.channel.id)
            if row:
                t_type = row["type"]
                t_cfg = TICKET_CONFIG.get("types", {}).get(t_type, {})
                
                form_fields = {}
                description = ""
                if row["form_data"]:
                    try:
                        parsed = json.loads(row["form_data"])
                        if isinstance(parsed, dict):
                            form_fields = parsed
                            # description — первое значение в form_fields, если ключ "description" пуст
                            description = parsed.get("description", "")
                    except json.JSONDecodeError:
                        pass
                
                author = interaction.guild.get_member(row["user_id"])
                author_mention = author.mention if author else f"<@{row['user_id']}>"
                
                td = {
                    "id": row["id"],
                    "type": t_type,
                    "type_label": t_cfg.get("label", t_type),
                    "author": author_mention,
                    "author_id": row["user_id"],
                    "description": description,
                    "form_fields": form_fields,
                    "created_at": row["created_at"],
                    "avatar_url": str(author.display_avatar.url) if author else None,
                    "assignee_id": new_assignee.id,
                }
            else:
                # Тикет не найден в БД - используем fallback с новым assignee
                print(f"[TICKET] Тикет не найден в БД для канала {interaction.channel.id}")
                td = dict(self.ticket_data)
                td["assignee_id"] = new_assignee.id
        except Exception as e:
            print(f"[TICKET] Ошибка загрузки данных для передачи: {e}")
            td = dict(self.ticket_data)
            td["assignee_id"] = new_assignee.id
        
        self.control_view.assignee = new_assignee
        await edit_ticket_embeds(interaction.channel, td, "в работе", new_assignee)
        await interaction.response.send_message(
            embed=discord.Embed(description=f"Тикет передан {new_assignee.mention}.", color=discord.Color.green()),
            ephemeral=True
        )
        self.view.stop()


class TransferView(discord.ui.View):
    def __init__(self, ticket_data: dict, control_view: "TicketControlView"):
        super().__init__(timeout=30)
        self.add_item(TransferSelect(ticket_data, control_view))


class TicketControlView(discord.ui.View):
    def __init__(self, ticket_data: dict = None):
        super().__init__(timeout=None)
        self.ticket_data = ticket_data or {}
        self.assignee: discord.Member = None

    def _get_data(self, interaction: discord.Interaction) -> dict:
        # Всегда пытаемся загрузить актуальные данные из БД
        try:
            row = get_ticket_by_channel(interaction.channel.id)
            if row:
                ticket_id = row["id"]
                t_type = row["type"]
                t_cfg = TICKET_CONFIG.get("types", {}).get(t_type, {})
                
                # Парсим form_data из JSON с валидацией
                form_fields = {}
                description = ""
                if row["form_data"]:
                    try:
                        parsed = json.loads(row["form_data"])
                        if isinstance(parsed, dict):
                            form_fields = parsed
                            description = parsed.get("description", "")
                        else:
                            print(f"[TICKET] form_data имеет неверный тип: {type(parsed)}")
                    except json.JSONDecodeError as e:
                        print(f"[TICKET] Ошибка парсинга form_data: {e}")
                
                # Получаем пользователя для корректного отображения
                author = interaction.guild.get_member(row["user_id"])
                author_mention = author.mention if author else f"<@{row['user_id']}>"
                
                # Обновляем данные из БД
                self.ticket_data = {
                    "id": ticket_id,
                    "type": t_type,
                    "type_label": t_cfg.get("label", t_type),
                    "author": author_mention,
                    "author_id": row["user_id"],
                    "description": description,
                    "form_fields": form_fields,
                    "created_at": row["created_at"],
                    "avatar_url": str(author.display_avatar.url) if author else None,
                }
                print(f"[TICKET] Загружены данные из БД: ID={ticket_id}, тип={t_cfg.get('label', t_type)}")
                return self.ticket_data
        except Exception as e:
            print(f"[TICKET] Ошибка загрузки ticket_data из БД: {e}")

        # Не удалось загрузить данные из БД
        return None

    @discord.ui.button(label="Взять тикет", style=discord.ButtonStyle.success, emoji="🙋", custom_id="ticket_take")
    async def take(self, interaction: discord.Interaction, button: discord.ui.Button):
        td = self._get_data(interaction)
        if not td:
            return await interaction.response.send_message(
                embed=discord.Embed(description="❌ Не удалось загрузить данные тикета.", color=discord.Color.red()),
                ephemeral=True
            )
        if not _is_mod(interaction, td):
            return await interaction.response.send_message(
                embed=discord.Embed(description="❌ У тебя нет прав брать этот тикет.", color=discord.Color.red()),
                ephemeral=True
            )
        if self.assignee is not None:
            return await interaction.response.send_message(
                embed=discord.Embed(description=f"❌ Тикет уже взят: {self.assignee.mention}", color=discord.Color.orange()),
                ephemeral=True
            )
        self.assignee = interaction.user
        td["assignee_id"] = interaction.user.id
        await edit_ticket_embeds(interaction.channel, td, "в работе", self.assignee, main_msg=interaction.message)
        try:
            db_claim_ticket(td["id"], interaction.user.id)
        except Exception as e:
            print(f"[DB] Ошибка claim_ticket: {e}")
        await interaction.response.send_message(
            embed=discord.Embed(description="✅ Ты взял тикет.", color=discord.Color.green()),
            ephemeral=True
        )

    @discord.ui.button(label="Передать тикет", style=discord.ButtonStyle.primary, emoji="🔄", custom_id="ticket_transfer")
    async def transfer(self, interaction: discord.Interaction, button: discord.ui.Button):
        td = self._get_data(interaction)
        if not td:
            return await interaction.response.send_message(
                embed=discord.Embed(description="❌ Не удалось загрузить данные тикета.", color=discord.Color.red()),
                ephemeral=True
            )
        if not _is_mod(interaction, td):
            return await interaction.response.send_message(
                embed=discord.Embed(description="❌ У тебя нет прав передавать этот тикет.", color=discord.Color.red()),
                ephemeral=True
            )
        await interaction.response.send_message(
            embed=discord.Embed(description="Выбери модератора для передачи тикета:", color=discord.Color.blurple()),
            view=TransferView(td, self),
            ephemeral=True
        )

    @discord.ui.button(label="Закрыть тикет", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="ticket_close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        td = self._get_data(interaction)
        if not td:
            return await interaction.response.send_message(
                embed=discord.Embed(description="❌ Не удалось загрузить данные тикета.", color=discord.Color.red()),
                ephemeral=True
            )
        if not _is_mod(interaction, td):
            if td.get("author_id") != interaction.user.id:
                return await interaction.response.send_message(
                    embed=discord.Embed(description="❌ Только модераторы или автор тикета могут его закрыть.", color=discord.Color.red()),
                    ephemeral=True
                )
        await interaction.response.send_modal(CloseModal(td, self.assignee))
