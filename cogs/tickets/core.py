import discord
import json
import os
import time
from typing import Optional
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from .config import TICKET_CONFIG
from .controls import TicketControlView, build_ticket_embed
from database import create_ticket as db_create_ticket

_cooldowns: dict[int, float] = {}
_active_tickets: dict[int, int] = {}  # user_id -> channel_id
_channel_tickets: dict[int, int] = {}  # channel_id -> ticket_id

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
_COUNTER_FILE     = os.path.join(_DATA_DIR, "ticket_counters.json")
_ACTIVE_FILE      = os.path.join(_DATA_DIR, "active_tickets.json")
_TICKETS_FILE     = os.path.join(_DATA_DIR, "tickets_data.json")
_CHANNEL_MAP_FILE = os.path.join(_DATA_DIR, "channel_tickets.json")


def _atomic_write(path: str, data: dict, **kwargs):
    """Атомарная запись JSON через временный файл."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, **kwargs)
    os.replace(tmp, path)


def _load_active():
    global _active_tickets
    try:
        with open(_ACTIVE_FILE, "r", encoding="utf-8") as f:
            _active_tickets = {int(k): v for k, v in json.load(f).items()}
    except (FileNotFoundError, ValueError):
        _active_tickets = {}


def _save_active():
    _atomic_write(_ACTIVE_FILE, {str(k): v for k, v in _active_tickets.items()})


def _load_channel_map():
    global _channel_tickets
    try:
        with open(_CHANNEL_MAP_FILE, "r", encoding="utf-8") as f:
            _channel_tickets = {int(k): v for k, v in json.load(f).items()}
    except (FileNotFoundError, ValueError):
        _channel_tickets = {}


def _save_channel_map():
    _atomic_write(_CHANNEL_MAP_FILE, {str(k): v for k, v in _channel_tickets.items()})


def _load_ticket_data(ticket_id: int) -> Optional[dict]:
    try:
        with open(_TICKETS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get(str(ticket_id))
    except (FileNotFoundError, ValueError):
        return None


def _save_ticket_data(ticket_data: dict):
    try:
        with open(_TICKETS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, ValueError):
        data = {}
    data[str(ticket_data["id"])] = ticket_data
    _atomic_write(_TICKETS_FILE, data, ensure_ascii=False)


def next_ticket_id(ticket_type: str) -> int:
    try:
        with open(_COUNTER_FILE, "r", encoding="utf-8") as f:
            counters = json.load(f)
    except (FileNotFoundError, ValueError):
        counters = {}
    counters[ticket_type] = counters.get(ticket_type, 0) + 1
    _atomic_write(_COUNTER_FILE, counters)
    return counters[ticket_type]


def _validate_config():
    """Проверяет конфиг при старте и выводит предупреждения."""
    cfg = TICKET_CONFIG
    if not cfg.get("log_channel_id"):
        print("[TICKETS] WARNING: log_channel_id не настроен")
    if not cfg.get("panel_channel_id"):
        print("[TICKETS] WARNING: panel_channel_id не настроен")
    for t_type, t_cfg in cfg.get("types", {}).items():
        if not t_cfg.get("category_id"):
            print(f"[TICKETS] WARNING: types.{t_type}.category_id не настроен")
        if not t_cfg.get("role_ids") and not t_cfg.get("role_id"):
            print(f"[TICKETS] WARNING: types.{t_type}.role_ids не настроен")


STYLE_MAP = {
    "danger":    discord.ButtonStyle.danger,
    "primary":   discord.ButtonStyle.primary,
    "secondary": discord.ButtonStyle.secondary,
    "success":   discord.ButtonStyle.success,
}


async def create_ticket_channel(interaction: discord.Interaction, ticket_type: str,
                                 type_cfg: dict, fields: dict, extra_msg: str = None):
    """Общая логика создания канала тикета."""
    user = interaction.user
    guild = interaction.guild
    cfg = TICKET_CONFIG

    now = time.time()
    remaining = cfg["cooldown_seconds"] - (now - _cooldowns.get(user.id, 0))
    if remaining > 0:
        return await interaction.response.send_message(
            embed=discord.Embed(description=f"⏳ Подожди ещё **{int(remaining)}** сек.", color=discord.Color.orange()),
            ephemeral=True
        )

    if cfg["one_active_per_user"] and user.id in _active_tickets:
        ch = guild.get_channel(_active_tickets[user.id])
        if ch is not None:
            return await interaction.response.send_message(
                embed=discord.Embed(description=f"❌ У тебя уже есть активный тикет: {ch.mention}", color=discord.Color.red()),
                ephemeral=True
            )
        del _active_tickets[user.id]
        _save_active()

    # Резервируем слот сразу, чтобы избежать race condition
    _active_tickets[user.id] = -1
    await interaction.response.defer(ephemeral=True)

    ticket_id = next_ticket_id(ticket_type)
    _cooldowns[user.id] = now

    try:
        category = guild.get_channel(type_cfg["category_id"])
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        for role_id in type_cfg.get("role_ids", [type_cfg.get("role_id", 0)]):
            mod_role = guild.get_role(role_id)
            if mod_role:
                overwrites[mod_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        channel = await guild.create_text_channel(
            name=f"{type_cfg['name_prefix']}-{ticket_id}",
            category=category,
            overwrites=overwrites,
            reason=f"Тикет #{ticket_id} от {user}"
        )
    except Exception as e:
        # Освобождаем зарезервированный слот при ошибке
        _active_tickets.pop(user.id, None)
        _save_active()
        await interaction.followup.send(
            embed=discord.Embed(description=f"❌ Не удалось создать канал тикета: {e}", color=discord.Color.red()),
            ephemeral=True
        )
        return

    _active_tickets[user.id] = channel.id
    _save_active()

    description = fields.get("description", next(iter(fields.values()), "—"))

    ticket_data = {
        "id": ticket_id,
        "type": ticket_type,
        "type_label": type_cfg["label"],
        "author": user.mention,
        "author_id": user.id,
        "description": description,
        "details": None,
        "created_at": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "assignee_id": None,
        "avatar_url": str(user.display_avatar.url),
    }
    _save_ticket_data(ticket_data)

    _channel_tickets[channel.id] = ticket_id
    _save_channel_map()

    try:
        db_create_ticket(ticket_id, guild.id, channel.id, user.id, ticket_type)
    except Exception as e:
        print(f"[DB] Ошибка записи тикета: {e}")

    embed = build_ticket_embed(ticket_data, "открыт")
    for label, value in fields.items():
        if value and label != "description":
            embed.add_field(name=label, value=value, inline=False)

    # Сохраняем поля формы в ticket_data для восстановления при обновлении embed
    ticket_data["form_fields"] = {k: v for k, v in fields.items() if v and k != "description"}
    _save_ticket_data(ticket_data)

    view = TicketControlView(ticket_data)
    msg = await channel.send(embed=embed, view=view)
    await msg.pin()

    followup_text = f"✅ Тикет создан: {channel.mention}"
    if extra_msg:
        followup_text += f"\n\n{extra_msg}"

    await interaction.followup.send(
        embed=discord.Embed(description=followup_text, color=discord.Color.green()),
        ephemeral=True
    )


class ComplaintModal(discord.ui.Modal, title="🚨 Жалоба"):
    offender = discord.ui.TextInput(label="Игровое имя / логин нарушителя в SS14", max_length=100)
    reporter = discord.ui.TextInput(label="Ваш игровой логин SS14", max_length=100)
    round_id = discord.ui.TextInput(label="ID раунда или примерное время события", max_length=100)
    rules    = discord.ui.TextInput(label="Номера нарушенных правил", max_length=100)
    content  = discord.ui.TextInput(label="Содержание жалобы", style=discord.TextStyle.paragraph, max_length=1000)

    def __init__(self, type_cfg: dict):
        super().__init__()
        self.type_cfg = type_cfg

    async def on_submit(self, interaction: discord.Interaction):
        await create_ticket_channel(interaction, "complaint", self.type_cfg, {
            "description":                                   "",
            "Игровое имя / логин нарушителя в SS14":         self.offender.value,
            "Ваш игровой логин SS14":                        self.reporter.value,
            "ID раунда или примерное время события":         self.round_id.value,
            "Номера нарушенных правил":                      self.rules.value,
            "Содержание жалобы":                             self.content.value,
        })


class AppealModal(discord.ui.Modal, title="⚖️ Обжалование"):
    punishment = discord.ui.TextInput(label="Тип наказания (перма, джоб, мут и т.д.)", max_length=100)
    ckey       = discord.ui.TextInput(label="Ваш логин SS14", max_length=100)
    ban_date   = discord.ui.TextInput(label="Дата / время или ID бана", max_length=100)
    ban_reason = discord.ui.TextInput(label="Причина бана", max_length=200)
    content    = discord.ui.TextInput(label="Текст обжалования", style=discord.TextStyle.paragraph, max_length=1000)

    def __init__(self, type_cfg: dict):
        super().__init__()
        self.type_cfg = type_cfg

    async def on_submit(self, interaction: discord.Interaction):
        await create_ticket_channel(interaction, "appeal", self.type_cfg, {
            "description":                              "",
            "Тип наказания (перма, джоб, мут и т.д.)": self.punishment.value,
            "Ваш логин SS14":                           self.ckey.value,
            "Дата / время или ID бана":                 self.ban_date.value,
            "Причина бана":                             self.ban_reason.value,
            "Текст обжалования":                        self.content.value,
        })


class RescheduleModal(discord.ui.Modal, title="🕐 Перенос времени"):
    ckey  = discord.ui.TextInput(label="Ваш CKEY", max_length=100)
    hours = discord.ui.TextInput(label="Количество часов", max_length=50)

    def __init__(self, type_cfg: dict):
        super().__init__()
        self.type_cfg = type_cfg

    async def on_submit(self, interaction: discord.Interaction):
        await create_ticket_channel(interaction, "reschedule", self.type_cfg, {
            "description":      "",
            "Ваш CKEY":         self.ckey.value,
            "Количество часов": self.hours.value,
        }, extra_msg="📎 Не забудь прикрепить скриншот с наигранными часами в созданный тикет.")


class VerifyModal(discord.ui.Modal, title="🔞 Верификация возраста"):
    ckey = discord.ui.TextInput(label="Ваш CKEY", max_length=100)
    age  = discord.ui.TextInput(label="Ваш возраст", max_length=10)

    def __init__(self, type_cfg: dict):
        super().__init__()
        self.type_cfg = type_cfg

    async def on_submit(self, interaction: discord.Interaction):
        await create_ticket_channel(interaction, "verify", self.type_cfg, {
            "description": "",
            "Ваш CKEY":    self.ckey.value,
            "Ваш возраст": self.age.value,
        })


class OtherModal(discord.ui.Modal, title="📝 Другое"):
    ckey    = discord.ui.TextInput(label="Ваш CKEY", max_length=100)
    content = discord.ui.TextInput(label="Суть обращения", style=discord.TextStyle.paragraph, max_length=1000)

    def __init__(self, type_cfg: dict):
        super().__init__()
        self.type_cfg = type_cfg

    async def on_submit(self, interaction: discord.Interaction):
        await create_ticket_channel(interaction, "other", self.type_cfg, {
            "description":    "",
            "Ваш CKEY":       self.ckey.value,
            "Суть обращения": self.content.value,
        })


MODAL_MAP = {
    "complaint":  ComplaintModal,
    "appeal":     AppealModal,
    "reschedule": RescheduleModal,
    "verify":     VerifyModal,
    "other":      OtherModal,
}


class TicketButton(discord.ui.Button):
    def __init__(self, ticket_type: str, type_cfg: dict):
        super().__init__(
            label=type_cfg["label"],
            emoji=type_cfg["emoji"],
            style=STYLE_MAP.get(type_cfg["style"], discord.ButtonStyle.primary),
            custom_id=f"ticket_{ticket_type}"
        )
        self.ticket_type = ticket_type
        self.type_cfg = type_cfg

    async def callback(self, interaction: discord.Interaction):
        modal_cls = MODAL_MAP.get(self.ticket_type)
        if modal_cls:
            await interaction.response.send_modal(modal_cls(self.type_cfg))


class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        for t_type, t_cfg in TICKET_CONFIG["types"].items():
            self.add_item(TicketButton(t_type, t_cfg))


def build_panel_embeds() -> discord.Embed:
    p = TICKET_CONFIG["panel"]
    embed = discord.Embed(
        title=p.get("title", "🎫 Тикеты поддержки"),
        description=p.get("description", (
            "Добро пожаловать в систему обращений.\n"
            "Выбери подходящую категорию и нажми кнопку ниже — "
            "мы постараемся помочь как можно скорее.\n\u200b"
        )),
        color=p["color"]
    )
    for t_cfg in TICKET_CONFIG["types"].values():
        embed.add_field(
            name=f"{t_cfg['emoji']} {t_cfg['label']}",
            value=t_cfg.get("description", ""),
            inline=False
        )
    footer = p.get("footer", "⏳ Ответ администрации может занять некоторое время. Спасибо за терпение.")
    if footer:
        embed.set_footer(text=footer)
    return embed


class PanelEmbedModal(discord.ui.Modal, title="Редактировать панель тикетов"):
    def __init__(self):
        super().__init__()
        p = TICKET_CONFIG.get("panel", {})
        color = p.get("color", 0x9B59B6)
        self.title_input = discord.ui.TextInput(
            label="Заголовок", max_length=100,
            default=p.get("title", "🎫 Тикеты поддержки")
        )
        self.desc_input = discord.ui.TextInput(
            label="Описание", style=discord.TextStyle.paragraph,
            max_length=1000, required=False,
            default=p.get("description", "")
        )
        self.color_input = discord.ui.TextInput(
            label="Цвет (HEX, например 9B59B6)", max_length=10,
            default=f"{color:06X}"
        )
        self.footer_input = discord.ui.TextInput(
            label="Footer", max_length=200, required=False,
            default=p.get("footer", "⏳ Ответ администрации может занять некоторое время.")
        )
        self.banner_url = discord.ui.TextInput(
            label="URL баннера (необязательно)", max_length=300, required=False,
            default=p.get("banner_url", "")
        )
        self.add_item(self.title_input)
        self.add_item(self.desc_input)
        self.add_item(self.color_input)
        self.add_item(self.footer_input)
        self.add_item(self.banner_url)

    async def on_submit(self, interaction: discord.Interaction):
        p = TICKET_CONFIG.setdefault("panel", {})
        p["title"]       = self.title_input.value
        p["description"] = self.desc_input.value
        p["footer"]      = self.footer_input.value
        p["banner_url"]  = self.banner_url.value.strip()
        try:
            p["color"] = int(self.color_input.value.strip().lstrip("#"), 16)
        except ValueError:
            return await interaction.response.send_message("❌ Неверный HEX цвет.", ephemeral=True)

        channel = interaction.guild.get_channel(TICKET_CONFIG.get("panel_channel_id", 0))
        msg_id  = TICKET_CONFIG.get("panel_message_id", 0)
        updated = False
        if channel and msg_id:
            try:
                msg = await channel.fetch_message(msg_id)
                await msg.edit(embed=build_panel_embeds(), view=TicketPanelView())
                updated = True
            except discord.NotFound:
                pass

        text = "✅ Embed обновлён." if updated else "✅ Настройки сохранены. Используй /panel чтобы отправить панель заново."
        await interaction.response.send_message(
            embed=discord.Embed(description=text, color=discord.Color.green()),
            ephemeral=True
        )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        import traceback; traceback.print_exc()
        try:
            await interaction.response.send_message(f"❌ Ошибка: `{error}`", ephemeral=True)
        except Exception:
            await interaction.followup.send(f"❌ Ошибка: `{error}`", ephemeral=True)


class TicketsCore(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        _load_active()
        _load_channel_map()
        _validate_config()
        # Восстанавливаем ID сообщения панели после рестарта
        try:
            with open(os.path.join(_DATA_DIR, "panel_state.json"), "r", encoding="utf-8") as f:
                TICKET_CONFIG["panel_message_id"] = json.load(f).get("panel_message_id", 0)
        except (FileNotFoundError, ValueError):
            pass
        bot.add_view(TicketPanelView())
        bot.add_view(TicketControlView({
            "id": 0, "type": "", "type_label": "",
            "author": "", "author_id": 0, "description": "", "created_at": ""
        }))

    @app_commands.command(name="panel", description="Отправить панель тикетов (только для администраторов)")
    @app_commands.default_permissions(administrator=True)
    async def send_panel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        channel_id = TICKET_CONFIG["panel_channel_id"]
        channel = interaction.guild.get_channel(channel_id) if channel_id else interaction.channel

        # Если есть баннер — отправляем его отдельным embed сверху
        banner_url = TICKET_CONFIG.get("panel", {}).get("banner_url", "")
        if banner_url:
            banner_embed = discord.Embed(color=TICKET_CONFIG["panel"]["color"])
            banner_embed.set_image(url=banner_url)
            await channel.send(embed=banner_embed)

        msg = await channel.send(embed=build_panel_embeds(), view=TicketPanelView())
        TICKET_CONFIG["panel_message_id"] = msg.id
        _atomic_write(os.path.join(_DATA_DIR, "panel_state.json"), {"panel_message_id": msg.id}, ensure_ascii=False)
        await interaction.followup.send(
            embed=discord.Embed(description=f"✅ Панель отправлена в {channel.mention}", color=discord.Color.green()),
            ephemeral=True
        )

    @app_commands.command(name="embed_edit", description="Редактировать embed панели тикетов")
    @app_commands.default_permissions(administrator=True)
    async def embed_edit(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PanelEmbedModal())


async def setup_core(bot: commands.Bot):
    await bot.add_cog(TicketsCore(bot))
