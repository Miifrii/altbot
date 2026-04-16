import discord
import json
import os
import time
from discord.ext import commands
from discord import app_commands
from datetime import datetime

REVIEWS_CHANNEL_ID = 1398827052047667270   # ← ID канала для отзывов
PANEL_CHANNEL_ID   = 1398827052047667270   # ← ID канала где висит кнопка

_DATA_DIR     = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_COUNTER_FILE = os.path.join(_DATA_DIR, "review_counter.json")
_cooldowns: dict[int, float] = {}
COOLDOWN = 60  # секунд между отзывами

TYPES = {
    "event":  {"label": "Ивент",          "emoji": "🎉", "color": discord.Color.green()},
    "admin":  {"label": "Администратора",  "emoji": "🛡️", "color": discord.Color.blue()},
    "thanks": {"label": "Благодарность",  "emoji": "💜", "color": discord.Color.purple()},
    "other":  {"label": "Другое",         "emoji": "📝", "color": discord.Color.light_grey()},
}

GOALS = {
    "reward":   {"label": "Позитивный", "emoji": "✅", "color": discord.Color.green()},
    "punish":   {"label": "Негативный", "emoji": "❌", "color": discord.Color.red()},
    "feedback": {"label": "Нейтральный", "emoji": "💬", "color": discord.Color.light_grey()},
}

# Типы без шага выбора тональности
NO_GOAL_TYPES = {"thanks"}


def next_review_id(review_type: str) -> int:
    try:
        with open(_COUNTER_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, ValueError):
        data = {}
    
    data[review_type] = data.get(review_type, 0) + 1
    tmp = _COUNTER_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, _COUNTER_FILE)
    return data[review_type]




async def send_review(guild: discord.Guild, channel: discord.TextChannel, review_data: dict):
    t = TYPES[review_data["type"]]
    review_id = next_review_id(review_data["type"])
    goal = GOALS.get(review_data.get("goal", "feedback"))
    embed_color = goal["color"] if goal else t["color"]

    if review_data["type"] == "thanks":
        embed = discord.Embed(
            title=f"{t['emoji']} Благодарность #{review_id}",
            color=t["color"],
            timestamp=datetime.now()
        )
        embed.add_field(name="Кому посвящается", value=review_data["target"], inline=False)
        embed.add_field(name="За что",            value=review_data["reason"], inline=False)

    elif review_data["type"] == "event":
        embed = discord.Embed(
            title=f"{t['emoji']} Отзыв на ивент #{review_id}",
            color=embed_color,
            timestamp=datetime.now()
        )
        embed.add_field(name="Дата проведения",          value=review_data["event_date"],   inline=False)
        embed.add_field(name="Оценка ивента",            value=review_data["event_rating"], inline=False)
        embed.add_field(name="Оценка ивентолога (1–10)", value=review_data["host_rating"],  inline=False)
        embed.add_field(name="Отзыв",                    value=review_data["reason"],       inline=False)

    elif review_data["type"] == "admin":
        embed = discord.Embed(
            title=f"{t['emoji']} Отзыв на администратора #{review_id}",
            color=embed_color,
            timestamp=datetime.now()
        )
        embed.add_field(name="На кого", value=review_data["target"], inline=False)
        embed.add_field(name="Причина", value=review_data["reason"], inline=False)

    else:  # other
        embed = discord.Embed(
            title=f"{t['emoji']} Отзыв #{review_id}",
            color=embed_color,
            timestamp=datetime.now()
        )
        embed.add_field(name="На что отзыв", value=review_data["target"], inline=False)
        embed.add_field(name="Отзыв",        value=review_data["reason"], inline=False)

    # Footer: тональность (кроме благодарности)
    footer_parts = []
    if review_data["type"] != "thanks" and goal:
        footer_parts.append(f"{goal['emoji']} {goal['label']}")
    if review_data["anonymous"]:
        footer_parts.append("🎭 Анонимно")

    if footer_parts:
        embed.set_footer(text=" · ".join(footer_parts))

    if not review_data["anonymous"]:
        embed.set_author(name=review_data["author_name"], icon_url=review_data["author_avatar"])

    try:
        await channel.send(embed=embed)
    except Exception as e:
        print(f"[REVIEWS] Ошибка отправки: {e}")


# ── Modals ────────────────────────────────────────────────────────────────────

def _base_review_data(review_type: str, user: discord.Member) -> dict:
    return {
        "type":          review_type,
        "author_id":     user.id,
        "author_name":   str(user),
        "author_avatar": str(user.display_avatar.url),
        "anonymous":     False,
        "goal":          "feedback",
    }


