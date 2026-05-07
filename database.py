import sqlite3
import os
from typing import Optional, Dict, Any
from datetime import datetime
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "bot.db")


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


def init_db():
    # Создаем папку data если её нет
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS tickets (
            id          INTEGER PRIMARY KEY,
            guild_id    INTEGER NOT NULL,
            channel_id  INTEGER NOT NULL UNIQUE,
            user_id     INTEGER NOT NULL,
            type        TEXT    NOT NULL,
            status      TEXT    NOT NULL DEFAULT 'open',
            claimed_by  INTEGER,
            created_at  TEXT    NOT NULL,
            closed_at   TEXT,
            close_reason TEXT,
            form_data   TEXT    -- JSON данные формы
        );

        CREATE TABLE IF NOT EXISTS users (
            user_id         INTEGER PRIMARY KEY,
            tickets_created INTEGER NOT NULL DEFAULT 0,
            tickets_closed  INTEGER NOT NULL DEFAULT 0,
            reputation      INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS ticket_roles (
            ticket_type TEXT PRIMARY KEY,
            role_id     INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS ticket_actions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id  INTEGER NOT NULL,
            action     TEXT    NOT NULL,
            user_id    INTEGER NOT NULL,
            created_at TEXT    NOT NULL,
            FOREIGN KEY (ticket_id) REFERENCES tickets(id)
        );

        CREATE TABLE IF NOT EXISTS ticket_counters (
            ticket_type TEXT PRIMARY KEY,
            counter     INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS review_counters (
            review_type TEXT PRIMARY KEY,
            counter     INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS user_cooldowns (
            user_id     INTEGER NOT NULL,
            action_type TEXT    NOT NULL,
            last_used   REAL    NOT NULL,
            PRIMARY KEY (user_id, action_type)
        );

        CREATE TABLE IF NOT EXISTS departments (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            emoji       TEXT,
            dept_role_id INTEGER
        );

        CREATE TABLE IF NOT EXISTS department_roles (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            dept_id     TEXT NOT NULL,
            role_id     INTEGER NOT NULL,
            role_name   TEXT NOT NULL,
            level       INTEGER NOT NULL,
            FOREIGN KEY (dept_id) REFERENCES departments(id)
        );

        CREATE TABLE IF NOT EXISTS role_permissions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            dept_id     TEXT NOT NULL,
            from_level  INTEGER NOT NULL,
            to_level    INTEGER NOT NULL,
            FOREIGN KEY (dept_id) REFERENCES departments(id)
        );

        CREATE TABLE IF NOT EXISTS ticket_moderator_roles (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id    INTEGER NOT NULL,
            ticket_type TEXT    NOT NULL,
            role_id     INTEGER NOT NULL,
            added_by    INTEGER NOT NULL,
            added_at    TEXT    NOT NULL,
            UNIQUE(guild_id, ticket_type, role_id)
        );

        CREATE INDEX IF NOT EXISTS idx_ticket_mod_roles_guild_type 
        ON ticket_moderator_roles(guild_id, ticket_type);
        """)
        
        # Миграция схемы: добавляем form_data если её нет
        try:
            cursor = conn.execute("PRAGMA table_info(tickets)")
            columns = [row[1] for row in cursor.fetchall()]
            if "form_data" not in columns:
                conn.execute("ALTER TABLE tickets ADD COLUMN form_data TEXT")
                print("[DB] Добавлена колонка form_data в таблицу tickets.")
        except Exception as e:
            print(f"[DB] Ошибка миграции схемы: {e}")
            
    print("[DB] База данных инициализирована.")
    
    # Автоматическая миграция ролей модераторов при первом запуске
    try:
        from cogs.tickets.config_manager import TicketConfigManager
        # Проверяем есть ли уже роли в БД
        with get_conn() as conn:
            count = conn.execute("SELECT COUNT(*) as cnt FROM ticket_moderator_roles").fetchone()["cnt"]
            if count == 0:
                print("[DB] Роли модераторов не найдены, выполняется автоматическая миграция...")
                # Миграция будет выполнена при первом обращении к TicketConfigManager
    except Exception as e:
        print(f"[DB] Предупреждение при проверке миграции: {e}")


# ── Tickets ───────────────────────────────────────────────────────────────────

def create_ticket(ticket_id: int, guild_id: int, channel_id: int,
                  user_id: int, ticket_type: str, form_data: Dict[str, Any] = None) -> None:
    import json
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    form_json = json.dumps(form_data or {}, ensure_ascii=False)
    
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO tickets (id, guild_id, channel_id, user_id, type, status, created_at, form_data) "
            "VALUES (?, ?, ?, ?, ?, 'open', ?, ?)",
            (ticket_id, guild_id, channel_id, user_id, ticket_type, now, form_json)
        )
        conn.execute(
            "INSERT INTO users (user_id, tickets_created) VALUES (?, 1) "
            "ON CONFLICT(user_id) DO UPDATE SET tickets_created = tickets_created + 1",
            (user_id,)
        )
        _log_action(conn, ticket_id, "created", user_id)


def claim_ticket(ticket_id: int, moderator_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE tickets SET status='in_progress', claimed_by=? WHERE id=?",
            (moderator_id, ticket_id)
        )
        _log_action(conn, ticket_id, "claimed", moderator_id)


def close_ticket(ticket_id: int, moderator_id: int, reason: str) -> None:
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    with get_conn() as conn:
        row = conn.execute("SELECT user_id FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        conn.execute(
            "UPDATE tickets SET status='closed', closed_at=?, close_reason=? WHERE id=?",
            (now, reason, ticket_id)
        )
        if row:
            conn.execute(
                "INSERT INTO users (user_id, tickets_closed) VALUES (?, 1) "
                "ON CONFLICT(user_id) DO UPDATE SET tickets_closed = tickets_closed + 1",
                (moderator_id,)
            )
        _log_action(conn, ticket_id, f"closed: {reason}", moderator_id)


def get_ticket_by_channel(channel_id: int) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM tickets WHERE channel_id=?", (channel_id,)
        ).fetchone()


def get_active_ticket(user_id: int, guild_id: int) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM tickets WHERE user_id=? AND guild_id=? AND status != 'closed'",
            (user_id, guild_id)
        ).fetchone()


def get_ticket(ticket_id: int) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()


# ── Counters ──────────────────────────────────────────────────────────────────

def next_ticket_id(ticket_type: str) -> int:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO ticket_counters (ticket_type, counter) VALUES (?, 1) "
            "ON CONFLICT(ticket_type) DO UPDATE SET counter = counter + 1",
            (ticket_type,)
        )
        row = conn.execute(
            "SELECT counter FROM ticket_counters WHERE ticket_type=?", (ticket_type,)
        ).fetchone()
        return row["counter"]


def next_review_id(review_type: str) -> int:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO review_counters (review_type, counter) VALUES (?, 1) "
            "ON CONFLICT(review_type) DO UPDATE SET counter = counter + 1",
            (review_type,)
        )
        row = conn.execute(
            "SELECT counter FROM review_counters WHERE review_type=?", (review_type,)
        ).fetchone()
        return row["counter"]


# ── Cooldowns ─────────────────────────────────────────────────────────────────

def check_cooldown(user_id: int, action_type: str, cooldown_seconds: int) -> Optional[float]:
    """Проверяет кулдаун. Возвращает оставшееся время или None если можно использовать."""
    import time
    now = time.time()
    
    with get_conn() as conn:
        row = conn.execute(
            "SELECT last_used FROM user_cooldowns WHERE user_id=? AND action_type=?",
            (user_id, action_type)
        ).fetchone()
        
        if row:
            remaining = cooldown_seconds - (now - row["last_used"])
            if remaining > 0:
                return remaining
        
        # Обновляем время последнего использования
        conn.execute(
            "INSERT INTO user_cooldowns (user_id, action_type, last_used) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, action_type) DO UPDATE SET last_used=excluded.last_used",
            (user_id, action_type, now)
        )
        return None


# ── Settings ──────────────────────────────────────────────────────────────────

def get_setting(key: str, default: str = None) -> Optional[str]:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def update_setting(key: str, value: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value))
        )


def get_all_settings() -> dict:
    with get_conn() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}


# ── Departments & Roles ───────────────────────────────────────────────────────

def init_departments():
    """Инициализирует отделы и роли из конфига."""
    from config import CONFIG
    
    departments_config = {
        "admin": {
            "name": "Администрация",
            "emoji": "🛡️",
            "dept_role_id": CONFIG["roles"]["admin_dept"],
            "roles": [
                {"role_id": CONFIG["roles"]["senior_admin"], "name": "Старший Администратор", "level": 3},
                {"role_id": CONFIG["roles"]["admin"], "name": "Администратор", "level": 2},
                {"role_id": CONFIG["roles"]["junior_admin"], "name": "Младший Администратор", "level": 1}
            ],
            "can_grant": {3: [2, 1], 2: [], 1: []}
        },
        "mapper": {
            "name": "Маппинг",
            "emoji": "🗺️",
            "dept_role_id": CONFIG["roles"]["dev_dept"],
            "roles": [
                {"role_id": CONFIG["roles"]["senior_mapper"], "name": "Старший маппер", "level": 2},
                {"role_id": CONFIG["roles"]["mapper"], "name": "Маппер", "level": 1},
                {"role_id": 0, "name": "Стажёр маппера", "level": 0}
            ],
            "can_grant": {2: [1, 0], 1: [], 0: []}
        },
        "spriter": {
            "name": "Спрайтинг",
            "emoji": "🎨",
            "dept_role_id": CONFIG["roles"]["dev_dept"],
            "roles": [
                {"role_id": CONFIG["roles"]["senior_spriter"], "name": "Старший спрайтер", "level": 2},
                {"role_id": CONFIG["roles"]["spriter"], "name": "Спрайтер", "level": 1}
            ],
            "can_grant": {2: [1], 1: []}
        },
        "dev": {
            "name": "Разработка",
            "emoji": "💻",
            "dept_role_id": CONFIG["roles"]["dev_dept"],
            "roles": [
                {"role_id": 0, "name": "Главный разработчик", "level": 2},
                {"role_id": 0, "name": "Прототипер", "level": 1},
                {"role_id": 0, "name": "Кодер", "level": 0}
            ],
            "can_grant": {2: [1, 0], 1: [], 0: []}
        },
        "wiki": {
            "name": "Вики",
            "emoji": "📖",
            "dept_role_id": CONFIG["roles"]["dev_dept"],
            "roles": [
                {"role_id": CONFIG["roles"]["wiki_trader"], "name": "Вольный торговец", "level": 2},
                {"role_id": CONFIG["roles"]["wiki_editor"], "name": "Редактор вики", "level": 1}
            ],
            "can_grant": {2: [1], 1: []}
        },
        "events": {
            "name": "Ивентологи",
            "emoji": "🎉",
            "dept_role_id": CONFIG["roles"]["events_dept"],
            "roles": [
                {"role_id": CONFIG["roles"]["chief_event"], "name": "Главный ивентолог", "level": 2},
                {"role_id": CONFIG["roles"]["event"], "name": "Ивентолог", "level": 1}
            ],
            "can_grant": {2: [1], 1: []}
        }
    }
    
    with get_conn() as conn:
        for dept_id, dept_config in departments_config.items():
            # Добавляем отдел
            conn.execute(
                "INSERT INTO departments (id, name, emoji, dept_role_id) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name, emoji=excluded.emoji, dept_role_id=excluded.dept_role_id",
                (dept_id, dept_config["name"], dept_config["emoji"], dept_config["dept_role_id"])
            )
            
            # Очищаем старые роли отдела
            conn.execute("DELETE FROM department_roles WHERE dept_id=?", (dept_id,))
            conn.execute("DELETE FROM role_permissions WHERE dept_id=?", (dept_id,))
            
            # Добавляем роли
            for role_config in dept_config["roles"]:
                conn.execute(
                    "INSERT INTO department_roles (dept_id, role_id, role_name, level) VALUES (?, ?, ?, ?)",
                    (dept_id, role_config["role_id"], role_config["name"], role_config["level"])
                )
            
            # Добавляем права на выдачу
            for from_level, to_levels in dept_config["can_grant"].items():
                for to_level in to_levels:
                    conn.execute(
                        "INSERT INTO role_permissions (dept_id, from_level, to_level) VALUES (?, ?, ?)",
                        (dept_id, int(from_level), to_level)
                    )


def get_user_permissions(member_role_ids: set, superadmin_role_id: int) -> list[dict]:
    """Получает список ролей, которые пользователь может выдавать."""
    if not member_role_ids:
        return []
        
    is_superadmin = superadmin_role_id in member_role_ids
    allowed = []
    
    with get_conn() as conn:
        if is_superadmin:
            # Суперадмин может выдавать все роли
            rows = conn.execute("""
                SELECT dr.role_id, dr.role_name, d.id as dept_id, d.name as dept_name, d.emoji as dept_emoji
                FROM department_roles dr
                JOIN departments d ON dr.dept_id = d.id
                WHERE dr.role_id != 0
            """).fetchall()
            for row in rows:
                allowed.append({
                    "role_id": row["role_id"],
                    "role_name": row["role_name"],
                    "dept_key": row["dept_id"],
                    "dept_name": row["dept_name"],
                    "dept_emoji": row["dept_emoji"]
                })
        else:
            # Обычный пользователь - проверяем права
            if len(member_role_ids) == 0:
                return allowed
                
            placeholders = ','.join('?' * len(member_role_ids))
            rows = conn.execute(f"""
                SELECT DISTINCT dr2.role_id, dr2.role_name, d.id as dept_id, d.name as dept_name, d.emoji as dept_emoji
                FROM department_roles dr1
                JOIN departments d ON dr1.dept_id = d.id
                JOIN role_permissions rp ON dr1.dept_id = rp.dept_id AND dr1.level = rp.from_level
                JOIN department_roles dr2 ON rp.dept_id = dr2.dept_id AND rp.to_level = dr2.level
                WHERE dr1.role_id IN ({placeholders}) AND dr2.role_id != 0
            """, list(member_role_ids)).fetchall()
            
            for row in rows:
                allowed.append({
                    "role_id": row["role_id"],
                    "role_name": row["role_name"],
                    "dept_key": row["dept_id"],
                    "dept_name": row["dept_name"],
                    "dept_emoji": row["dept_emoji"]
                })
    
    return allowed


def get_department_role_id(dept_id: str) -> Optional[int]:
    """Получает ID роли отдела."""
    with get_conn() as conn:
        row = conn.execute("SELECT dept_role_id FROM departments WHERE id=?", (dept_id,)).fetchone()
        return row["dept_role_id"] if row else None


def get_department_roles(dept_id: str) -> list[int]:
    """Получает все ID ролей отдела."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT role_id FROM department_roles WHERE dept_id=? AND role_id != 0", (dept_id,)
        ).fetchall()
        return [row["role_id"] for row in rows]


# ── Ticket Moderator Roles ────────────────────────────────────────────────────

def add_ticket_moderator_role(guild_id: int, ticket_type: str, role_id: int, added_by: int) -> bool:
    """Добавляет роль модератора для типа тикета. Возвращает True если добавлено, False если уже существует."""
    from datetime import datetime
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    
    with get_conn() as conn:
        try:
            conn.execute(
                "INSERT INTO ticket_moderator_roles (guild_id, ticket_type, role_id, added_by, added_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (guild_id, ticket_type, role_id, added_by, now)
            )
            return True
        except sqlite3.IntegrityError:
            # Роль уже существует для этого типа тикета
            return False


def remove_ticket_moderator_role(guild_id: int, ticket_type: str, role_id: int) -> bool:
    """Удаляет роль модератора для типа тикета. Возвращает True если удалено, False если не найдено."""
    with get_conn() as conn:
        cursor = conn.execute(
            "DELETE FROM ticket_moderator_roles WHERE guild_id=? AND ticket_type=? AND role_id=?",
            (guild_id, ticket_type, role_id)
        )
        return cursor.rowcount > 0


def get_ticket_moderator_roles(guild_id: int, ticket_type: str) -> set[int]:
    """Получает множество ID ролей модераторов для типа тикета."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT role_id FROM ticket_moderator_roles WHERE guild_id=? AND ticket_type=?",
            (guild_id, ticket_type)
        ).fetchall()
        return {row["role_id"] for row in rows}


def get_all_ticket_moderator_roles(guild_id: int) -> dict[str, list[dict]]:
    """Получает все роли модераторов для всех типов тикетов на сервере."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT ticket_type, role_id, added_by, added_at FROM ticket_moderator_roles "
            "WHERE guild_id=? ORDER BY ticket_type, added_at",
            (guild_id,)
        ).fetchall()
        
        result = {}
        for row in rows:
            ticket_type = row["ticket_type"]
            if ticket_type not in result:
                result[ticket_type] = []
            result[ticket_type].append({
                "role_id": row["role_id"],
                "added_by": row["added_by"],
                "added_at": row["added_at"]
            })
        return result


