import json
import sqlite3
from contextlib import contextmanager

DB_PATH = "conversations.db"


@contextmanager
def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                messages TEXT NOT NULL,
                final_answer TEXT,
                created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
            )
        """)


def save_conversation(query: str, messages: list, final_answer: str) -> int:
    with _db() as conn:
        cur = conn.execute(
            "INSERT INTO conversations (query, messages, final_answer) VALUES (?, ?, ?)",
            (query, json.dumps(messages), final_answer),
        )
        return cur.lastrowid


def get_conversation(conv_id: int) -> dict | None:
    with _db() as conn:
        cur = conn.execute(
            "SELECT id, query, messages, final_answer, created_at FROM conversations WHERE id = ?",
            (conv_id,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    row = dict(row)
    row["messages"] = json.loads(row["messages"])
    return row


def list_conversations() -> list[dict]:
    with _db() as conn:
        cur = conn.execute(
            "SELECT id, query, created_at FROM conversations ORDER BY created_at DESC LIMIT 50"
        )
        return [dict(r) for r in cur.fetchall()]