class EventModal(discord.ui.Modal, title="🎉 Отзыв на ивент"):
    event_date   = discord.ui.TextInput(label="Дата проведения", max_length=50)
    event_rating = discord.ui.TextInput(label="Как вы оцените проведённый ивент?", max_length=200)
    review_text  = discord.ui.TextInput(label="Ваш отзыв", style=discord.TextStyle.paragraph, max_length=500)
    host_rating  = discord.ui.TextInput(label="Оцените работу ивентолога от 1 до 10", max_length=10)

    def __init__(self, user: discord.Member):
        super().__init__()
        self.user = user

    async def on_submit(self, interaction: discord.Interaction):
        review_data = _base_review_data("event", self.user)
        review_data.update({
            "event_date":   self.event_date.value,
            "event_rating": self.event_rating.value,
            "reason":       self.review_text.value,
            "host_rating":  self.host_rating.value,
            "target":       "—",
        })
        await interaction.response.send_message(
            embed=discord.Embed(description="Отправить отзыв анонимно?", color=discord.Color.purple()),
            view=AnonView(review_data),
            ephemeral=True
        )


class AdminModal(discord.ui.Modal, title="🛡️ Отзыв на администратора"):
    reason = discord.ui.TextInput(label="Из-за чего решили написать отзыв?", style=discord.TextStyle.paragraph, max_length=500)
    target = discord.ui.TextInput(label="На кого вы пишете отзыв?", max_length=100)

    def __init__(self, user: discord.Member):
        super().__init__()
        self.user = user

    async def on_submit(self, interaction: discord.Interaction):
        review_data = _base_review_data("admin", self.user)
        review_data.update({
            "reason": self.reason.value,
            "target": self.target.value,
        })
        await interaction.response.send_message(
            embed=discord.Embed(description="Отправить отзыв анонимно?", color=discord.Color.purple()),
            view=AnonView(review_data),
            ephemeral=True
        )


class ThanksModal(discord.ui.Modal, title="💜 Благодарность"):
    target = discord.ui.TextInput(label="Кому посвящается?", max_length=100)
    reason = discord.ui.TextInput(label="За что?", style=discord.TextStyle.paragraph, max_length=500)

    def __init__(self, user: discord.Member):
        super().__init__()
        self.user = user

    async def on_submit(self, interaction: discord.Interaction):
        review_data = _base_review_data("thanks", self.user)
        review_data.update({
            "target": self.target.value,
            "reason": self.reason.value,
        })
        await interaction.response.send_message(
            embed=discord.Embed(description="Отправить анонимно?", color=discord.Color.purple()),
            view=AnonView(review_data),
            ephemeral=True
        )


class OtherModal(discord.ui.Modal, title="📝 Другое"):
    target = discord.ui.TextInput(label="На что пишете отзыв?", max_length=100)
    reason = discord.ui.TextInput(label="Ваш отзыв", style=discord.TextStyle.paragraph, max_length=500)

    def __init__(self, user: discord.Member):
        super().__init__()
        self.user = user

    async def on_submit(self, interaction: discord.Interaction):
        review_data = _base_review_data("other", self.user)
        review_data.update({
            "target": self.target.value,
            "reason": self.reason.value,
        })
        await interaction.response.send_message(
            embed=discord.Embed(description="Отправить отзыв анонимно?", color=discord.Color.purple()),
            view=AnonView(review_data),
            ephemeral=True
        )


MODAL_MAP = {
    "event":  EventModal,
    "admin":  AdminModal,
    "thanks": ThanksModal,
    "other":  OtherModal,
}


# ── Views ─────────────────────────────────────────────────────────────────────

