"""
Основная логика системы опросов.
"""
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Dict, List
from datetime import datetime

from .database_surveys import *
from .ui.views import SurveyView, SurveySelectView
from .ui.embeds import *


class SurveyController:
    """Контроллер для управления прохождением опроса."""
    
    def __init__(self, survey_id: int, user: discord.Member, guild: discord.Guild):
        self.survey_id = survey_id
        self.user = user
        self.guild = guild
        self.session_id: Optional[int] = None
        self.current_question_index = 0
        self.questions: List[sqlite3.Row] = []
        self.categories: List[sqlite3.Row] = []
        self.current_question: Optional[Dict] = None
        self.current_answer: Optional[str] = None
        self.responses: Dict[int, str] = {}  # question_id -> answer
        
    async def start(self, interaction: discord.Interaction) -> bool:
        """Начинает прохождение опроса."""
        # Проверяем, не проходил ли пользователь уже этот опрос
        existing_session = get_session(self.survey_id, self.user.id)
        
        if existing_session:
            if existing_session['completed_at']:
                # Опрос уже завершен
                if interaction.response.is_done():
                    await interaction.followup.send(
                        embed=create_error_embed(
                            "Опрос уже пройден",
                            "Вы уже проходили этот опрос. Повторное прохождение невозможно."
                        ),
                        ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        embed=create_error_embed(
                            "Опрос уже пройден",
                            "Вы уже проходили этот опрос. Повторное прохождение невозможно."
                        ),
                        ephemeral=True
                    )
                return False
            else:
                # Есть незавершенная сессия - продолжаем её
                self.session_id = existing_session['id']
                saved_responses = get_session_responses(self.session_id)
                for resp in saved_responses:
                    self.responses[resp['question_id']] = resp['answer']
                self.current_question_index = existing_session['current_question']
        else:
            # Создаем новую сессию
            self.session_id = create_session(self.survey_id, self.user.id, self.guild.id)
            if not self.session_id:
                if interaction.response.is_done():
                    await interaction.followup.send(
                        embed=create_error_embed(
                            "Ошибка",
                            "Не удалось начать опрос. Попробуйте позже."
                        ),
                        ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        embed=create_error_embed(
                            "Ошибка",
                            "Не удалось начать опрос. Попробуйте позже."
                        ),
                        ephemeral=True
                    )
                return False
        
        # Загружаем вопросы
        self.questions = get_survey_questions(self.survey_id)
        
        if not self.questions:
            if interaction.response.is_done():
                await interaction.followup.send(
                    embed=create_error_embed(
                        "Опрос пуст",
                        "В этом опросе нет вопросов."
                    ),
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    embed=create_error_embed(
                        "Опрос пуст",
                        "В этом опросе нет вопросов."
                    ),
                    ephemeral=True
                )
            return False
        
        # Показываем первый вопрос (или текущий, если продолжаем)
        await self.show_question(interaction)
        return True
    
    async def show_question(self, interaction: discord.Interaction, edit: bool = False):
        """Показывает текущий вопрос."""
        if self.current_question_index >= len(self.questions):
            await self.finish_survey(interaction)
            return
        
        # Получаем текущий вопрос
        question_row = self.questions[self.current_question_index]
        self.current_question = dict(question_row)
        self.current_answer = self.responses.get(self.current_question['id'])
        
        # Получаем данные опроса
        survey = get_survey(self.survey_id)
        
        # Вычисляем прогресс
        progress = self._calculate_progress()
        
        # Создаем embed
        embed = create_survey_embed(
            survey_data=dict(survey),
            question_data=self.current_question,
            current_answer=self.current_answer,
            progress=progress
        )
        
        # Создаем view
        view = SurveyView(self)
        view.update_buttons(
            question_type=self.current_question['question_type'],
            has_prev=self.current_question_index > 0,
            has_next=self.current_question_index < len(self.questions) - 1,
            current_answer=self.current_answer
        )
        
        # Отправляем или обновляем сообщение
        if edit and interaction.message:
            await interaction.response.edit_message(embed=embed, view=view)
            view.message = interaction.message
        else:
            if interaction.response.is_done():
                msg = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
                msg = await interaction.original_response()
            view.message = msg
    
    def _calculate_progress(self) -> Dict:
        """Вычисляет прогресс прохождения."""
        return {
            'current_question': self.current_question_index + 1,
            'total_questions': len(self.questions),
            'answered': len(self.responses)
        }
    
    async def save_answer(self, interaction: discord.Interaction, answer: str, auto_advance: bool = True):
        """Сохраняет ответ на текущий вопрос."""
        # Сохраняем в память и БД
        self.responses[self.current_question['id']] = answer
        self.current_answer = answer
        save_response(self.session_id, self.current_question['id'], answer)
        
        # Обновляем прогресс в сессии
        update_session_progress(self.session_id, self.current_question_index)
        
        # Автопереход к следующему вопросу
        if auto_advance and self.current_question_index < len(self.questions) - 1:
            self.current_question_index += 1
            await self.show_question(interaction, edit=True)
        else:
            # Последний вопрос или auto_advance=False - просто обновляем
            await self.show_question(interaction, edit=True)
    
    async def prev_question(self, interaction: discord.Interaction):
        """Переход к предыдущему вопросу."""
        if self.current_question_index > 0:
            self.current_question_index -= 1
            await self.show_question(interaction, edit=True)
    
    async def skip_question(self, interaction: discord.Interaction):
        """Пропуск вопроса."""
        # Если вопрос обязательный, не даем пропустить
        if self.current_question.get('required'):
            await interaction.response.send_message(
                embed=create_error_embed(
                    "Вопрос обязателен",
                    "Этот вопрос нельзя пропустить. Пожалуйста, ответьте на него."
                ),
                ephemeral=True
            )
            return
        
        # Переходим к следующему вопросу
        self.current_question_index += 1
        await self.show_question(interaction, edit=True)
    
    async def finish_survey(self, interaction: discord.Interaction):
        """Завершает опрос."""
        # Defer сразу, так как отправка результатов может занять время
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        
        # Проверяем, что все обязательные вопросы отвечены
        unanswered_required = []
        for q in self.questions:
            if q['required'] and q['id'] not in self.responses:
                unanswered_required.append(q['question_text'])
        
        if unanswered_required:
            if interaction.response.is_done():
                await interaction.followup.send(
                    embed=create_error_embed(
                        "Не все вопросы отвечены",
                        f"Пожалуйста, ответьте на все обязательные вопросы.\n\n"
                        f"Осталось: {len(unanswered_required)}"
                    ),
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    embed=create_error_embed(
                        "Не все вопросы отвечены",
                        f"Пожалуйста, ответьте на все обязательные вопросы.\n\n"
                        f"Осталось: {len(unanswered_required)}"
                    ),
                    ephemeral=True
                )
            return
        
        # Завершаем сессию
        complete_session(self.session_id)
        
        # Получаем данные для статистики
        survey = get_survey(self.survey_id)
        session = get_session(self.survey_id, self.user.id)
        
        # Вычисляем время прохождения
        start_time = datetime.strptime(session['started_at'], "%d.%m.%Y %H:%M")
        end_time = datetime.strptime(session['completed_at'], "%d.%m.%Y %H:%M")
        duration = end_time - start_time
        duration_str = f"{duration.seconds // 60} мин"
        
        stats = {
            'answered': len(self.responses),
            'duration': duration_str
        }
        
        # Показываем сообщение о завершении
        completion_embed = create_completion_embed(dict(survey), stats, self.user)
        
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=completion_embed, view=None)
        else:
            await interaction.response.edit_message(embed=completion_embed, view=None)
        
        # Отправляем результаты в канал
        await self._send_results_to_channel(survey)
    
    async def _send_results_to_channel(self, survey):
        """Отправляет результаты в канал результатов."""
        if not survey['results_channel_id']:
            return
        
        channel = self.guild.get_channel(survey['results_channel_id'])
        if not channel:
            return
        
        # Собираем все ответы с информацией о вопросах
        responses_data = []
        for question in self.questions:
            if question['id'] in self.responses:
                responses_data.append({
                    'question_text': question['question_text'],
                    'question_type': question['question_type'],
                    'answer': self.responses[question['id']]
                })
        
        # Discord limit: максимум 25 полей в embed
        # Если ответов больше 25, разбиваем на несколько сообщений
        MAX_FIELDS = 23  # Оставляем место для заголовка с пользователем
        
        try:
            if len(responses_data) <= MAX_FIELDS:
                # Все ответы помещаются в один embed
                results_embed = create_results_embed(
                    survey_data=dict(survey),
                    responses=responses_data,
                    user=self.user if not survey['anonymous'] else None,
                    anonymous=bool(survey['anonymous'])
                )
                await channel.send(embed=results_embed)
            else:
                # Разбиваем на несколько embeds
                # Первый embed с информацией о пользователе
                first_embed = create_results_embed(
                    survey_data=dict(survey),
                    responses=responses_data[:MAX_FIELDS],
                    user=self.user if not survey['anonymous'] else None,
                    anonymous=bool(survey['anonymous']),
                    part=1,
                    total_parts=(len(responses_data) + MAX_FIELDS - 1) // MAX_FIELDS
                )
                await channel.send(embed=first_embed)
                
                # Остальные embeds с продолжением
                for i in range(MAX_FIELDS, len(responses_data), MAX_FIELDS):
                    part_num = (i // MAX_FIELDS) + 1
                    continuation_embed = create_results_continuation_embed(
                        survey_data=dict(survey),
                        responses=responses_data[i:i + MAX_FIELDS],
                        part=part_num + 1,
                        total_parts=(len(responses_data) + MAX_FIELDS - 1) // MAX_FIELDS
                    )
                    await channel.send(embed=continuation_embed)
                    
        except Exception as e:
            print(f"[SURVEYS] Ошибка отправки результатов: {e}")


class SurveysCog(commands.Cog):
    """Cog для пользовательских команд опросов."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_surveys: Dict[int, SurveyController] = {}  # user_id -> controller
    
    @app_commands.command(name="survey", description="Пройти опрос")
    async def survey_command(self, interaction: discord.Interaction):
        """Команда для начала прохождения опроса."""
        # Получаем список активных опросов
        surveys = get_guild_surveys(interaction.guild_id, status='published')
        
        if not surveys:
            await interaction.response.send_message(
                embed=create_error_embed(
                    "Нет доступных опросов",
                    "На данный момент нет активных опросов."
                ),
                ephemeral=True
            )
            return
        
        # Если опрос один, сразу начинаем его
        if len(surveys) == 1:
            await self._start_survey(interaction, surveys[0]['id'])
            return
        
        # Иначе показываем список для выбора
        view = SurveySelectView(
            surveys=[dict(s) for s in surveys],
            callback=self._start_survey
        )
        
        await interaction.response.send_message(
            embed=create_survey_list_embed([dict(s) for s in surveys], interaction.guild.name),
            view=view,
            ephemeral=True
        )
    
    async def _start_survey(self, interaction: discord.Interaction, survey_id: int):
        """Начинает прохождение опроса."""
        controller = SurveyController(survey_id, interaction.user, interaction.guild)
        self.active_surveys[interaction.user.id] = controller
        
        await controller.start(interaction)


async def setup(bot: commands.Bot):
    """Загружает cog."""
    # Инициализируем БД
    init_surveys_db()
    
    # Регистрируем persistent views для всех опубликованных опросов
    from .ui.views import StartSurveyButton
    
    with get_conn() as conn:
        # Получаем все сообщения с опросами
        messages = conn.execute("""
            SELECT sm.survey_id, sm.message_id
            FROM survey_messages sm
            JOIN surveys s ON sm.survey_id = s.id
            WHERE s.status = 'published'
        """).fetchall()
        
        for msg in messages:
            view = StartSurveyButton(msg['survey_id'], bot)
            # Регистрируем view с привязкой к message_id
            bot.add_view(view, message_id=msg['message_id'])
    
    print(f"[SURVEYS] Зарегистрировано {len(messages)} persistent views")
    
    await bot.add_cog(SurveysCog(bot))
