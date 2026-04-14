import discord
from .transcript import generate_transcript
from .config import TICKET_CONFIG
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

        if log_channel_id:
            log_channel = interaction.guild.get_channel(log_channel_id)
            if log_channel:
                embed = discord.Embed(title=f"📋 Тикет #{self.ticket_data['id']} закрыт", color=discord.Color.red())
                embed.add_field(name="Тип",     value=self.ticket_data.get("type_label", "—"), inline=True)
                embed.add_field(name="Автор",   value=self.ticket_data.get("author", "—"),     inline=True)
                embed.add_field(name="Закрыл",  value=interaction.user.mention,                inline=True)
                embed.add_field(name="Причина", value=self.reason,                             inline=False)
                try:
                    if transcript:
                        await log_channel.send(embed=embed, file=transcript)
                    else:
                        await log_channel.send(embed=embed)
                except Exception:
                    pass

        from .core import _active_tickets, _save_active, _channel_tickets, _save_channel_map
        author_id = self.ticket_data.get("author_id")
        if author_id and _active_tickets.get(author_id) == channel.id:
            del _active_tickets[author_id]
            _save_active()
        if channel.id in _channel_tickets:
            del _channel_tickets[channel.id]
            _save_channel_map()

        try:
            row = get_ticket_by_channel(channel.id)
            if row:
                db_close_ticket(row["id"], interaction.user.id, self.reason)
        except Exception as e:
            print(f"[DB] Ошибка close_ticket: {e}")

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
        if self.ticket_data.get("id") == 0:
            import json
            from .core import _TICKETS_FILE, _channel_tickets, _load_channel_map
            try:
                _load_channel_map()
                ticket_id = _channel_tickets.get(interaction.channel.id)
                if ticket_id is not None:
                    with open(_TICKETS_FILE, "r", encoding="utf-8") as f:
                        all_tickets = json.load(f)
                    td = all_tickets.get(str(ticket_id))
                    if td:
                        self.ticket_data = td
            except Exception as e:
                print(f"[TICKET] Ошибка загрузки ticket_data: {e}")
        return self.ticket_data

    @discord.ui.button(label="Взять тикет", style=discord.ButtonStyle.success, emoji="🙋", custom_id="ticket_take")
    async def take(self, interaction: discord.Interaction, button: discord.ui.Button):
        td = self._get_data(interaction)
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
        if not _is_mod(interaction, td):
            if td.get("author_id") != interaction.user.id:
                return await interaction.response.send_message(
                    embed=discord.Embed(description="❌ Только модераторы или автор тикета могут его закрыть.", color=discord.Color.red()),
                    ephemeral=True
                )
        await interaction.response.send_modal(CloseModal(td, self.assignee))
