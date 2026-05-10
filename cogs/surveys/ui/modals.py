"""
Модальные окна для системы опросов.
"""
import discord
from typing import Callable, Optional


class TextAnswerModal(discord.ui.Modal):
    """Модальное окно для текстового ответа."""
    
    def __init__(self, question_text: str, current_answer: Optional[str], callback: Callable):
        super().__init__(title="Ответ на вопрос")
        self.callback_func = callback
        
        # Обрезаем вопрос если слишком длинный
        label = question_text[:45] if len(question_text) > 45 else question_text
        
        self.answer_input = discord.ui.TextInput(
            label=label,
            style=discord.TextStyle.paragraph,
            placeholder="Введите ваш ответ...",
            required=True,
            max_length=2000,
            default=current_answer if current_answer else None
        )
        self.add_item(self.answer_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        await self.callback_func(interaction, self.answer_input.value)


class CreateSurveyModal(discord.ui.Modal, title="Создать опрос"):
    """Модальное окно для создания опроса."""
    
    title_input = discord.ui.TextInput(
        label="Название опроса",
        placeholder="Опрос проекта",
        required=True,
        max_length=100
    )
    
    description_input = discord.ui.TextInput(
        label="Описание",
        style=discord.TextStyle.paragraph,
        placeholder="Краткое описание опроса...",
        required=False,
        max_length=500
    )
    
    def __init__(self, callback: Callable):
        super().__init__()
        self.callback_func = callback
    
    async def on_submit(self, interaction: discord.Interaction):
        await self.callback_func(
            interaction,
            self.title_input.value,
            self.description_input.value
        )


class AddCategoryModal(discord.ui.Modal, title="Добавить категорию"):
    """Модальное окно для добавления категории."""
    
    title_input = discord.ui.TextInput(
        label="Название категории",
        placeholder="Общие впечатления",
        required=True,
        max_length=100
    )
    
    description_input = discord.ui.TextInput(
        label="Описание (необязательно)",
        style=discord.TextStyle.paragraph,
        placeholder="Описание категории...",
        required=False,
        max_length=300
    )
    
    def __init__(self, callback: Callable):
        super().__init__()
        self.callback_func = callback
    
    async def on_submit(self, interaction: discord.Interaction):
        await self.callback_func(
            interaction,
            self.title_input.value,
            self.description_input.value
        )


class AddQuestionModal(discord.ui.Modal, title="Добавить вопрос"):
    """Модальное окно для добавления вопроса."""
    
    question_input = discord.ui.TextInput(
        label="Текст вопроса",
        style=discord.TextStyle.paragraph,
        placeholder="Как вы оцениваете работу администрации?",
        required=True,
        max_length=500
    )
    
    def __init__(self, callback: Callable):
        super().__init__()
        self.callback_func = callback
    
    async def on_submit(self, interaction: discord.Interaction):
        await self.callback_func(interaction, self.question_input.value)
