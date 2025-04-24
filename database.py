import sqlite3
import logging

logger = logging.getLogger(__name__)

DB_FILE = "telemon.db"

def init_db():
    """Инициализация базы данных."""
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
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            is_admin INTEGER DEFAULT 0
        )
        """
    )
    conn.commit()
    conn.close()
    logger.info("База данных инициализирована")

def add_user(user_id: int, username: str, is_admin: bool = False):
    """Добавить пользователя в базу данных."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT OR REPLACE INTO users (user_id, username, is_admin) VALUES (?, ?, ?)",
            (user_id, username, int(is_admin))
        )
        conn.commit()
        logger.info(f"Пользователь {username} (ID: {user_id}) добавлен в базу данных.")
    except sqlite3.Error as e:
        logger.error(f"Ошибка добавления пользователя: {e}")
    finally:
        conn.close()

def remove_user(user_id: int):
    """Удалить пользователя из базы данных."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        conn.commit()
        logger.info(f"Пользователь с ID {user_id} удалён из базы данных.")
    except sqlite3.Error as e:
        logger.error(f"Ошибка удаления пользователя: {e}")
    finally:
        conn.close()

def is_admin(user_id: int) -> bool:
    """Проверить, является ли пользователь администратором."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        return result is not None and result[0] == 1
    except sqlite3.Error as e:
        logger.error(f"Ошибка проверки администратора: {e}")
        return False
    finally:
        conn.close()

def get_all_users():
    """Получить список всех пользователей."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT user_id, username, is_admin FROM users")
        return cursor.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Ошибка получения списка пользователей: {e}")
        return []
    finally:
        conn.close()
