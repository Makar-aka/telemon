import os
import re
import logging
import sqlite3
import requests
import asyncio
import pytz
from dotenv import load_dotenv
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from qbittorrentapi import Client as QBittorrentClient

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

# Получение настроек из .env
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
PROXY_URL = os.getenv("PROXY_URL")
PROXY_USERNAME = os.getenv("PROXY_USERNAME")
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD")
QBITTORRENT_URL = os.getenv("QBITTORRENT_URL")
QBITTORRENT_USERNAME = os.getenv("QBITTORRENT_USERNAME")
QBITTORRENT_PASSWORD = os.getenv("QBITTORRENT_PASSWORD")
RUTRACKER_USERNAME = os.getenv("RUTRACKER_USERNAME")
RUTRACKER_PASSWORD = os.getenv("RUTRACKER_PASSWORD")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "3600"))  # Интервал проверки в секундах
TIMEZONE = os.getenv("TIMEZONE", "Europe/Moscow")  # Часовой пояс

# Настройка прокси для requests
proxies = {
    "http": f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_URL}",
    "https": f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_URL}",
}

# Инициализация глобальных переменных
qbt_client = None
rutracker_session = requests.Session()  # Сессия для авторизации на RuTracker


# Функция для авторизации на RuTracker
def login_to_rutracker():
    login_url = "https://rutracker.org/forum/login.php"
    payload = {
        "login_username": RUTRACKER_USERNAME,
        "login_password": RUTRACKER_PASSWORD,
        "login": "Вход",  # Это значение кнопки входа
    }

    try:
        # Выполняем POST-запрос для авторизации
        response = rutracker_session.post(login_url, data=payload, proxies=proxies, timeout=10)
        response.raise_for_status()

        # Проверяем, успешен ли вход (например, по наличию куки)
        if "bb_session" in rutracker_session.cookies:
            logger.info("Успешная авторизация на RuTracker")
            return True
        else:
            logger.error("Не удалось авторизоваться на RuTracker. Проверьте логин и пароль.")
            return False
    except Exception as e:
        logger.error(f"Ошибка авторизации на RuTracker: {str(e)}")
        return False


# Функция проверки подключения к прокси
def check_proxy_connection():
    try:
        response = requests.get("https://api.ipify.org", proxies=proxies, timeout=10)
        if response.status_code == 200:
            logger.info(f"Подключение к прокси успешно. Внешний IP: {response.text}")
            return True
        else:
            logger.error(f"Не удалось подключиться к прокси. Код статуса: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"Не удалось подключиться к прокси: {str(e)}")
        return False


# Функция проверки подключения к RuTracker
def check_rutracker_connection():
    try:
        response = rutracker_session.get("https://rutracker.org", proxies=proxies, timeout=10)
        if response.status_code == 200:
            logger.info("Подключение к RuTracker успешно")
            return True
        else:
            logger.error(f"Не удалось подключиться к RuTracker. Код статуса: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"Не удалось подключиться к RuTracker: {str(e)}")
        return False


# Инициализация и проверка клиента qBittorrent
def init_qbittorrent():
    try:
        qbt_client = QBittorrentClient(
            host=QBITTORRENT_URL,
            username=QBITTORRENT_USERNAME,
            password=QBITTORRENT_PASSWORD,
        )
        qbt_client.auth_log_in()
        version = qbt_client.app.version
        logger.info(f"Успешное подключение к qBittorrent. Версия: {version}")
        return qbt_client
    except Exception as e:
        logger.error(f"Не удалось подключиться к qBittorrent: {str(e)}")
        return None


# Проверка всех подключений при запуске
def check_connections():
    results = {
        "proxy": check_proxy_connection(),
        "rutracker": login_to_rutracker() and check_rutracker_connection(),
        "qbittorrent": init_qbittorrent() is not None,
    }

    logger.info("===== Статус подключений =====")
    for service, status in results.items():
        status_text = "✅ ПОДКЛЮЧЕНО" if status else "❌ ОШИБКА"
        logger.info(f"{service.upper()}: {status_text}")
    logger.info("============================")

    return all(results.values())


# Инициализация базы данных
def init_db():
    conn = sqlite3.connect("telemon.db")
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
    logger.info("База данных инициализирована")


# Функция для парсинга страницы раздачи
def parse_rutracker_page(url):
    try:
        response = rutracker_session.get(url, proxies=proxies)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        title = soup.select_one("h1.maintitle").text.strip()
        update_info = soup.select_one("p.post-time")
        last_updated = update_info.text.strip() if update_info else None
        dl_link_elem = soup.select_one("a.dl-stub")
        dl_link = f"https://rutracker.org{dl_link_elem['href']}" if dl_link_elem else None

        return {"title": title, "last_updated": last_updated, "dl_link": dl_link}
    except Exception as e:
        logger.error(f"Ошибка парсинга страницы {url}: {str(e)}")
        return None


# Команда /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Список доступных команд:\n"
        "/start - начать работу с ботом\n"
        "/help - показать справку\n"
        "/list - показать отслеживаемые раздачи\n"
        "/clear - очистить категорию 'from telegram' в qBittorrent\n"
        "/status - проверить статус подключений\n\n"
        "Чтобы добавить раздачу для отслеживания, просто отправь мне ссылку на неё."
    )


# Команда /list
async def list_torrents(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    conn = sqlite3.connect("telemon.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, url FROM torrents WHERE added_by = ?", (user_id,))
    torrents = cursor.fetchall()
    conn.close()

    if not torrents:
        await update.message.reply_text("У вас нет отслеживаемых раздач.")
        return

    message = "Ваши отслеживаемые раздачи:\n\n"
    for torrent_id, title, url in torrents:
        message += f"{torrent_id}. {title}\n{url}\n\n"

    await update.message.reply_text(message)


# Команда /clear
async def clear_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("Да", callback_data="clear_yes"),
            InlineKeyboardButton("Нет", callback_data="clear_no"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Вы уверены, что хотите очистить категорию 'from telegram' в qBittorrent?",
        reply_markup=reply_markup,
    )


# Обработчик кнопок
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "clear_yes":
        if clear_telegram_category():
            await query.edit_message_text(text="Категория 'from telegram' очищена.")
        else:
            await query.edit_message_text(text="Не удалось очистить категорию. Проверьте логи.")
    elif query.data == "clear_no":
        await query.edit_message_text(text="Операция отменена.")


# Остальные функции остаются без изменений (например, download_torrent, add_torrent_to_qbittorrent, команды Telegram)

async def main():
    global qbt_client

    # Инициализация БД
    init_db()

    # Проверка подключений
    logger.info("Проверка подключений...")
    if not check_connections():
        logger.error("Ошибка подключения. Завершение работы.")
        return

    # Инициализация qBittorrent
    qbt_client = init_qbittorrent()

    # Создание приложения
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Добавление обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("list", list_torrents))
    application.add_handler(CommandHandler("clear", clear_category))
    application.add_handler(CommandHandler("status", check_status))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.job_queue.run_repeating(check_updates, interval=timedelta(seconds=CHECK_INTERVAL), first=10)

    # Запуск бота
    logger.info("Бот запущен.")
    await application.run_polling()


if __name__ == "__main__":
    asyncio.run(main())
