import sqlite3
import os
from typing import Optional
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
            close_reason TEXT
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
        """)
    print("[DB] База данных инициализирована.")


# ── Tickets ───────────────────────────────────────────────────────────────────

def create_ticket(ticket_id: int, guild_id: int, channel_id: int,
                  user_id: int, ticket_type: str) -> None:
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO tickets (id, guild_id, channel_id, user_id, type, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'open', ?)",
            (ticket_id, guild_id, channel_id, user_id, ticket_type, now)
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
                        conn.execute(
                            "INSERT OR IGNORE INTO tickets "
                            "(id, guild_id, channel_id, user_id, type, status, created_at) "
                            "VALUES (?, 0, 0, ?, ?, 'closed', ?)",
                            (int(tid), td.get("author_id", 0), td.get("type", "other"), td.get("created_at", ""))
                        )
                        migrated += 1
            if migrated:
                print(f"[DB] Мигрировано {migrated} тикетов из JSON.")
        except Exception as e:
            print(f"[DB] Ошибка миграции tickets: {e}")
