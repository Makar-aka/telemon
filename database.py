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
            return True
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
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            return cursor.lastrowid
    except sqlite3.Error as e:
        logger.error(f"Ошибка добавления сериала: {e}")
        return None

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

def get_all_series(series_id=None):
    """Получить список всех сериалов или конкретный сериал по ID."""
    if series_id is not None:
        query = "SELECT id, url, title, last_updated, added_by, added_at FROM series WHERE id = ?"
        return execute_query(query, (series_id,), fetchone=True)
    else:
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

def get_all_users():
    """Получить список всех пользователей."""
    query = "SELECT user_id, username, is_admin FROM users"
    return execute_query(query, fetchall=True)

def add_user(user_id, username, is_admin=False):
    """Добавить пользователя в базу данных."""
    query = """
        INSERT OR REPLACE INTO users (user_id, username, is_admin, added_at)
        VALUES (?, ?, ?, ?)
    """
    params = (user_id, username, 1 if is_admin else 0, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    return execute_query(query, params)

def remove_user(user_id):
    """Удалить пользователя из базы данных."""
    query = "DELETE FROM users WHERE user_id = ?"
    return execute_query(query, (user_id,))

def make_admin(user_id):
    """Сделать пользователя администратором."""
    query = "UPDATE users SET is_admin = 1 WHERE user_id = ?"
    return execute_query(query, (user_id,))

def is_user_allowed(user_id, admin_required=False):
    """
    Проверить, имеет ли пользователь доступ к боту.
    
    Args:
        user_id: ID пользователя
        admin_required: True, если требуются права администратора
    
    Returns:
        bool: True, если пользователь имеет доступ, False в противном случае
    """
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            if admin_required:
                cursor.execute("SELECT 1 FROM users WHERE user_id = ? AND is_admin = 1", (user_id,))
            else:
                cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
            return cursor.fetchone() is not None
    except sqlite3.Error as e:
        logger.error(f"Ошибка проверки пользователя: {e}")
        return False

def has_admins():
    """Проверить наличие администраторов в базе данных."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1")
            count = cursor.fetchone()[0]
            return count > 0
    except sqlite3.Error as e:
        logger.error(f"Ошибка проверки наличия администраторов: {e}")
        return False
