import discord


class ConfirmView(discord.ui.View):
    """Кнопки подтверждения действия (Да / Отмена)"""

    def __init__(self, author: discord.Member, timeout: float = 30):
        super().__init__(timeout=timeout)
        self.author = author
        self.confirmed: bool | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.author:
            await interaction.response.send_message(
                "Это не твоя кнопка!", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Подтвердить", style=discord.ButtonStyle.danger, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Отмена", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = False
        self.stop()
        await interaction.response.send_message("Действие отменено.", ephemeral=True)
