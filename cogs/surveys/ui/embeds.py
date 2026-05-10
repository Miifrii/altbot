"""
Генерация embeds для системы опросов.
"""
import discord
from typing import Optional, Dict, Any, List


def create_survey_embed(survey_data: Dict, question_data: Dict,
                       current_answer: Optional[str], progress: Dict) -> discord.Embed:
    """
    Создает embed для текущего вопроса опроса.
    
    Args:
        survey_data: Данные опроса
        question_data: Данные вопроса
        current_answer: Текущий ответ пользователя
        progress: Прогресс прохождения
    """
    embed = discord.Embed(
        title=f"📋 {survey_data['title']}",
        color=discord.Color.blue()
    )
    
    # Номер вопроса
    question_info = f"**Вопрос {progress['current_question']}/{progress['total_questions']}**"
    embed.add_field(name="", value=question_info, inline=False)
    
    # Текст вопроса
    embed.add_field(name="❓ Вопрос", value=question_data['question_text'], inline=False)
    
    # Текущий ответ
    if current_answer:
        if question_data['question_type'] == 'rating':
            answer_display = f"**{current_answer}/10** ⭐"
        else:
            answer_display = f"```{current_answer[:100]}{'...' if len(current_answer) > 100 else ''}```"
        embed.add_field(name="✅ Ваш ответ", value=answer_display, inline=False)
    else:
        embed.add_field(name="⏳ Ответ", value="*Не выбран*", inline=False)
    
    # Прогресс-бар
    progress_percent = (progress['answered'] / progress['total_questions']) * 100
    progress_bar = create_progress_bar(progress_percent)
    embed.add_field(
        name="📊 Прогресс",
        value=f"{progress_bar} {progress_percent:.0f}%\n{progress['answered']}/{progress['total_questions']} вопросов",
        inline=False
    )
    
    # Footer
    if survey_data.get('anonymous'):
        embed.set_footer(text="🔒 Анонимный опрос • Ваши данные не будут раскрыты")
    else:
        embed.set_footer(text="📝 Опрос проекта")
    
    return embed


def create_progress_bar(percent: float, length: int = 10) -> str:
    """Создает визуальный прогресс-бар."""
    filled = int((percent / 100) * length)
    empty = length - filled
    return "█" * filled + "░" * empty


def create_completion_embed(survey_data: Dict, stats: Dict, user: discord.Member) -> discord.Embed:
    """Создает embed завершения опроса."""
    embed = discord.Embed(
        title="✅ Опрос завершен!",
        description=f"Спасибо за прохождение опроса **{survey_data['title']}**!",
        color=discord.Color.green()
    )
    
    if not survey_data.get('anonymous'):
        embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    
    embed.set_footer(text="Ваши ответы сохранены и отправлены администрации")
    
    return embed


def create_results_embed(survey_data: Dict, responses: List[Dict], 
                        user: Optional[discord.Member], anonymous: bool,
                        part: int = 1, total_parts: int = 1) -> discord.Embed:
    """Создает embed с результатами для канала результатов."""
    title = f"📋 Результаты опроса: {survey_data['title']}"
    if total_parts > 1:
        title += f" (Часть {part}/{total_parts})"
    
    embed = discord.Embed(
        title=title,
        color=discord.Color.blue(),
        timestamp=discord.utils.utcnow()
    )
    
    if not anonymous and user:
        embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
        embed.add_field(name="👤 Пользователь", value=f"{user.mention} (ID: {user.id})", inline=True)
    else:
        embed.set_author(name="Анонимный пользователь")
        embed.add_field(name="👤 Пользователь", value="🔒 Анонимно", inline=True)
    
    # Добавляем ответы
    for response in responses:
        # Форматируем ответ
        if response['question_type'] == 'rating':
            answer_text = f"⭐ **{response['answer']}/10**"
        else:
            answer_text = response['answer'][:1024]  # Discord limit
        
        embed.add_field(
            name=f"❓ {response['question_text'][:256]}",
            value=answer_text,
            inline=False
        )
    
    if total_parts > 1 and part == 1:
        embed.set_footer(text=f"Продолжение в следующем сообщении...")
    
    return embed


