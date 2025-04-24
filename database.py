import sqlite3
import logging

logger = logging.getLogger(__name__)

DB_FILE = "telemon.db"

def init_db():
    """������������� ���� ������."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS torrents (
            id INTEGER PRIMARY KEY,
            url TEXT UNIQUE,
            title TEXT,
            last_updated TEXT,
            added_by INTEGER,
            added_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()
    logger.info("���� ������ ����������������")

def add_torrent(url: str, title: str, last_updated: str, added_by: int, added_at: str):
    """���������� ������� � ���� ������."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT OR REPLACE INTO torrents (url, title, last_updated, added_by, added_at) VALUES (?, ?, ?, ?, ?)",
            (url, title, last_updated, added_by, added_at)
        )
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"������ ���� ������: {e}")
    finally:
        conn.close()

def get_all_torrents():
    """��������� ���� ������ �� ���� ������."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, url, title, last_updated, added_by FROM torrents")
    torrents = cursor.fetchall()
    conn.close()
    return torrents
