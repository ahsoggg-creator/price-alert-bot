import sqlite3
from datetime import datetime

DB_PATH = "items.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                url TEXT NOT NULL,
                title TEXT,
                target_price REAL NOT NULL,
                last_price REAL,
                notified INTEGER DEFAULT 0,
                added_at TEXT
            )
        """)


def add_item(chat_id, url, title, target_price, price):
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO items (chat_id, url, title, target_price, last_price, added_at) VALUES (?, ?, ?, ?, ?, ?)",
            (chat_id, url, title, target_price, price, datetime.now().isoformat(timespec="seconds")),
        )
        return cur.lastrowid


def get_items(chat_id=None):
    with get_connection() as conn:
        if chat_id is None:
            return conn.execute("SELECT * FROM items").fetchall()
        return conn.execute("SELECT * FROM items WHERE chat_id = ? ORDER BY id", (chat_id,)).fetchall()


def delete_item(chat_id, item_id):
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM items WHERE id = ? AND chat_id = ?", (item_id, chat_id))
        return cur.rowcount > 0


def update_item(item_id, price, notified):
    with get_connection() as conn:
        conn.execute("UPDATE items SET last_price = ?, notified = ? WHERE id = ?", (price, int(notified), item_id))
