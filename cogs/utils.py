import io
import discord
from discord.ext import commands
from discord import app_commands


class Utils(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="members_list", description="Получить список всех участников сервера (только для администраторов)")
    @app_commands.default_permissions(administrator=True)
    async def members_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        members = interaction.guild.members
        lines = [f"{m.display_name} ({m.name})" for m in sorted(members, key=lambda m: m.display_name.lower())]
        content = f"Участников: {len(lines)}\n\n" + "\n".join(lines)

        file = discord.File(
            io.BytesIO(content.encode("utf-8")),
            filename=f"members_{interaction.guild.name}.txt"
        )
        try:
            await interaction.user.send(file=file)
            await interaction.followup.send(
                embed=discord.Embed(description="✅ Список отправлен в личку.", color=discord.Color.green()),
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.followup.send(
                embed=discord.Embed(description="❌ Не удалось отправить в личку — у тебя закрыты ЛС.", color=discord.Color.red()),
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Utils(bot))