def cleanup_deleted_roles(guild_id: int, existing_role_ids: set[int]) -> int:
    """Удаляет роли модераторов, которые больше не существуют на сервере. Возвращает количество удаленных."""
    if not existing_role_ids:
        return 0
        
    with get_conn() as conn:
        # Получаем все роли из БД для этого сервера
        db_roles = conn.execute(
            "SELECT role_id FROM ticket_moderator_roles WHERE guild_id=?", (guild_id,)
        ).fetchall()
        
        deleted_count = 0
        for row in db_roles:
            role_id = row["role_id"]
            if role_id not in existing_role_ids:
                conn.execute(
                    "DELETE FROM ticket_moderator_roles WHERE guild_id=? AND role_id=?",
                    (guild_id, role_id)
                )
                deleted_count += 1
        
        return deleted_count


def migrate_ticket_roles_from_config(guild_id: int, config_roles: dict[str, list[int]]) -> int:
    """Мигрирует роли модераторов из старого конфига в БД. Возвращает количество добавленных ролей."""
    migrated_count = 0
    
    with get_conn() as conn:
        for ticket_type, role_ids in config_roles.items():
            for role_id in role_ids:
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO ticket_moderator_roles "
                        "(guild_id, ticket_type, role_id, added_by, added_at) "
                        "VALUES (?, ?, ?, 0, 'Migrated from config')",
                        (guild_id, ticket_type, role_id)
                    )
                    if conn.total_changes > 0:
                        migrated_count += 1
                except Exception:
                    continue
    
    return migrated_count


