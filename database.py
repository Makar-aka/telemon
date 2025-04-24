import sqlite3
import logging
import pytz
from datetime import datetime
from config import TIMEZONE

logger = logging.getLogger(__name__)

DB_FILE = "rutracker_bot.db"

def init_db():
    """Инициализация базы данных."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            is_admin INTEGER DEFAULT 0,
            added_at TEXT
        )
        """
    )
    
    # Таблица сериалов (раздач)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS series (
            id INTEGER PRIMARY KEY,
            url TEXT UNIQUE,
            title TEXT,
            last_updated TEXT,
            added_by INTEGER,
            added_at TEXT,
            FOREIGN KEY (added_by) REFERENCES users(user_id)
        )
        """
    )
    
    conn.commit()
    conn.close()
    logger.info("База данных инициализирована")

def get_min_free_id():
    """Найти минимальный свободный ID для новой записи в таблице series."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        # Получаем все существующие ID
        cursor.execute("SELECT id FROM series ORDER BY id")
        existing_ids = [row[0] for row in cursor.fetchall()]
        
        # Если таблица пуста, начинаем с ID = 1
        if not existing_ids:
            return 1
            
        # Ищем первую "дырку" в последовательности ID
        expected_id = 1
        for id_value in existing_ids:
            if id_value > expected_id:
                # Нашли свободный ID
                return expected_id
            expected_id = id_value + 1
            
        # Если нет "дырок", возвращаем следующий ID после максимального
        return expected_id
    except sqlite3.Error as e:
        logger.error(f"Ошибка поиска минимального свободного ID: {e}")
        # В случае ошибки возвращаем None, и будет использован автоинкремент
        return None
    finally:
        conn.close()

def add_user(user_id: int, username: str, is_admin: bool = False):
    """Добавить пользователя в базу данных."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        cursor.execute(
            "INSERT OR REPLACE INTO users (user_id, username, is_admin, added_at) VALUES (?, ?, ?, ?)",
            (user_id, username, int(is_admin), now)
        )
        conn.commit()
        logger.info(f"Пользователь {username} (ID: {user_id}) добавлен в базу данных.")
        return True
    except sqlite3.Error as e:
        logger.error(f"Ошибка добавления пользователя: {e}")
        return False
    finally:
        conn.close()

def get_user(user_id: int):
    """Получить информацию о пользователе."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT user_id, username, is_admin FROM users WHERE user_id = ?", (user_id,))
        return cursor.fetchone()
    except sqlite3.Error as e:
        logger.error(f"Ошибка получения пользователя: {e}")
        return None
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
        return True
    except sqlite3.Error as e:
        logger.error(f"Ошибка удаления пользователя: {e}")
        return False
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

def make_admin(user_id: int):
    """Сделать пользователя администратором."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        cursor.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        logger.info(f"Пользователь с ID {user_id} стал администратором.")
        return True
    except sqlite3.Error as e:
        logger.error(f"Ошибка назначения администратора: {e}")
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

def has_admins():
    """Проверить наличие администраторов в системе."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1")
        count = cursor.fetchone()[0]
        return count > 0
    except sqlite3.Error as e:
        logger.error(f"Ошибка проверки наличия администраторов: {e}")
        return False
    finally:
        conn.close()

def add_series(url: str, title: str, last_updated: str, added_by: int):
    """Добавить сериал в базу данных."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now = datetime.now(pytz.timezone(TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        # Ищем свободный ID
        free_id = get_min_free_id()
        
        if free_id is not None:
            # Используем найденный свободный ID
            cursor.execute(
                "INSERT OR REPLACE INTO series (id, url, title, last_updated, added_by, added_at) VALUES (?, ?, ?, ?, ?, ?)",
                (free_id, url, title, last_updated, added_by, now)
            )
            series_id = free_id
        else:
            # Если поиск свободного ID не удался, используем автоинкремент
            cursor.execute(
                "INSERT OR REPLACE INTO series (url, title, last_updated, added_by, added_at) VALUES (?, ?, ?, ?, ?)",
                (url, title, last_updated, added_by, now)
            )
            series_id = cursor.lastrowid
            
        conn.commit()
        logger.info(f"Сериал {title} (URL: {url}) добавлен в базу данных с ID {series_id}.")
        return series_id
    except sqlite3.Error as e:
        logger.error(f"Ошибка добавления сериала: {e}")
        return None
    finally:
        conn.close()

def remove_series(series_id: int = None, url: str = None):
    """Удалить сериал из базы данных."""
    if not series_id and not url:
        logger.error("Необходимо указать series_id или url для удаления сериала.")
        return False
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        if series_id:
            cursor.execute("DELETE FROM series WHERE id = ?", (series_id,))
        elif url:
            cursor.execute("DELETE FROM series WHERE url = ?", (url,))
        conn.commit()
        logger.info(f"Сериал с ID {series_id} или URL {url} удалён из базы данных.")
        return True
    except sqlite3.Error as e:
        logger.error(f"Ошибка удаления сериала: {e}")
        return False
    finally:
        conn.close()

def update_series(series_id: int, title: str = None, last_updated: str = None):
    """Обновить информацию о сериале."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        if title:
            cursor.execute("UPDATE series SET title = ? WHERE id = ?", (title, series_id))
        if last_updated:
            cursor.execute("UPDATE series SET last_updated = ? WHERE id = ?", (last_updated, series_id))
        conn.commit()
        logger.info(f"Сериал с ID {series_id} обновлён.")
        return True
    except sqlite3.Error as e:
        logger.error(f"Ошибка обновления сериала: {e}")
        return False
    finally:
        conn.close()

def get_series(series_id: int = None, url: str = None):
    """Получить информацию о сериале."""
    if not series_id and not url:
        logger.error("Необходимо указать series_id или url для получения сериала.")
        return None
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        if series_id:
            cursor.execute("SELECT * FROM series WHERE id = ?", (series_id,))
        elif url:
            cursor.execute("SELECT * FROM series WHERE url = ?", (url,))
        return cursor.fetchone()
    except sqlite3.Error as e:
        logger.error(f"Ошибка получения сериала: {e}")
        return None
    finally:
        conn.close()

def get_all_series():
    """Получить список всех сериалов."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT id, url, title, last_updated, added_by, added_at FROM series")
        return cursor.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Ошибка получения списка сериалов: {e}")
        return []
    finally:
        conn.close()

def series_exists(url: str) -> bool:
    """Проверить, существует ли сериал в базе данных."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT 1 FROM series WHERE url = ?", (url,))
        return cursor.fetchone() is not None
    except sqlite3.Error as e:
        logger.error(f"Ошибка проверки существования сериала: {e}")
        return False
    finally:
        conn.close()
