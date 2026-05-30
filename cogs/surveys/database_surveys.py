"""
Расширение базы данных для системы опросов.
"""
import sqlite3
import json
from typing import Optional, List, Dict, Any
from datetime import datetime
from contextlib import contextmanager
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "bot.db")


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_surveys_db():
    """Инициализация таблиц для системы опросов."""
    with get_conn() as conn:
        # Проверяем, нужна ли миграция
        cursor = conn.execute("PRAGMA table_info(survey_questions)")
        columns = [row[1] for row in cursor.fetchall()]
        
        # Если есть category_id, нужна миграция
        if 'category_id' in columns:
            print("[SURVEYS] Обнаружена старая структура БД. Выполняется миграция...")
            
            # Создаем новую таблицу
            conn.execute("""
                CREATE TABLE IF NOT EXISTS survey_questions_new (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    survey_id       INTEGER NOT NULL,
                    question_text   TEXT NOT NULL,
                    question_type   TEXT NOT NULL,
                    required        INTEGER NOT NULL DEFAULT 1,
                    order_index     INTEGER NOT NULL,
                    options         TEXT,
                    FOREIGN KEY (survey_id) REFERENCES surveys(id) ON DELETE CASCADE
                )
            """)
            
            # Мигрируем данные (если есть)
            try:
                conn.execute("""
                    INSERT INTO survey_questions_new (id, survey_id, question_text, question_type, required, order_index, options)
                    SELECT sq.id, sc.survey_id, sq.question_text, sq.question_type, sq.required, sq.order_index, sq.options
                    FROM survey_questions sq
                    JOIN survey_categories sc ON sq.category_id = sc.id
                """)
                print("[SURVEYS] Данные мигрированы.")
            except:
                pass  # Нет данных для миграции
            
            # Удаляем старые таблицы
            conn.execute("DROP TABLE IF EXISTS survey_questions")
            conn.execute("DROP TABLE IF EXISTS survey_categories")
            
            # Переименовываем новую таблицу
            conn.execute("ALTER TABLE survey_questions_new RENAME TO survey_questions")
            
            print("[SURVEYS] Миграция завершена.")
        
        conn.executescript("""
        -- Таблица опросов
        CREATE TABLE IF NOT EXISTS surveys (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id        INTEGER NOT NULL,
            title           TEXT NOT NULL,
            description     TEXT,
            anonymous       INTEGER NOT NULL DEFAULT 0,
            status          TEXT NOT NULL DEFAULT 'draft',
            results_channel_id INTEGER,
            created_by      INTEGER NOT NULL,
            created_at      TEXT NOT NULL,
            published_at    TEXT,
            closed_at       TEXT
        );

        -- Таблица вопросов (без категорий)
        CREATE TABLE IF NOT EXISTS survey_questions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            survey_id       INTEGER NOT NULL,
            question_text   TEXT NOT NULL,
            question_type   TEXT NOT NULL,
            required        INTEGER NOT NULL DEFAULT 1,
            order_index     INTEGER NOT NULL,
            options         TEXT,
            FOREIGN KEY (survey_id) REFERENCES surveys(id) ON DELETE CASCADE
        );

        -- Таблица сессий прохождения
        CREATE TABLE IF NOT EXISTS survey_sessions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            survey_id       INTEGER NOT NULL,
            user_id         INTEGER NOT NULL,
            guild_id        INTEGER NOT NULL,
            started_at      TEXT NOT NULL,
            completed_at    TEXT,
            current_question INTEGER DEFAULT 0,
            FOREIGN KEY (survey_id) REFERENCES surveys(id) ON DELETE CASCADE,
            UNIQUE(survey_id, user_id)
        );

        -- Таблица ответов
        CREATE TABLE IF NOT EXISTS survey_responses (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER NOT NULL,
            question_id     INTEGER NOT NULL,
            answer          TEXT NOT NULL,
            answered_at     TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES survey_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY (question_id) REFERENCES survey_questions(id) ON DELETE CASCADE
        );

        -- Таблица сообщений с опросами
        CREATE TABLE IF NOT EXISTS survey_messages (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            survey_id       INTEGER NOT NULL,
            channel_id      INTEGER NOT NULL,
            message_id      INTEGER NOT NULL,
            posted_at       TEXT NOT NULL,
            FOREIGN KEY (survey_id) REFERENCES surveys(id) ON DELETE CASCADE
        );

        -- Индексы для производительности
        CREATE INDEX IF NOT EXISTS idx_surveys_guild ON surveys(guild_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_survey_user ON survey_sessions(survey_id, user_id);
        CREATE INDEX IF NOT EXISTS idx_responses_session ON survey_responses(session_id);
        CREATE INDEX IF NOT EXISTS idx_responses_question ON survey_responses(question_id);
        """)
    print("[SURVEYS] База данных опросов инициализирована.")


