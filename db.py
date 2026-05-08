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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS classification_cache (
                text_hash TEXT PRIMARY KEY,
                labels TEXT NOT NULL,
                created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS checkin_snapshot (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                grouped TEXT NOT NULL,
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


def get_classification(text_hash: str) -> list[str] | None:
    with _db() as conn:
        cur = conn.execute(
            "SELECT labels FROM classification_cache WHERE text_hash = ?",
            (text_hash,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return json.loads(row["labels"])


def put_classification(text_hash: str, labels: list[str]) -> None:
    with _db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO classification_cache (text_hash, labels) VALUES (?, ?)",
            (text_hash, json.dumps(labels)),
        )


def get_snapshot() -> tuple[dict, str] | None:
    with _db() as conn:
        cur = conn.execute(
            "SELECT grouped, created_at FROM checkin_snapshot WHERE id = 1"
        )
        row = cur.fetchone()
    if row is None:
        return None
    return json.loads(row["grouped"]), row["created_at"]


def put_snapshot(grouped: dict) -> None:
    with _db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO checkin_snapshot (id, grouped, created_at) "
            "VALUES (1, ?, strftime('%Y-%m-%dT%H:%M:%S', 'now'))",
            (json.dumps(grouped),),
        )
