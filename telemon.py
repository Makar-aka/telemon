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


# Функция для скачивания торрент-файла
def download_torrent(url):
    try:
        response = rutracker_session.get(url, proxies=proxies)
        response.raise_for_status()
        return response.content
    except Exception as e:
        logger.error(f"Ошибка скачивания торрента {url}: {str(e)}")
        return None


# Функция для добавления торрента в qBittorrent
def add_torrent_to_qbittorrent(torrent_data):
    global qbt_client
    try:
        if qbt_client is None:
            logger.error("Клиент qBittorrent не инициализирован")
            return False

        qbt_client.torrents_add(torrent_files=torrent_data, category="from telegram")
        logger.info("Торрент добавлен в qBittorrent")
        return True
    except Exception as e:
        logger.error(f"Ошибка добавления торрента в qBittorrent: {str(e)}")
        return False


# Функция для очистки категории "from telegram" в qBittorrent
def clear_telegram_category():
    global qbt_client
    try:
        if qbt_client is None:
            logger.error("Клиент qBittorrent не инициализирован")
            return False
            
        torrents = qbt_client.torrents_info(category="from telegram")
        for torrent in torrents:
            qbt_client.torrents_delete(delete_files=False, hashes=torrent.hash)
        logger.info("Категория 'from telegram' очищена")
        return True
    except Exception as e:
        logger.error(f"Ошибка очистки категории: {str(e)}")
        return False


# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот для отслеживания обновлений раздач на RuTracker.\n"
        "Отправь мне ссылку на раздачу, и я буду следить за обновлениями.\n"
        "/help - показать справку\n"
        "/list - показать отслеживаемые раздачи\n"
        "/clear - очистить категорию 'from telegram' в qBittorrent\n"
        "/status - проверить статус подключений"
    )


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


# Команда /status
async def check_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = await update.message.reply_text("Проверяю подключения...")
    
    # Проверяем подключения
    proxy_status = check_proxy_connection()
    rutracker_status = check_rutracker_connection()
    qbt_status = init_qbittorrent() is not None
    
    status_text = (
        f"Статус подключений:\n\n"
        f"Прокси: {'✅ Подключено' if proxy_status else '❌ Ошибка подключения'}\n"
        f"RuTracker: {'✅ Доступен' if rutracker_status else '❌ Недоступен'}\n"
        f"qBittorrent: {'✅ Подключено' if qbt_status else '❌ Ошибка подключения'}\n"
        f"Текущий часовой пояс: {TIMEZONE}\n"
    )
    await message.edit_text(status_text)


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


# Обработчик ссылок
async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    
    # Проверка, что это ссылка на rutracker
    if not re.match(r'https?://rutracker\.org/forum/viewtopic\.php\?t=\d+', url):
        await update.message.reply_text("Пожалуйста, отправьте ссылку на раздачу rutracker.org")
        return
    
    # Сообщаем пользователю о начале обработки
    processing_msg = await update.message.reply_text("Обрабатываю ссылку, пожалуйста подождите...")
    
    # Парсим страницу
    page_data = parse_rutracker_page(url)
    if not page_data:
        await processing_msg.edit_text("Не удалось получить информацию о раздаче.")
        return
    
    user_id = update.message.from_user.id
    current_time = datetime.now(pytz.timezone(TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S")
    
    # Сохраняем в БД
    conn = sqlite3.connect("telemon.db")
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT OR REPLACE INTO torrents (url, title, last_updated, added_by, added_at) VALUES (?, ?, ?, ?, ?)",
            (url, page_data["title"], page_data["last_updated"], user_id, current_time)
        )
        conn.commit()
        
        # Скачиваем торрент и добавляем в qBittorrent
        if page_data["dl_link"]:
            torrent_data = download_torrent(page_data["dl_link"])
            if torrent_data:
                if add_torrent_to_qbittorrent(torrent_data):
                    await processing_msg.edit_text(
                        f"Раздача добавлена для отслеживания:\n"
                        f"Название: {page_data['title']}\n"
                        f"Последнее обновление: {page_data['last_updated']}\n"
                        f"Торрент добавлен в qBittorrent."
                    )
                else:
                    await processing_msg.edit_text(
                        f"Раздача добавлена для отслеживания, но не удалось добавить торрент в qBittorrent:\n"
                        f"Название: {page_data['title']}\n"
                        f"Последнее обновление: {page_data['last_updated']}"
                    )
            else:
                await processing_msg.edit_text(
                    f"Раздача добавлена для отслеживания, но не удалось скачать торрент-файл:\n"
                    f"Название: {page_data['title']}\n"
                    f"Последнее обновление: {page_data['last_updated']}"
                )
        else:
            await processing_msg.edit_text(
                f"Раздача добавлена для отслеживания, но ссылка на торрент не найдена:\n"
                f"Название: {page_data['title']}\n"
                f"Последнее обновление: {page_data['last_updated']}"
            )
    except sqlite3.Error as e:
        logger.error(f"Ошибка базы данных: {str(e)}")
        await processing_msg.edit_text(f"Произошла ошибка при сохранении в базу данных: {str(e)}")
    finally:
        conn.close()


# Функция для проверки обновлений раздач
async def check_updates(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Проверка обновлений...")
    conn = sqlite3.connect("telemon.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, url, title, last_updated, added_by FROM torrents")
    torrents = cursor.fetchall()
    conn.close()

    for torrent_id, url, title, last_updated, user_id in torrents:
        page_data = parse_rutracker_page(url)
        if not page_data:
            continue

        if page_data["last_updated"] != last_updated:
            logger.info(f"Обнаружено обновление для {title}")
            conn = sqlite3.connect("telemon.db")
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE torrents SET last_updated = ?, title = ? WHERE id = ?",
                (page_data["last_updated"], page_data["title"], torrent_id),
            )
            conn.commit()
            conn.close()

            if page_data["dl_link"]:
                torrent_data = download_torrent(page_data["dl_link"])
                if torrent_data and add_torrent_to_qbittorrent(torrent_data):
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"🔄 Обновление раздачи!\n\n"
                        f"Название: {page_data['title']}\n"
                        f"Новое время обновления: {page_data['last_updated']}\n"
                        f"Торрент добавлен в qBittorrent.",
                    )
                else:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"🔄 Обновление раздачи, но не удалось добавить торрент в qBittorrent!\n\n"
                        f"Название: {page_data['title']}\n"
                        f"Новое время обновления: {page_data['last_updated']}",
                    )
            else:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"🔄 Обновление раздачи, но ссылка на торрент не найдена!\n\n"
                    f"Название: {page_data['title']}\n"
                    f"Новое время обновления: {page_data['last_updated']}",
                )
        await asyncio.sleep(5)

    logger.info("Проверка обновлений завершена.")


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
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    application.job_queue.run_repeating(check_updates, interval=timedelta(seconds=CHECK_INTERVAL), first=10)

    # Запуск бота
    logger.info("Бот запущен.")
    await application.run_polling()


if __name__ == "__main__":
    asyncio.run(main())