# ═══════════════════════════════════════════════════════════════════════════
# CRUD операции для опросов
# ═══════════════════════════════════════════════════════════════════════════

def create_survey(guild_id: int, title: str, description: str, anonymous: bool, 
                 created_by: int, results_channel_id: Optional[int] = None) -> int:
    """Создает новый опрос."""
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    with get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO surveys (guild_id, title, description, anonymous, created_by, created_at, results_channel_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (guild_id, title, description, 1 if anonymous else 0, created_by, now, results_channel_id)
        )
        return cursor.lastrowid


def get_survey(survey_id: int) -> Optional[sqlite3.Row]:
    """Получает опрос по ID."""
    with get_conn() as conn:
        return conn.execute("SELECT * FROM surveys WHERE id=?", (survey_id,)).fetchone()


def get_guild_surveys(guild_id: int, status: Optional[str] = None) -> List[sqlite3.Row]:
    """Получает все опросы сервера."""
    with get_conn() as conn:
        if status:
            return conn.execute(
                "SELECT * FROM surveys WHERE guild_id=? AND status=? ORDER BY created_at DESC",
                (guild_id, status)
            ).fetchall()
        return conn.execute(
            "SELECT * FROM surveys WHERE guild_id=? ORDER BY created_at DESC",
            (guild_id,)
        ).fetchall()


def update_survey_status(survey_id: int, status: str) -> None:
    """Обновляет статус опроса."""
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    with get_conn() as conn:
        if status == 'published':
            conn.execute(
                "UPDATE surveys SET status=?, published_at=? WHERE id=?",
                (status, now, survey_id)
            )
        elif status == 'closed':
            conn.execute(
                "UPDATE surveys SET status=?, closed_at=? WHERE id=?",
                (status, now, survey_id)
            )
        else:
            conn.execute("UPDATE surveys SET status=? WHERE id=?", (status, survey_id))


def update_results_channel(survey_id: int, channel_id: Optional[int]) -> None:
    """Обновляет канал результатов опроса."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE surveys SET results_channel_id=? WHERE id=?",
            (channel_id, survey_id)
        )


def save_survey_message(survey_id: int, channel_id: int, message_id: int) -> None:
    """Сохраняет ID сообщения с опросом."""
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO survey_messages (survey_id, channel_id, message_id, posted_at) VALUES (?, ?, ?, ?)",
            (survey_id, channel_id, message_id, now)
        )


# ═══════════════════════════════════════════════════════════════════════════
# CRUD операции для вопросов
# ═══════════════════════════════════════════════════════════════════════════

def add_question(survey_id: int, question_text: str, question_type: str,
                required: bool, order_index: int, options: Optional[Dict] = None) -> int:
    """Добавляет вопрос в опрос."""
    options_json = json.dumps(options) if options else None
    with get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO survey_questions (survey_id, question_text, question_type, required, order_index, options) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (survey_id, question_text, question_type, 1 if required else 0, order_index, options_json)
        )
        return cursor.lastrowid


def get_survey_questions(survey_id: int) -> List[sqlite3.Row]:
    """Получает все вопросы опроса."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM survey_questions WHERE survey_id=? ORDER BY order_index",
            (survey_id,)
        ).fetchall()


# ═══════════════════════════════════════════════════════════════════════════
# Сессии прохождения
# ═══════════════════════════════════════════════════════════════════════════

