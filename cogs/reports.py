import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

REPORT_CHANNEL_ID = 1348258343629750373  # <- вставь ID канала для репортов


class ReportModal(discord.ui.Modal, title="Репорт на пользователя"):
    description = discord.ui.TextInput(
        label="Что сделал?",
        placeholder="Опиши нарушение...",
        style=discord.TextStyle.paragraph,
        max_length=1000
    )

    def __init__(self, target: discord.Member):
        super().__init__()
        self.target = target

    async def on_submit(self, interaction: discord.Interaction):
        channel = interaction.client.get_channel(REPORT_CHANNEL_ID)
        if not channel:
            return await interaction.response.send_message(
                embed=discord.Embed(description="❌ Канал для репортов не найден. Обратись к администратору.", color=discord.Color.red()),
                ephemeral=True
            )

        embed = discord.Embed(title="🚨 Новый репорт", color=discord.Color.red(), timestamp=datetime.now())
        embed.add_field(name="Нарушитель",    value=self.target.mention,          inline=True)
        embed.add_field(name="Автор репорта", value=interaction.user.mention,     inline=True)
        embed.add_field(name="Канал",         value=interaction.channel.mention,  inline=True)
        embed.add_field(name="Описание",      value=self.description.value,       inline=False)
        embed.set_thumbnail(url=self.target.display_avatar.url)
        embed.set_footer(text=f"ID нарушителя: {self.target.id}")

        await channel.send(embed=embed)
        await interaction.response.send_message(
            embed=discord.Embed(description="✅ Репорт отправлен. Спасибо!", color=discord.Color.green()),
            ephemeral=True
        )


class UserSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Выбери нарушителя...")
    async def select_user(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        target = select.values[0]
        if target == interaction.user:
            return await interaction.response.send_message(
                embed=discord.Embed(description="❌ Нельзя репортить самого себя.", color=discord.Color.red()),
                ephemeral=True
            )
        if target.bot:
            return await interaction.response.send_message(
                embed=discord.Embed(description="❌ Нельзя репортить бота.", color=discord.Color.red()),
                ephemeral=True
            )
        await interaction.response.send_modal(ReportModal(target))
        self.stop()


class Reports(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="report", description="Пожаловаться на пользователя")
    async def report(self, interaction: discord.Interaction):
        embed = discord.Embed(
            description="Выбери пользователя, на которого хочешь пожаловаться.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, view=UserSelectView(), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Reports(bot))
