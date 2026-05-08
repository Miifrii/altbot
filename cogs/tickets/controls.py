import discord
import json
from .transcript import generate_transcript
from .config import TICKET_CONFIG
from .permissions import is_ticket_moderator
from database import claim_ticket as db_claim_ticket, close_ticket as db_close_ticket, get_ticket_by_channel


def build_ticket_embed(ticket_data: dict, status: str, assignee: discord.Member = None) -> discord.Embed:
    colors = {"открыт": discord.Color.purple(), "в работе": discord.Color.yellow(), "закрыт": discord.Color.red()}
    embed = discord.Embed(title=f"🎫 Тикет #{ticket_data['id']}", color=colors.get(status, discord.Color.blurple()))
    embed.add_field(name="Тип",    value=ticket_data["type_label"], inline=True)
    embed.add_field(name="Статус", value=status,                    inline=True)
    embed.add_field(name="Автор",  value=ticket_data["author"],     inline=True)
    if ticket_data.get("description"):
        embed.add_field(name="Описание", value=ticket_data["description"], inline=False)
    if ticket_data.get("details"):
        embed.add_field(name="Детали", value=ticket_data["details"], inline=False)
    for label, value in ticket_data.get("form_fields", {}).items():
        if value:
            embed.add_field(name=label, value=value, inline=False)
    if assignee:
        embed.add_field(name="Ответственный", value=assignee.mention, inline=True)
    if ticket_data.get("avatar_url"):
        embed.set_thumbnail(url=ticket_data["avatar_url"])
    embed.set_footer(text=f"Создан: {ticket_data['created_at']}")
    return embed


async def _is_mod(interaction: discord.Interaction, ticket_data: dict = None) -> bool:
    """Администратор — полный доступ. Иначе проверяем роли из новой системы управления."""
    return await is_ticket_moderator(interaction, ticket_data)


class CloseModal(discord.ui.Modal, title="Закрытие тикета"):
    reason = discord.ui.TextInput(label="Причина закрытия", style=discord.TextStyle.paragraph, max_length=500)

    def __init__(self, ticket_data: dict, assignee: discord.Member = None):
        super().__init__()
        self.ticket_data = ticket_data
        self.assignee = assignee

    async def on_submit(self, interaction: discord.Interaction):
        # ВАЖНО: Загружаем актуальные данные из БД перед созданием view
        try:
            row = get_ticket_by_channel(interaction.channel.id)
            if row:
                ticket_id = row["id"]
                t_type = row["type"]
                user_id = row["user_id"]
                
                # Получаем конфиг типа тикета
                from .config import TICKET_CONFIG
                t_cfg = TICKET_CONFIG.get("types", {}).get(t_type, {})
                type_label = t_cfg.get("label", t_type)
                
                # Получаем пользователя
                author = interaction.guild.get_member(user_id)
                author_mention = author.mention if author else f"<@{user_id}>"
                
                # Парсим form_data из JSON
                form_fields = {}
                if row["form_data"]:
                    try:
                        form_fields = json.loads(row["form_data"])
                    except json.JSONDecodeError:
                        pass
                
                # Обновляем ticket_data актуальными данными из БД
                self.ticket_data = {
                    "id": ticket_id,
                    "type": t_type,
                    "type_label": type_label,
                    "author": author_mention,
                    "author_id": user_id,
                    "description": self.ticket_data.get("description", ""),
                    "form_fields": form_fields,
                    "created_at": row["created_at"],
                    "avatar_url": str(author.display_avatar.url) if author else None,
                }
        except Exception as e:
            print(f"[CLOSE_MODAL] Ошибка загрузки данных: {e}")
        
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
        ticket_id = 0
        type_label = "—"
        author_mention = "—"
        
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
            else:
                # Fallback на данные из ticket_data
                ticket_id = self.ticket_data.get("id", 0)
                type_label = self.ticket_data.get("type_label", "—")
                author_mention = self.ticket_data.get("author", "—")
        except Exception as e:
            print(f"[LOG] Ошибка получения данных тикета: {e}")
            # Fallback на данные из ticket_data
            ticket_id = self.ticket_data.get("id", 0)
            type_label = self.ticket_data.get("type_label", "—")
            author_mention = self.ticket_data.get("author", "—")

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
        self.ticket_data["assignee_id"] = new_assignee.id
        self.control_view.assignee = new_assignee
        embed = build_ticket_embed(self.ticket_data, "в работе", new_assignee)
        async for msg in interaction.channel.history(limit=10, oldest_first=True):
            if msg.author == interaction.guild.me and msg.embeds:
                await msg.edit(embed=embed)
                break
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
    def __init__(self, ticket_data: dict):
        super().__init__(timeout=None)
        self.ticket_data = ticket_data
        self.assignee: discord.Member = None

    def _get_data(self, interaction: discord.Interaction) -> dict:
        # Всегда пытаемся загрузить актуальные данные из БД
        try:
            row = get_ticket_by_channel(interaction.channel.id)
            if row:
                ticket_id = row["id"]
                t_type = row["type"]
                t_cfg = TICKET_CONFIG.get("types", {}).get(t_type, {})
                
                # Парсим form_data из JSON
                form_fields = {}
                if row["form_data"]:
                    try:
                        form_fields = json.loads(row["form_data"])
                    except json.JSONDecodeError:
                        pass
                
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
                    "description": self.ticket_data.get("description", ""),
                    "form_fields": form_fields,
                    "created_at": row["created_at"],
                    "avatar_url": str(author.display_avatar.url) if author else None,
                }
        except Exception as e:
            print(f"[TICKET] Ошибка загрузки ticket_data из БД: {e}")

        return self.ticket_data

    @discord.ui.button(label="Взять тикет", style=discord.ButtonStyle.success, emoji="🙋", custom_id="ticket_take")
    async def take(self, interaction: discord.Interaction, button: discord.ui.Button):
        td = self._get_data(interaction)
        if not await _is_mod(interaction, td):
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
        embed = build_ticket_embed(td, "в работе", self.assignee)
        await interaction.message.edit(embed=embed, view=self)
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
        if not await _is_mod(interaction, td):
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
        if not await _is_mod(interaction, td):
            if td.get("author_id") != interaction.user.id:
                return await interaction.response.send_message(
                    embed=discord.Embed(description="❌ Только модераторы или автор тикета могут его закрыть.", color=discord.Color.red()),
                    ephemeral=True
                )
        await interaction.response.send_modal(CloseModal(td, self.assignee))