def create_results_continuation_embed(survey_data: Dict, responses: List[Dict],
                                      part: int, total_parts: int) -> discord.Embed:
    """Создает embed с продолжением результатов."""
    embed = discord.Embed(
        title=f"📋 Результаты опроса: {survey_data['title']} (Часть {part}/{total_parts})",
        color=discord.Color.blue()
    )
    
    # Добавляем ответы
    for response in responses:
        # Форматируем ответ
        if response['question_type'] == 'rating':
            answer_text = f"⭐ **{response['answer']}/10**"
        else:
            answer_text = response['answer'][:1024]  # Discord limit
        
        embed.add_field(
            name=f"❓ {response['question_text'][:256]}",
            value=answer_text,
            inline=False
        )
    
    if part < total_parts:
        embed.set_footer(text=f"Продолжение в следующем сообщении...")
    
    return embed


def create_stats_embed(survey_data: Dict, stats: Dict) -> discord.Embed:
    """Создает embed со статистикой опроса."""
    embed = discord.Embed(
        title=f"📊 Статистика: {survey_data['title']}",
        color=discord.Color.gold()
    )
    
    # Общая статистика
    embed.add_field(
        name="📈 Общая статистика",
        value=f"Начали: **{stats['total_started']}**\n"
              f"Завершили: **{stats['total_completed']}**\n"
              f"Процент завершения: **{stats['completion_rate']}%**",
        inline=False
    )
    
    return embed


def create_question_stats_embed(question_text: str, stats: Dict, question_type: str) -> discord.Embed:
    """Создает embed со статистикой по вопросу."""
    embed = discord.Embed(
        title="📊 Статистика вопроса",
        description=f"**{question_text}**",
        color=discord.Color.blue()
    )
    
    embed.add_field(name="📝 Всего ответов", value=str(stats['total']), inline=True)
    
    if question_type == 'rating' and 'average' in stats:
        embed.add_field(name="⭐ Средняя оценка", value=f"{stats['average']}/10", inline=True)
        
        # Распределение оценок
        distribution_text = ""
        for rating in range(1, 11):
            count = stats['distribution'].get(str(rating), 0)
            percent = (count / stats['total'] * 100) if stats['total'] > 0 else 0
            bar = create_progress_bar(percent, 15)
            distribution_text += f"**{rating}** — {bar} {percent:.1f}% ({count})\n"
        
        embed.add_field(name="📊 Распределение оценок", value=distribution_text, inline=False)
    else:
        # Для текстовых ответов показываем топ-5
        sorted_answers = sorted(stats['distribution'].items(), key=lambda x: x[1], reverse=True)[:5]
        if sorted_answers:
            top_text = ""
            for answer, count in sorted_answers:
                percent = (count / stats['total'] * 100) if stats['total'] > 0 else 0
                top_text += f"• {answer[:50]} — {count} ({percent:.1f}%)\n"
            embed.add_field(name="🔝 Популярные ответы", value=top_text, inline=False)
    
    return embed


def create_survey_list_embed(surveys: List[Dict], guild_name: str) -> discord.Embed:
    """Создает embed со списком опросов."""
    embed = discord.Embed(
        title=f"📋 Опросы сервера {guild_name}",
        color=discord.Color.blue()
    )
    
    if not surveys:
        embed.description = "Нет доступных опросов"
        return embed
    
    for survey in surveys:
        status_emoji = {
            'draft': '📝',
            'published': '✅',
            'closed': '🔒'
        }.get(survey['status'], '❓')
        
        value = f"{status_emoji} Статус: **{survey['status']}**\n"
        value += f"Создан: {survey['created_at']}\n"
        if survey.get('anonymous'):
            value += "🔒 Анонимный\n"
        
        embed.add_field(
            name=f"#{survey['id']} — {survey['title']}",
            value=value,
            inline=False
        )
    
    return embed


def create_error_embed(title: str, description: str) -> discord.Embed:
    """Создает embed с ошибкой."""
    return discord.Embed(
        title=f"❌ {title}",
        description=description,
        color=discord.Color.red()
    )


def create_success_embed(title: str, description: str) -> discord.Embed:
    """Создает embed с успешным сообщением."""
    return discord.Embed(
        title=f"✅ {title}",
        description=description,
        color=discord.Color.green()
    )


def create_survey_announcement_embed(survey_data: Dict, total_questions: int) -> discord.Embed:
    """Создает embed для публикации опроса в канале."""
    embed = discord.Embed(
        title=f"📋 {survey_data['title']}",
        description=survey_data.get('description', 'Пройдите опрос и поделитесь своим мнением!'),
        color=discord.Color.blue()
    )
    
    embed.set_footer(text="Нажмите кнопку ниже, чтобы начать")
    embed.timestamp = discord.utils.utcnow()
    
    return embed
