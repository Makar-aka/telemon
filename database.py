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

def add_torrent(url: str, title: str, last_updated: str, added_by: int, added_at: str):
    """Добавить раздачу в базу данных."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT OR REPLACE INTO torrents (url, title, last_updated, added_by, added_at) VALUES (?, ?, ?, ?, ?)",
            (url, title, last_updated, added_by, added_at)
        )
        conn.commit()
        logger.info(f"Раздача {title} (URL: {url}) добавлена в базу данных.")
    except sqlite3.Error as e:
        logger.error(f"Ошибка добавления раздачи: {e}")
    finally:
        conn.close()

def remove_torrent(torrent_id: int = None, url: str = None):
    """Удалить раздачу из базы данных."""
    if not torrent_id and not url:
        logger.error("Необходимо указать torrent_id или url для удаления раздачи.")
        return
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        if torrent_id:
            cursor.execute("DELETE FROM torrents WHERE id = ?", (torrent_id,))
        elif url:
            cursor.execute("DELETE FROM torrents WHERE url = ?", (url,))
        conn.commit()
        logger.info(f"Раздача с ID {torrent_id} или URL {url} удалена из базы данных.")
    except sqlite3.Error as e:
        logger.error(f"Ошибка удаления раздачи: {e}")
    finally:
        conn.close()

def update_torrent(torrent_id: int, title: str = None, last_updated: str = None):
    """Обновить информацию о раздаче."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        if title:
            cursor.execute("UPDATE torrents SET title = ? WHERE id = ?", (title, torrent_id))
        if last_updated:
            cursor.execute("UPDATE torrents SET last_updated = ? WHERE id = ?", (last_updated, torrent_id))
        conn.commit()
        logger.info(f"Раздача с ID {torrent_id} обновлена.")
    except sqlite3.Error as e:
        logger.error(f"Ошибка обновления раздачи: {e}")
    finally:
        conn.close()

def get_torrent(torrent_id: int = None, url: str = None):
    """Получить информацию о раздаче."""
    if not torrent_id and not url:
        logger.error("Необходимо указать torrent_id или url для получения раздачи.")
        return None
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        if torrent_id:
            cursor.execute("SELECT * FROM torrents WHERE id = ?", (torrent_id,))
        elif url:
            cursor.execute("SELECT * FROM torrents WHERE url = ?", (url,))
        return cursor.fetchone()
    except sqlite3.Error as e:
        logger.error(f"Ошибка получения раздачи: {e}")
        return None
    finally:
        conn.close()

def get_all_torrents():
    """Получить список всех раздач."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM torrents")
        return cursor.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Ошибка получения списка раздач: {e}")
        return []
    finally:
        conn.close()

def torrent_exists(url: str) -> bool:
    """Проверить, существует ли раздача в базе данных."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT 1 FROM torrents WHERE url = ?", (url,))
        return cursor.fetchone() is not None
    except sqlite3.Error as e:
        logger.error(f"Ошибка проверки существования раздачи: {e}")
        return False
    finally:
        conn.close()

