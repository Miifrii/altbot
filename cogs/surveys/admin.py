"""
Админ-команды для управления опросами.
"""
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Literal

from .database_surveys import *
from .ui.modals import CreateSurveyModal, AddCategoryModal, AddQuestionModal
from .ui.views import QuestionTypeView, ConfirmView
from .ui.embeds import *


class SurveyAdminCog(commands.Cog):
    """Cog для админ-команд опросов."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.temp_data = {}  # Временное хранилище для создания опросов
    
    survey_admin = app_commands.Group(
        name="surveyadmin",
        description="Управление опросами",
        default_permissions=discord.Permissions(administrator=True)
    )
    
    @survey_admin.command(name="create", description="Создать новый опрос")
    @app_commands.describe(
        anonymous="Анонимный опрос (ответы без имен пользователей)",
        results_channel="Канал для отправки результатов"
    )
    async def create_survey(
        self,
        interaction: discord.Interaction,
        anonymous: bool = False,
        results_channel: Optional[discord.TextChannel] = None
    ):
        """Создает новый опрос."""
        modal = CreateSurveyModal(
            callback=lambda i, title, desc: self._create_survey_callback(
                i, title, desc, anonymous, results_channel
            )
        )
        await interaction.response.send_modal(modal)
    
    async def _create_survey_callback(
        self,
        interaction: discord.Interaction,
        title: str,
        description: str,
        anonymous: bool,
        results_channel: Optional[discord.TextChannel]
    ):
        """Callback создания опроса."""
        survey_id = create_survey(
            guild_id=interaction.guild_id,
            title=title,
            description=description,
            anonymous=anonymous,
            created_by=interaction.user.id,
            results_channel_id=results_channel.id if results_channel else None
        )
        
        embed = create_success_embed(
            "Опрос создан",
            f"**ID опроса:** {survey_id}\n"
            f"**Название:** {title}\n"
            f"**Анонимный:** {'Да' if anonymous else 'Нет'}\n\n"
            f"Используйте `/surveyadmin addquestion {survey_id}` для добавления вопросов."
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @survey_admin.command(name="addquestion", description="Добавить вопрос в опрос")
    @app_commands.describe(
        survey_id="ID опроса",
        required="Обязательный вопрос"
    )
    async def add_question(
        self,
        interaction: discord.Interaction,
        survey_id: int,
        required: bool = True
    ):
        """Добавляет вопрос в опрос."""
        # Проверяем существование опроса
        survey = get_survey(survey_id)
        if not survey or survey['guild_id'] != interaction.guild_id:
            await interaction.response.send_message(
                embed=create_error_embed("Опрос не найден", "Опрос с таким ID не существует."),
                ephemeral=True
            )
            return
        
        # Сохраняем данные для следующего шага
        self.temp_data[interaction.user.id] = {
            'survey_id': survey_id,
            'required': required
        }
        
        # Показываем выбор типа вопроса
        view = QuestionTypeView(callback=self._question_type_selected)
        
        await interaction.response.send_message(
            embed=discord.Embed(
                title="Выберите тип вопроса",
                description="**Оценка 1-10** — пользователь выбирает оценку кнопками\n"
                           "**Текстовый ответ** — пользователь вводит текст в модальном окне",
                color=discord.Color.blue()
            ),
            view=view,
            ephemeral=True
        )
    
    async def _question_type_selected(self, interaction: discord.Interaction, question_type: str):
        """Callback выбора типа вопроса."""
        temp = self.temp_data.get(interaction.user.id, {})
        temp['question_type'] = question_type
        self.temp_data[interaction.user.id] = temp
        
        # Показываем модальное окно для ввода текста вопроса
        modal = AddQuestionModal(callback=self._add_question_callback)
        await interaction.response.send_modal(modal)
    
    async def _add_question_callback(self, interaction: discord.Interaction, question_text: str):
        """Callback добавления вопроса."""
        temp = self.temp_data.pop(interaction.user.id, {})
        
        # Получаем текущее количество вопросов в опросе
        questions = get_survey_questions(temp['survey_id'])
        order_index = len(questions)
        
        question_id = add_question(
            survey_id=temp['survey_id'],
            question_text=question_text,
            question_type=temp['question_type'],
            required=temp['required'],
            order_index=order_index
        )
        
        type_label = "Оценка 1-10" if temp['question_type'] == 'rating' else "Текстовый ответ"
        
        embed = create_success_embed(
            "Вопрос добавлен",
            f"**ID вопроса:** {question_id}\n"
            f"**Тип:** {type_label}\n"
            f"**Обязательный:** {'Да' if temp['required'] else 'Нет'}\n"
            f"**Текст:** {question_text}"
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @survey_admin.command(name="publish", description="Опубликовать опрос")
    @app_commands.describe(survey_id="ID опроса")
    async def publish_survey(self, interaction: discord.Interaction, survey_id: int):
        """Публикует опрос."""
        survey = get_survey(survey_id)
        if not survey or survey['guild_id'] != interaction.guild_id:
            await interaction.response.send_message(
                embed=create_error_embed("Опрос не найден", "Опрос с таким ID не существует."),
                ephemeral=True
            )
            return
        
        if survey['status'] == 'published':
            await interaction.response.send_message(
                embed=create_error_embed("Опрос уже опубликован", "Этот опрос уже активен."),
                ephemeral=True
            )
            return
        
        # Проверяем, что есть вопросы
        questions = get_survey_questions(survey_id)
        if not questions:
            await interaction.response.send_message(
                embed=create_error_embed(
                    "Опрос пуст",
                    "Добавьте хотя бы один вопрос перед публикацией."
                ),
                ephemeral=True
            )
            return
        
        # Публикуем
        update_survey_status(survey_id, 'published')
        
        embed = create_success_embed(
            "Опрос опубликован",
            f"**{survey['title']}** теперь доступен для прохождения.\n\n"
            f"Пользователи могут начать опрос командой `/survey`"
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @survey_admin.command(name="close", description="Закрыть опрос")
    @app_commands.describe(survey_id="ID опроса")
    async def close_survey(self, interaction: discord.Interaction, survey_id: int):
        """Закрывает опрос."""
        survey = get_survey(survey_id)
        if not survey or survey['guild_id'] != interaction.guild_id:
            await interaction.response.send_message(
                embed=create_error_embed("Опрос не найден", "Опрос с таким ID не существует."),
                ephemeral=True
            )
            return
        
        update_survey_status(survey_id, 'closed')
        
        embed = create_success_embed(
            "Опрос закрыт",
            f"**{survey['title']}** больше не доступен для прохождения."
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @survey_admin.command(name="list", description="Список всех опросов")
    async def list_surveys(self, interaction: discord.Interaction):
        """Показывает список всех опросов."""
        surveys = get_guild_surveys(interaction.guild_id)
        
        embed = create_survey_list_embed(
            [dict(s) for s in surveys],
            interaction.guild.name
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @survey_admin.command(name="post", description="Опубликовать опрос в канал")
    @app_commands.describe(
        survey_id="ID опроса",
        channel="Канал для публикации опроса"
    )
    async def post_survey(
        self,
        interaction: discord.Interaction,
        survey_id: int,
        channel: discord.TextChannel
    ):
        """Публикует опрос в указанный канал с кнопкой для прохождения."""
        survey = get_survey(survey_id)
        if not survey or survey['guild_id'] != interaction.guild_id:
            await interaction.response.send_message(
                embed=create_error_embed("Опрос не найден", "Опрос с таким ID не существует."),
                ephemeral=True
            )
            return
        
        if survey['status'] != 'published':
            await interaction.response.send_message(
                embed=create_error_embed(
                    "Опрос не опубликован",
                    "Сначала опубликуйте опрос командой `/surveyadmin publish`"
                ),
                ephemeral=True
            )
            return
        
        # Получаем статистику опроса
        questions = get_survey_questions(survey_id)
        
        # Создаем embed для публикации
        from .ui.embeds import create_survey_announcement_embed
        from .ui.views import StartSurveyButton
        
        embed = create_survey_announcement_embed(
            survey_data=dict(survey),
            total_questions=len(questions)
        )
        
        # Создаем view с кнопкой
        view = StartSurveyButton(survey_id, self.bot)
        
        try:
            # Отправляем в канал
            message = await channel.send(embed=embed, view=view)
            
            # Сохраняем ID сообщения в БД
            save_survey_message(survey_id, channel.id, message.id)
            
            await interaction.response.send_message(
                embed=create_success_embed(
                    "Опрос опубликован",
                    f"Опрос **{survey['title']}** опубликован в {channel.mention}\n\n"
                    f"Пользователи могут пройти его, нажав кнопку под сообщением."
                ),
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=create_error_embed(
                    "Нет доступа",
                    f"У бота нет прав для отправки сообщений в {channel.mention}"
                ),
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                embed=create_error_embed("Ошибка", f"Не удалось опубликовать опрос: {e}"),
                ephemeral=True
            )
    
    @survey_admin.command(name="setchannel", description="Изменить канал результатов")
    @app_commands.describe(
        survey_id="ID опроса",
        results_channel="Новый канал для результатов (или оставьте пустым для отключения)"
    )
    async def set_results_channel(
        self,
        interaction: discord.Interaction,
        survey_id: int,
        results_channel: Optional[discord.TextChannel] = None
    ):
        """Изменяет канал результатов опроса."""
        survey = get_survey(survey_id)
        if not survey or survey['guild_id'] != interaction.guild_id:
            await interaction.response.send_message(
                embed=create_error_embed("Опрос не найден", "Опрос с таким ID не существует."),
                ephemeral=True
            )
            return
        
        # Обновляем канал
        update_results_channel(survey_id, results_channel.id if results_channel else None)
        
        if results_channel:
            message = f"Результаты опроса **{survey['title']}** теперь будут отправляться в {results_channel.mention}"
        else:
            message = f"Автоматическая отправка результатов для опроса **{survey['title']}** отключена."
        
        embed = create_success_embed("Канал результатов обновлен", message)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @survey_admin.command(name="delete", description="Удалить опрос")
    @app_commands.describe(survey_id="ID опроса")
    async def delete_survey(self, interaction: discord.Interaction, survey_id: int):
        """Удаляет опрос."""
        survey = get_survey(survey_id)
        if not survey or survey['guild_id'] != interaction.guild_id:
            await interaction.response.send_message(
                embed=create_error_embed("Опрос не найден", "Опрос с таким ID не существует."),
                ephemeral=True
            )
            return
        
        # Подтверждение удаления
        async def confirm_callback(i: discord.Interaction, confirmed: bool):
            if confirmed:
                with get_conn() as conn:
                    conn.execute("DELETE FROM surveys WHERE id=?", (survey_id,))
                
                await i.response.edit_message(
                    embed=create_success_embed("Опрос удален", f"Опрос **{survey['title']}** удален."),
                    view=None
                )
            else:
                await i.response.edit_message(
                    embed=create_error_embed("Отменено", "Удаление опроса отменено."),
                    view=None
                )
        
        view = ConfirmView(callback=confirm_callback)
        
        await interaction.response.send_message(
            embed=discord.Embed(
                title="⚠️ Подтверждение удаления",
                description=f"Вы уверены, что хотите удалить опрос **{survey['title']}**?\n\n"
                           f"Это действие необратимо. Все ответы будут удалены.",
                color=discord.Color.orange()
            ),
            view=view,
            ephemeral=True
        )


async def setup(bot: commands.Bot):
    """Загружает cog."""
    await bot.add_cog(SurveyAdminCog(bot))
