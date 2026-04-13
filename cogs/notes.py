import json
import os
import discord
from discord.ext import commands
from datetime import datetime

NOTES_FILE = "data/notes.json"
PER_PAGE = 5


def load_notes() -> dict:
    if not os.path.exists(NOTES_FILE):
        return {}
    with open(NOTES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_notes(data: dict):
    with open(NOTES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def build_embed(member: discord.Member, notes: list, page: int, total_pages: int) -> discord.Embed:
    embed = discord.Embed(
        title=f"📋 Заметки — {member.display_name}",
        color=discord.Color.blurple()
    )
    embed.set_thumbnail(url=member.display_avatar.url)

    start = page * PER_PAGE
    for note in notes[start:start + PER_PAGE]:
        embed.add_field(
            name=f"#{note['id']} • {note['date']}",
            value=f"{note['text']}\n*— {note['author']}*",
            inline=False
        )

    embed.set_footer(text=f"Страница {page + 1}/{total_pages} • Всего заметок: {len(notes)}")
    return embed


class NotesView(discord.ui.View):
    def __init__(self, member: discord.Member, notes: list, page: int = 0):
        super().__init__(timeout=60)
        self.member = member
        self.notes = notes
        self.page = page
        self.total_pages = (len(notes) - 1) // PER_PAGE + 1
        self._update_buttons()

    def _update_buttons(self):
        self.prev_btn.disabled = self.page == 0
        self.next_btn.disabled = self.page >= self.total_pages - 1

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        self._update_buttons()
        await interaction.response.edit_message(
            embed=build_embed(self.member, self.notes, self.page, self.total_pages),
            view=self
        )

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        self._update_buttons()
        await interaction.response.edit_message(
            embed=build_embed(self.member, self.notes, self.page, self.total_pages),
            view=self
        )


class Notes(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.group(name="note", invoke_without_command=True)
    async def note(self, ctx: commands.Context):
        embed = discord.Embed(
            title="📝 Система заметок",
            description=(
                "`!note add @user текст` — добавить заметку\n"
                "`!note list @user` — посмотреть заметки\n"
                "`!note remove @user <id>` — удалить заметку"
            ),
            color=discord.Color.blurple()
        )
        await ctx.send(embed=embed)

    @note.command(name="add")
    @commands.has_permissions(moderate_members=True)
    async def note_add(self, ctx: commands.Context, member: discord.Member, *, text: str):
        data = load_notes()
        key = str(member.id)
        if key not in data:
            data[key] = []

        note_id = len(data[key]) + 1
        data[key].append({
            "id": note_id,
            "text": text,
            "author": str(ctx.author),
            "author_id": ctx.author.id,
            "date": datetime.now().strftime("%d.%m.%Y %H:%M")
        })
        save_notes(data)

        embed = discord.Embed(title="📝 Заметка добавлена", color=discord.Color.green())
        embed.add_field(name="Участник", value=member.mention, inline=True)
        embed.add_field(name="ID заметки", value=f"`#{note_id}`", inline=True)
        embed.add_field(name="Текст", value=text, inline=False)
        embed.set_footer(text=f"Добавил: {ctx.author} • {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        await ctx.send(embed=embed)

    @note.command(name="list")
    async def note_list(self, ctx: commands.Context, member: discord.Member):
        data = load_notes()
        notes = data.get(str(member.id), [])

        if not notes:
            return await ctx.send(embed=discord.Embed(
                description=f"У {member.mention} нет заметок.",
                color=discord.Color.light_grey()
            ))

        total_pages = (len(notes) - 1) // PER_PAGE + 1
        embed = build_embed(member, notes, 0, total_pages)

        if total_pages > 1:
            await ctx.send(embed=embed, view=NotesView(member, notes))
        else:
            await ctx.send(embed=embed)

    @note.command(name="remove")
    @commands.has_permissions(moderate_members=True)
    async def note_remove(self, ctx: commands.Context, member: discord.Member, note_id: int):
        data = load_notes()
        key = str(member.id)
        notes = data.get(key, [])

        note = next((n for n in notes if n["id"] == note_id), None)
        if not note:
            return await ctx.send(embed=discord.Embed(
                description=f"Заметка `#{note_id}` не найдена.",
                color=discord.Color.red()
            ))

        notes.remove(note)
        data[key] = notes
        save_notes(data)

        await ctx.send(embed=discord.Embed(
            description=f"Заметка `#{note_id}` для {member.mention} удалена.",
            color=discord.Color.green()
        ))


async def setup(bot: commands.Bot):
    await bot.add_cog(Notes(bot))