class GoalView(discord.ui.View):
    def __init__(self, review_data: dict):
        super().__init__(timeout=60)
        self.review_data = review_data

    async def _send(self, interaction: discord.Interaction, goal: str):
        self.review_data["goal"] = goal
        await interaction.response.defer(ephemeral=True)
        channel = interaction.guild.get_channel(REVIEWS_CHANNEL_ID)
        if not channel:
            await interaction.followup.send(
                embed=discord.Embed(description="❌ Канал для отзывов не найден.", color=discord.Color.red()),
                ephemeral=True
            )
            return
        await send_review(interaction.guild, channel, self.review_data)
        await interaction.followup.send(
            embed=discord.Embed(description="✅ Ваш отзыв успешно отправлен!", color=discord.Color.green()),
            ephemeral=True
        )
        self.stop()

    @discord.ui.button(label="Позитивный", style=discord.ButtonStyle.secondary, emoji="✅")
    async def reward(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._send(interaction, "reward")

    @discord.ui.button(label="Негативный", style=discord.ButtonStyle.secondary, emoji="❌")
    async def punish(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._send(interaction, "punish")

    @discord.ui.button(label="Нейтральный", style=discord.ButtonStyle.secondary, emoji="💬")
    async def feedback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._send(interaction, "feedback")


class AnonView(discord.ui.View):
    def __init__(self, review_data: dict):
        super().__init__(timeout=60)
        self.review_data = review_data

    async def _proceed(self, interaction: discord.Interaction, anonymous: bool):
        self.review_data["anonymous"] = anonymous
        if self.review_data["type"] in NO_GOAL_TYPES:
            # Сразу отправляем без выбора тональности
            await interaction.response.defer(ephemeral=True)
            channel = interaction.guild.get_channel(REVIEWS_CHANNEL_ID)
            if not channel:
                await interaction.followup.send(
                    embed=discord.Embed(description="❌ Канал для отзывов не найден.", color=discord.Color.red()),
                    ephemeral=True
                )
                return
            await send_review(interaction.guild, channel, self.review_data)
            await interaction.followup.send(
                embed=discord.Embed(description="✅ Отправлено!", color=discord.Color.green()),
                ephemeral=True
            )
        else:
            await interaction.response.edit_message(
                embed=discord.Embed(description="Выберите тональность отзыва:", color=discord.Color.purple()),
                view=GoalView(self.review_data)
            )
        self.stop()

    @discord.ui.button(label="Анонимно", style=discord.ButtonStyle.secondary, emoji="🎭")
    async def anon(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._proceed(interaction, True)

    @discord.ui.button(label="Показывать автора", style=discord.ButtonStyle.primary, emoji="👤")
    async def not_anon(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._proceed(interaction, False)


class TypeSelect(discord.ui.Select):
    def __init__(self, user: discord.Member):
        self.user = user
        options = [
            discord.SelectOption(
                label=v["label"] if k in ("other", "thanks") else f"На {v['label'].lower() if k != 'admin' else v['label']}",
                value=k,
                emoji=v["emoji"]
            )
            for k, v in TYPES.items()
        ]
        super().__init__(placeholder="Выбери тип отзыва...", options=options)

    async def callback(self, interaction: discord.Interaction):
        modal_cls = MODAL_MAP.get(self.values[0])
        if modal_cls:
            await interaction.response.send_modal(modal_cls(self.user))
        else:
            await interaction.response.send_message(
                embed=discord.Embed(description="❌ Ошибка: неизвестный тип отзыва.", color=discord.Color.red()),
                ephemeral=True
            )


class TypeSelectView(discord.ui.View):
    def __init__(self, user: discord.Member):
        super().__init__(timeout=60)
        self.add_item(TypeSelect(user))


class ReviewPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Оставить отзыв", style=discord.ButtonStyle.secondary,
                       emoji="📝", custom_id="review_start")
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        now = time.time()
        remaining = COOLDOWN - (now - _cooldowns.get(user.id, 0))
        if remaining > 0:
            return await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"⏳ Подожди ещё **{int(remaining)}** сек. перед следующим отзывом.",
                    color=discord.Color.orange()
                ),
                ephemeral=True
            )
        _cooldowns[user.id] = now
        await interaction.response.send_message(
            embed=discord.Embed(description="Отзыв на что?", color=discord.Color.purple()),
            view=TypeSelectView(user),
            ephemeral=True
        )


# ── Cog ───────────────────────────────────────────────────────────────────────

class Reviews(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.add_view(ReviewPanelView())

    @app_commands.command(name="review_panel", description="Отправить панель отзывов (только для администраторов)")
    @app_commands.default_permissions(administrator=True)
    async def review_panel(self, interaction: discord.Interaction):
        channel = interaction.guild.get_channel(PANEL_CHANNEL_ID) if PANEL_CHANNEL_ID else interaction.channel

        embed = discord.Embed(
            title="> <:log_galaxy:1463258898231197696> Система отзывов ",
            description=(
                "Есть что сказать о сервере, игроках или ивентах?\n"
                "Оставь отзыв, похвали, предложи или поделись мнением.\n\n"
                "**Не стесняйся писать отзывы, они помогают стать нам лучше!** \n"
            ),
            color=discord.Color.purple()
        )

        await channel.send(embed=embed, view=ReviewPanelView())
        await interaction.response.send_message(
            embed=discord.Embed(description=f"✅ Панель отправлена в {channel.mention}", color=discord.Color.green()),
            ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Reviews(bot))
