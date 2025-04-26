import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger(__name__)
DB_FILE = "rutracker_bot.db"

def init_db():
    """Инициализация базы данных."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                is_admin INTEGER DEFAULT 0,
                added_at TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS series (
                id INTEGER PRIMARY KEY,
                url TEXT UNIQUE,
                title TEXT,
                last_updated TEXT,
                added_by INTEGER,
                added_at TEXT,
                FOREIGN KEY (added_by) REFERENCES users(user_id)
            )
        """)
        conn.commit()
    logger.info("База данных инициализирована")

def execute_query(query, params=(), fetchone=False, fetchall=False):
    """Универсальный метод для выполнения SQL-запросов."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            if fetchone:
                return cursor.fetchone()
            if fetchall:
                return cursor.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Ошибка выполнения запроса: {e}")
        return None

def add_series(url, title, last_updated, added_by):
    """Добавить сериал в базу данных."""
    query = """
        INSERT OR REPLACE INTO series (url, title, last_updated, added_by, added_at)
        VALUES (?, ?, ?, ?, ?)
    """
    params = (url, title, last_updated, added_by, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    return execute_query(query, params)

def update_series(series_id, title=None, last_updated=None):
    """Обновить информацию о сериале."""
    query = "UPDATE series SET "
    params = []
    if title:
        query += "title = ?, "
        params.append(title)
    if last_updated:
        query += "last_updated = ?, "
        params.append(last_updated)
    query = query.rstrip(", ") + " WHERE id = ?"
    params.append(series_id)
    return execute_query(query, params)

def get_all_series():
    """Получить список всех сериалов."""
    query = "SELECT id, url, title, last_updated, added_by, added_at FROM series"
    return execute_query(query, fetchall=True)

def remove_series(series_id):
    """Удалить сериал из базы данных."""
    query = "DELETE FROM series WHERE id = ?"
    return execute_query(query, (series_id,))

def series_exists(url):
    """Проверить, существует ли сериал в базе данных."""
    query = "SELECT 1 FROM series WHERE url = ?"
    return execute_query(query, (url,), fetchone=True) is not None