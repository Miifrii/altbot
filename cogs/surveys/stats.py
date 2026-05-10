"""
Команды статистики для системы опросов.
"""
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
import csv
import json
import io

from .database_surveys import *
from .ui.embeds import create_stats_embed, create_question_stats_embed, create_error_embed


class SurveyStatsCog(commands.Cog):
    """Cog для команд статистики опросов."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    survey_stats = app_commands.Group(
        name="surveystats",
        description="Статистика опросов",
        default_permissions=discord.Permissions(administrator=True)
    )
    
    @survey_stats.command(name="overview", description="Общая статистика опроса")
    @app_commands.describe(survey_id="ID опроса")
    async def stats_overview(self, interaction: discord.Interaction, survey_id: int):
        """Показывает общую статистику опроса."""
        survey = get_survey(survey_id)
        if not survey or survey['guild_id'] != interaction.guild_id:
            await interaction.response.send_message(
                embed=create_error_embed("Опрос не найден", "Опрос с таким ID не существует."),
                ephemeral=True
            )
            return
        
        stats = get_survey_stats(survey_id)
        embed = create_stats_embed(dict(survey), stats)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @survey_stats.command(name="question", description="Статистика по конкретному вопросу")
    @app_commands.describe(
        survey_id="ID опроса",
        question_id="ID вопроса"
    )
    async def stats_question(self, interaction: discord.Interaction, survey_id: int, question_id: int):
        """Показывает статистику по вопросу."""
        # Проверяем опрос
        survey = get_survey(survey_id)
        if not survey or survey['guild_id'] != interaction.guild_id:
            await interaction.response.send_message(
                embed=create_error_embed("Опрос не найден", "Опрос с таким ID не существует."),
                ephemeral=True
            )
            return
        
        # Получаем вопрос
        with get_conn() as conn:
            question = conn.execute(
                "SELECT * FROM survey_questions WHERE id=? AND survey_id=?",
                (question_id, survey_id)
            ).fetchone()
        
        if not question:
            await interaction.response.send_message(
                embed=create_error_embed("Вопрос не найден", "Вопрос с таким ID не существует в этом опросе."),
                ephemeral=True
            )
            return
        
        stats = get_question_stats(question_id)
        embed = create_question_stats_embed(
            question['question_text'],
            stats,
            question['question_type']
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @survey_stats.command(name="export", description="Экспорт результатов опроса")
    @app_commands.describe(
        survey_id="ID опроса",
        format="Формат экспорта"
    )
    @app_commands.choices(format=[
        app_commands.Choice(name="CSV", value="csv"),
        app_commands.Choice(name="JSON", value="json")
    ])
    async def export_results(
        self,
        interaction: discord.Interaction,
        survey_id: int,
        format: str = "csv"
    ):
        """Экспортирует результаты опроса в CSV или JSON."""
        survey = get_survey(survey_id)
        if not survey or survey['guild_id'] != interaction.guild_id:
            await interaction.response.send_message(
                embed=create_error_embed("Опрос не найден", "Опрос с таким ID не существует."),
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Получаем все вопросы
        questions = get_survey_questions(survey_id)
        
        # Получаем все завершенные сессии
        with get_conn() as conn:
            sessions = conn.execute(
                "SELECT * FROM survey_sessions WHERE survey_id=? AND completed_at IS NOT NULL ORDER BY completed_at DESC",
                (survey_id,)
            ).fetchall()
        
        if not sessions:
            await interaction.followup.send(
                embed=create_error_embed("Нет данных", "Никто еще не завершил этот опрос."),
                ephemeral=True
            )
            return
        
        # Собираем данные
        export_data = []
        for session in sessions:
            responses = get_session_responses(session['id'])
            
            # Получаем пользователя
            user = None
            if not survey['anonymous']:
                try:
                    user = await self.bot.fetch_user(session['user_id'])
                except:
                    pass
            
            session_data = {
                'User ID': session['user_id'] if not survey['anonymous'] else 'anonymous',
                'Username': str(user) if user else 'Unknown',
                'Started At': session['started_at'],
                'Completed At': session['completed_at']
            }
            
            # Добавляем ответы на каждый вопрос
            for question in questions:
                response = next(
                    (r for r in responses if r['question_id'] == question['id']),
                    None
                )
                
                # Используем текст вопроса как ключ (обрезаем если длинный)
                question_key = question['question_text'][:100]
                session_data[question_key] = response['answer'] if response else ''
            
            export_data.append(session_data)
        
        # Экспорт в выбранном формате
        if format == "csv":
            file_content = self._export_to_csv(export_data)
            filename = f"survey_{survey_id}_results.csv"
            file = discord.File(io.BytesIO(file_content.encode('utf-8-sig')), filename=filename)
        else:  # json
            json_export = {
                'survey_id': survey_id,
                'survey_title': survey['title'],
                'total_responses': len(export_data),
                'anonymous': bool(survey['anonymous']),
                'responses': export_data
            }
            file_content = json.dumps(json_export, ensure_ascii=False, indent=2)
            filename = f"survey_{survey_id}_results.json"
            file = discord.File(io.BytesIO(file_content.encode('utf-8')), filename=filename)
        
        await interaction.followup.send(
            content=f"✅ Экспорт завершен: **{len(export_data)}** завершенных ответов из **{survey['title']}**",
            file=file,
            ephemeral=True
        )
    
    def _export_to_csv(self, data: list) -> str:
        """Конвертирует данные в CSV."""
        if not data:
            return ""
        
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
        
        return output.getvalue()
    
    @survey_stats.command(name="responses", description="Список всех ответов на опрос")
    @app_commands.describe(survey_id="ID опроса")
    async def list_responses(self, interaction: discord.Interaction, survey_id: int):
        """Показывает список всех ответов на опрос."""
        survey = get_survey(survey_id)
        if not survey or survey['guild_id'] != interaction.guild_id:
            await interaction.response.send_message(
                embed=create_error_embed("Опрос не найден", "Опрос с таким ID не существует."),
                ephemeral=True
            )
            return
        
        # Получаем завершенные сессии
        with get_conn() as conn:
            sessions = conn.execute(
                "SELECT * FROM survey_sessions WHERE survey_id=? AND completed_at IS NOT NULL ORDER BY completed_at DESC",
                (survey_id,)
            ).fetchall()
        
        if not sessions:
            await interaction.response.send_message(
                embed=create_error_embed("Нет ответов", "Никто еще не завершил этот опрос."),
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title=f"📋 Ответы на опрос: {survey['title']}",
            color=discord.Color.blue()
        )
        
        for i, session in enumerate(sessions[:25], 1):  # Discord limit
            user_info = f"<@{session['user_id']}>" if not survey['anonymous'] else "🔒 Анонимно"
            
            embed.add_field(
                name=f"#{i} — {session['completed_at']}",
                value=f"Пользователь: {user_info}\nВремя: {session['started_at']} → {session['completed_at']}",
                inline=False
            )
        
        if len(sessions) > 25:
            embed.set_footer(text=f"Показано 25 из {len(sessions)} ответов. Используйте /surveystats export для полного списка.")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    """Загружает cog."""
    await bot.add_cog(SurveyStatsCog(bot))