# ── Ticket Roles ──────────────────────────────────────────────────────────────

def set_ticket_role(ticket_type: str, role_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO ticket_roles (ticket_type, role_id) VALUES (?, ?) "
            "ON CONFLICT(ticket_type) DO UPDATE SET role_id=excluded.role_id",
            (ticket_type, role_id)
        )


def get_ticket_role(ticket_type: str) -> Optional[int]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT role_id FROM ticket_roles WHERE ticket_type=?", (ticket_type,)
        ).fetchone()
        return row["role_id"] if row else None


# ── Users ─────────────────────────────────────────────────────────────────────

def get_user_stats(user_id: int) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()


# ── Actions (internal) ────────────────────────────────────────────────────────

def _log_action(conn: sqlite3.Connection, ticket_id: int, action: str, user_id: int) -> None:
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    conn.execute(
        "INSERT INTO ticket_actions (ticket_id, action, user_id, created_at) VALUES (?, ?, ?, ?)",
        (ticket_id, action, user_id, now)
    )


# ── Migration from JSON ───────────────────────────────────────────────────────

def migrate_from_json():
    """Мигрирует старые данные из JSON файлов в SQLite."""
    import json
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    
    # Создаем папку data если её нет
    os.makedirs(data_dir, exist_ok=True)

def migrate_from_json():
    """Мигрирует старые данные из JSON файлов в SQLite."""
    import json
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    
    # Создаем папку data если её нет
    os.makedirs(data_dir, exist_ok=True)

    # Миграция тикетов
    tickets_file = os.path.join(data_dir, "tickets_data.json")
    if os.path.exists(tickets_file):
        try:
            with open(tickets_file, "r", encoding="utf-8") as f:
                tickets = json.load(f)
            migrated = 0
            for tid, td in tickets.items():
                with get_conn() as conn:
                    existing = conn.execute("SELECT id FROM tickets WHERE id=?", (int(tid),)).fetchone()
                    if not existing:
                        form_data = td.get("form_fields", {})
                        
                        # Проверяем есть ли колонка form_data
                        cursor = conn.execute("PRAGMA table_info(tickets)")
                        columns = [row[1] for row in cursor.fetchall()]
                        
                        if "form_data" in columns:
                            # Новая схема с form_data
                            conn.execute(
                                "INSERT OR IGNORE INTO tickets "
                                "(id, guild_id, channel_id, user_id, type, status, created_at, form_data) "
                                "VALUES (?, 0, 0, ?, ?, 'closed', ?, ?)",
                                (int(tid), td.get("author_id", 0), td.get("type", "other"), 
                                 td.get("created_at", ""), json.dumps(form_data, ensure_ascii=False))
                            )
                        else:
                            # Старая схема без form_data
                            conn.execute(
                                "INSERT OR IGNORE INTO tickets "
                                "(id, guild_id, channel_id, user_id, type, status, created_at) "
                                "VALUES (?, 0, 0, ?, ?, 'closed', ?)",
                                (int(tid), td.get("author_id", 0), td.get("type", "other"), 
                                 td.get("created_at", ""))
                            )
                        migrated += 1
            if migrated:
                print(f"[DB] Мигрировано {migrated} тикетов из JSON.")
        except Exception as e:
            print(f"[DB] Ошибка миграции tickets: {e}")

    # Миграция счетчиков
    counters_file = os.path.join(data_dir, "ticket_counters.json")
    if os.path.exists(counters_file):
        try:
            with open(counters_file, "r", encoding="utf-8") as f:
                counters = json.load(f)
            with get_conn() as conn:
                for ticket_type, counter in counters.items():
                    conn.execute(
                        "INSERT INTO ticket_counters (ticket_type, counter) VALUES (?, ?) "
                        "ON CONFLICT(ticket_type) DO UPDATE SET counter=excluded.counter",
                        (ticket_type, counter)
                    )
            print(f"[DB] Мигрированы счетчики тикетов.")
        except Exception as e:
            print(f"[DB] Ошибка миграции counters: {e}")

    # Миграция счетчиков отзывов
    review_counters_file = os.path.join(data_dir, "review_counter.json")
    if os.path.exists(review_counters_file):
        try:
            with open(review_counters_file, "r", encoding="utf-8") as f:
                counters = json.load(f)
            with get_conn() as conn:
                for review_type, counter in counters.items():
                    conn.execute(
                        "INSERT INTO review_counters (review_type, counter) VALUES (?, ?) "
                        "ON CONFLICT(review_type) DO UPDATE SET counter=excluded.counter",
                        (review_type, counter)
                    )
            print(f"[DB] Мигрированы счетчики отзывов.")
        except Exception as e:
            print(f"[DB] Ошибка миграции review counters: {e}")