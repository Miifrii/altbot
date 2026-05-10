"""
Views и кнопки для системы опросов.
"""
import discord
from typing import Dict, List, Optional, Callable
from .modals import TextAnswerModal


class SurveyView(discord.ui.View):
    """View для прохождения опроса."""
    
    def __init__(self, survey_controller, timeout: int = 600):
        super().__init__(timeout=timeout)
        self.controller = survey_controller
        self.message: Optional[discord.Message] = None
    
    async def on_timeout(self):
        """Обработка таймаута."""
        if self.message:
            try:
                for item in self.children:
                    item.disabled = True
                await self.message.edit(view=self)
            except:
                pass
    
    def update_buttons(self, question_type: str, has_prev: bool, has_next: bool, 
                      current_answer: Optional[str]):
        """Обновляет кнопки в зависимости от состояния."""
        self.clear_items()
        
        # Кнопки оценки 1-10 для rating вопросов
        if question_type == 'rating':
            for i in range(1, 11):
                button = RatingButton(i, current_answer == str(i))
                self.add_item(button)
        
        # Кнопка текстового ответа для text вопросов
        elif question_type == 'text':
            button = TextAnswerButton()
            self.add_item(button)
        
        # Навигация
        nav_row = []
        
        if has_prev:
            prev_btn = discord.ui.Button(
                label="◀ Назад",
                style=discord.ButtonStyle.secondary,
                custom_id="survey_prev"
            )
            prev_btn.callback = self.prev_question
            nav_row.append(prev_btn)
        
        # Кнопка завершения только на последнем вопросе
        if not has_next:
            finish_btn = discord.ui.Button(
                label="✅ Завершить",
                style=discord.ButtonStyle.success,
                custom_id="survey_finish",
                disabled=current_answer is None
            )
            finish_btn.callback = self.finish_survey
            nav_row.append(finish_btn)
        
        # Кнопка пропуска (если вопрос не обязательный)
        skip_btn = discord.ui.Button(
            label="⏭ Пропустить",
            style=discord.ButtonStyle.secondary,
            custom_id="survey_skip"
        )
        skip_btn.callback = self.skip_question
        nav_row.append(skip_btn)
        
        for btn in nav_row:
            self.add_item(btn)
    
    async def prev_question(self, interaction: discord.Interaction):
        """Переход к предыдущему вопросу."""
        await self.controller.prev_question(interaction)
    
    async def skip_question(self, interaction: discord.Interaction):
        """Пропуск вопроса."""
        await self.controller.skip_question(interaction)
    
    async def finish_survey(self, interaction: discord.Interaction):
        """Завершение опроса."""
        await self.controller.finish_survey(interaction)


class RatingButton(discord.ui.Button):
    """Кнопка оценки от 1 до 10."""
    
    def __init__(self, rating: int, selected: bool = False):
        style = discord.ButtonStyle.primary if selected else discord.ButtonStyle.secondary
        super().__init__(
            label=str(rating),
            style=style,
            custom_id=f"rating_{rating}"
        )
        self.rating = rating
    
    async def callback(self, interaction: discord.Interaction):
        """Обработка выбора оценки."""
        view: SurveyView = self.view
        await view.controller.save_answer(interaction, str(self.rating))