def create_session(survey_id: int, user_id: int, guild_id: int) -> Optional[int]:
    """Создает сессию прохождения опроса."""
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    with get_conn() as conn:
        try:
            cursor = conn.execute(
                "INSERT INTO survey_sessions (survey_id, user_id, guild_id, started_at) VALUES (?, ?, ?, ?)",
                (survey_id, user_id, guild_id, now)
            )
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            # Пользователь уже проходил опрос
            return None


def get_session(survey_id: int, user_id: int) -> Optional[sqlite3.Row]:
    """Получает сессию пользователя."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM survey_sessions WHERE survey_id=? AND user_id=?",
            (survey_id, user_id)
        ).fetchone()


def update_session_progress(session_id: int, current_question: int) -> None:
    """Обновляет прогресс прохождения."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE survey_sessions SET current_question=? WHERE id=?",
            (current_question, session_id)
        )


def complete_session(session_id: int) -> None:
    """Завершает сессию."""
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    with get_conn() as conn:
        conn.execute(
            "UPDATE survey_sessions SET completed_at=? WHERE id=?",
            (now, session_id)
        )


# ═══════════════════════════════════════════════════════════════════════════
# Ответы
# ═══════════════════════════════════════════════════════════════════════════

def save_response(session_id: int, question_id: int, answer: str) -> None:
    """Сохраняет ответ на вопрос."""
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    with get_conn() as conn:
        # Удаляем старый ответ если есть
        conn.execute(
            "DELETE FROM survey_responses WHERE session_id=? AND question_id=?",
            (session_id, question_id)
        )
        # Сохраняем новый
        conn.execute(
            "INSERT INTO survey_responses (session_id, question_id, answer, answered_at) VALUES (?, ?, ?, ?)",
            (session_id, question_id, answer, now)
        )


def get_session_responses(session_id: int) -> List[sqlite3.Row]:
    """Получает все ответы сессии."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM survey_responses WHERE session_id=? ORDER BY answered_at",
            (session_id,)
        ).fetchall()


def get_question_responses(question_id: int) -> List[sqlite3.Row]:
    """Получает все ответы на вопрос."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM survey_responses WHERE question_id=?",
            (question_id,)
        ).fetchall()


# ═══════════════════════════════════════════════════════════════════════════
# Статистика
# ═══════════════════════════════════════════════════════════════════════════

def get_survey_stats(survey_id: int) -> Dict[str, Any]:
    """Получает статистику опроса."""
    with get_conn() as conn:
        # Общая статистика
        total_started = conn.execute(
            "SELECT COUNT(*) as cnt FROM survey_sessions WHERE survey_id=?",
            (survey_id,)
        ).fetchone()["cnt"]
        
        total_completed = conn.execute(
            "SELECT COUNT(*) as cnt FROM survey_sessions WHERE survey_id=? AND completed_at IS NOT NULL",
            (survey_id,)
        ).fetchone()["cnt"]
        
        completion_rate = (total_completed / total_started * 100) if total_started > 0 else 0
        
        return {
            "total_started": total_started,
            "total_completed": total_completed,
            "completion_rate": round(completion_rate, 1)
        }


def get_question_stats(question_id: int) -> Dict[str, Any]:
    """Получает статистику по вопросу."""
    with get_conn() as conn:
        responses = conn.execute(
            "SELECT answer FROM survey_responses WHERE question_id=?",
            (question_id,)
        ).fetchall()
        
        if not responses:
            return {"total": 0, "distribution": {}}
        
        # Подсчет распределения ответов
        distribution = {}
        for row in responses:
            answer = row["answer"]
            distribution[answer] = distribution.get(answer, 0) + 1
        
        # Для числовых ответов (оценки 1-10) вычисляем среднее
        try:
            numeric_answers = [int(row["answer"]) for row in responses]
            average = sum(numeric_answers) / len(numeric_answers)
            return {
                "total": len(responses),
                "distribution": distribution,
                "average": round(average, 2)
            }
        except ValueError:
            # Текстовые ответы
            return {
                "total": len(responses),
                "distribution": distribution
            }
