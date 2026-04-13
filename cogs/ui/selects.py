import discord

WARN_REASONS = [
    ("Спам", "Массовая отправка сообщений"),
    ("Оскорбления", "Оскорбление участников сервера"),
    ("Реклама", "Несанкционированная реклама"),
    ("NSFW", "Неприемлемый контент"),
    ("Другое", "Другая причина"),
]


class ReasonSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=label, description=desc)
            for label, desc in WARN_REASONS
        ]
        super().__init__(
            placeholder="Выбери причину...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.reason = self.values[0]
        self.view.stop()
        await interaction.response.defer()


class ReasonView(discord.ui.View):
    """Выпадающий список для выбора причины наказания"""

    def __init__(self, author: discord.Member, timeout: float = 30):
        super().__init__(timeout=timeout)
        self.author = author
        self.reason: str | None = None
        self.add_item(ReasonSelect())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.author:
            await interaction.response.send_message(
                "Это не твой список!", ephemeral=True
            )
            return False
        return True