class TextAnswerButton(discord.ui.Button):
    """Кнопка для открытия модального окна текстового ответа."""
    
    def __init__(self):
        super().__init__(
            label="✍ Ответить",
            style=discord.ButtonStyle.primary,
            custom_id="text_answer",
            row=2
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Открытие модального окна."""
        view: SurveyView = self.view
        controller = view.controller
        
        modal = TextAnswerModal(
            question_text=controller.current_question['question_text'],
            current_answer=controller.current_answer,
            callback=controller.save_answer
        )
        await interaction.response.send_modal(modal)


class SurveySelectView(discord.ui.View):
    """View для выбора опроса."""
    
    def __init__(self, surveys: List[Dict], callback: Callable):
        super().__init__(timeout=60)
        self.callback_func = callback
        
        # Создаем select menu с опросами
        options = []
        for survey in surveys[:25]:  # Discord limit
            options.append(
                discord.SelectOption(
                    label=survey['title'][:100],
                    description=f"ID: {survey['id']} | Статус: {survey['status']}",
                    value=str(survey['id']),
                    emoji="📋"
                )
            )
        
        select = discord.ui.Select(
            placeholder="Выберите опрос...",
            options=options,
            custom_id="survey_select"
        )
        select.callback = self.on_select
        self.add_item(select)
    
    async def on_select(self, interaction: discord.Interaction):
        """Обработка выбора опроса."""
        survey_id = int(self.values[0])
        await self.callback_func(interaction, survey_id)


class ConfirmView(discord.ui.View):
    """View для подтверждения действия."""
    
    def __init__(self, callback: Callable, timeout: int = 30):
        super().__init__(timeout=timeout)
        self.callback_func = callback
        self.confirmed = False
    
    @discord.ui.button(label="✅ Подтвердить", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Подтверждение."""
        self.confirmed = True
        await self.callback_func(interaction, True)
        self.stop()
    
    @discord.ui.button(label="❌ Отмена", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Отмена."""
        await self.callback_func(interaction, False)
        self.stop()


class QuestionTypeSelect(discord.ui.Select):
    """Select для выбора типа вопроса."""
    
    def __init__(self, callback: Callable):
        options = [
            discord.SelectOption(
                label="Оценка 1-10",
                description="Пользователь выбирает оценку от 1 до 10",
                value="rating",
                emoji="⭐"
            ),
            discord.SelectOption(
                label="Текстовый ответ",
                description="Пользователь вводит текст",
                value="text",
                emoji="✍"
            )
        ]
        super().__init__(
            placeholder="Выберите тип вопроса...",
            options=options,
            custom_id="question_type_select"
        )
        self.callback_func = callback
    
    async def callback(self, interaction: discord.Interaction):
        """Обработка выбора типа."""
        await self.callback_func(interaction, self.values[0])


class QuestionTypeView(discord.ui.View):
    """View для выбора типа вопроса."""
    
    def __init__(self, callback: Callable):
        super().__init__(timeout=60)
        self.add_item(QuestionTypeSelect(callback))


class StartSurveyButton(discord.ui.View):
    """Persistent view с кнопкой для начала опроса."""
    
    def __init__(self, survey_id: int, bot):
        super().__init__(timeout=None)  # Persistent view
        self.survey_id = survey_id
        self.bot = bot
        
        # Добавляем кнопку
        button = discord.ui.Button(
            label="📋 Пройти опрос",
            style=discord.ButtonStyle.primary,
            custom_id=f"start_survey_{survey_id}"
        )
        button.callback = self.start_survey
        self.add_item(button)
    
    async def start_survey(self, interaction: discord.Interaction):
        """Начинает прохождение опроса."""
        print(f"[SURVEYS] Пользователь {interaction.user.id} нажал кнопку опроса {self.survey_id}")
        
        # Defer сразу, чтобы Discord знал что мы обрабатываем запрос
        try:
            await interaction.response.defer(ephemeral=True)
        except discord.errors.NotFound:
            # Interaction истек (старое сообщение)
            print(f"[SURVEYS] Interaction истек для опроса {self.survey_id}. Нужно переотправить сообщение.")
            # Не можем ответить, так как interaction недействителен
            return
        except Exception as e:
            print(f"[SURVEYS] Ошибка defer: {e}")
            return
        
        from ..database_surveys import get_survey
        from ..core import SurveyController
        
        # Проверяем статус опроса
        survey = get_survey(self.survey_id)
        if not survey:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ Опрос не найден",
                    description="Этот опрос был удален.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            return
        
        if survey['status'] != 'published':
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ Опрос недоступен",
                    description="Этот опрос больше не активен.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            return
        
        # Создаем контроллер и начинаем опрос
        controller = SurveyController(self.survey_id, interaction.user, interaction.guild)
        await controller.start(interaction)
