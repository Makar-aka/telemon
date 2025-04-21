#!/usr/bin/env python3
import os
import re
import logging
import sqlite3
import requests
import threading
import time
from dotenv import load_dotenv
from datetime import datetime, timedelta
import pytz
from bs4 import BeautifulSoup
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
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

# Инициализация глобальных объектов
bot = telebot.TeleBot(TELEGRAM_TOKEN)
rutracker_session = requests.Session()
qbt_client = None
stop_event = threading.Event()  # Событие для остановки фонового потока

# ПЕРЕПОДКЛЮЧЕНИЕ
RECONNECT_INTERVAL = 300  # 5 минут в секундах
last_connection_attempt = {
    "rutracker": datetime.min,
    "qbittorrent": datetime.min
}

# Настройка прокси для requests
if PROXY_URL:
    proxies = {
        "http": f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_URL}",
        "https": f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_URL}",
    }
else:
    proxies = None


# ===== ФУНКЦИИ ДЛЯ РАБОТЫ С ПОДКЛЮЧЕНИЯМИ =====

# Функция для проверки необходимости повторного подключения
def should_reconnect(service):
    now = datetime.now()
    if (now - last_connection_attempt[service]).total_seconds() >= RECONNECT_INTERVAL:
        last_connection_attempt[service] = now
        return True
    return False

# Функция для авторизации на RuTracker
def login_to_rutracker():
    login_url = "https://rutracker.org/forum/login.php"
    payload = {
        "login_username": RUTRACKER_USERNAME,
        "login_password": RUTRACKER_PASSWORD,
        "login": "Вход",
    }

    try:
        response = rutracker_session.post(login_url, data=payload, proxies=proxies, timeout=20)
        response.raise_for_status()

        # Проверка успешности входа
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
    if not PROXY_URL:
        logger.info("Прокси не настроен, проверка пропущена")
        return True

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
    global qbt_client
    try:
        qbt_client = QBittorrentClient(
            host=QBITTORRENT_URL,
            username=QBITTORRENT_USERNAME,
            password=QBITTORRENT_PASSWORD,
        )
        qbt_client.auth_log_in()
        version = qbt_client.app.version
        logger.info(f"Успешное подключение к qBittorrent. Версия: {version}")
        return True
    except Exception as e:
        logger.error(f"Не удалось подключиться к qBittorrent: {str(e)}")
        qbt_client = None
        return False


# Проверка всех подключений
def check_connections():
    results = {
        "proxy": check_proxy_connection(),
        "rutracker": login_to_rutracker() and check_rutracker_connection(),
        "qbittorrent": init_qbittorrent(),
    }

    logger.info("===== Статус подключений =====")
    for service, status in results.items():
        status_text = "✅ ПОДКЛЮЧЕНО" if status else "❌ ОШИБКА"
        logger.info(f"{service.upper()}: {status_text}")
    logger.info("============================")

    return results


# Функция для периодической проверки подключений и переподключения
def reconnect_services():
    global qbt_client
    
    while not stop_event.is_set():
        reconnected = False
        
        # Проверяем подключение к RuTracker и переподключаемся при необходимости
        if should_reconnect("rutracker"):
            logger.info("Попытка переподключения к RuTracker...")
            if login_to_rutracker():
                logger.info("Успешное переподключение к RuTracker")
                reconnected = True
            else:
                logger.warning("Не удалось переподключиться к RuTracker, следующая попытка через 5 минут")
        
        # Проверяем подключение к qBittorrent и переподключаемся при необходимости
        if should_reconnect("qbittorrent") and qbt_client is None:
            logger.info("Попытка переподключения к qBittorrent...")
            if init_qbittorrent():
                logger.info("Успешное переподключение к qBittorrent")
                reconnected = True
            else:
                logger.warning("Не удалось переподключиться к qBittorrent, следующая попытка через 5 минут")
        
        # Если были успешные переподключения, обновляем статус
        if reconnected:
            results = {
                "proxy": check_proxy_connection(),
                "rutracker": "bb_session" in rutracker_session.cookies,
                "qbittorrent": qbt_client is not None,
            }
            logger.info("===== Обновленный статус подключений =====")
            for service, status in results.items():
                status_text = "✅ ПОДКЛЮЧЕНО" if status else "❌ ОШИБКА"
                logger.info(f"{service.upper()}: {status_text}")
            logger.info("===================================")
        
        # Ждем следующую проверку или сигнал остановки
        for _ in range(60):  # Проверка каждую минуту на случай остановки потока
            if stop_event.is_set():
                break
            time.sleep(1)


# ===== ФУНКЦИИ ДЛЯ РАБОТЫ С БАЗОЙ ДАННЫХ =====

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


# ===== ФУНКЦИИ ДЛЯ РАБОТЫ С RUTRACKER =====

# Функция для получения ID темы из URL
def get_topic_id(url):
    match = re.search(r't=(\d+)', url)
    if match:
        return match.group(1)
    return None


# Функция для парсинга страницы раздачи
def parse_rutracker_page(url):
    try:
        # Если нет активной сессии, пытаемся переподключиться
        if "bb_session" not in rutracker_session.cookies:
            logger.warning("Сессия RuTracker не активна, попытка переподключения...")
            if not login_to_rutracker():
                logger.error("Не удалось переподключиться к RuTracker")
                return None
        
        response = rutracker_session.get(url, proxies=proxies, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        title = soup.select_one("h1.maintitle")
        if not title:
            logger.error(f"Не удалось найти заголовок раздачи на странице {url}")
            return None
        title = title.text.strip()
        
        update_info = soup.select_one("p.post-time")
        last_updated = update_info.text.strip() if update_info else "Неизвестно"
        
        topic_id = get_topic_id(url)
        if not topic_id:
            logger.error(f"Не удалось извлечь ID темы из URL {url}")
            return None
            
        dl_link = f"https://rutracker.org/forum/dl.php?t={topic_id}"
        
        return {"title": title, "last_updated": last_updated, "dl_link": dl_link}
    except Exception as e:
        logger.error(f"Ошибка парсинга страницы {url}: {str(e)}")
        return None


# Функция для скачивания торрент-файла
def download_torrent(url):
    try:
        # Если нет активной сессии, пытаемся переподключиться
        if "bb_session" not in rutracker_session.cookies:
            logger.warning("Сессия RuTracker не активна, попытка переподключения...")
            if not login_to_rutracker():
                logger.error("Не удалось переподключиться к RuTracker")
                return None
                
        logger.info(f"Скачивание торрента: {url}")
        response = rutracker_session.get(url, proxies=proxies, timeout=30)
        response.raise_for_status()
        
        # Проверка, что действительно получен торрент-файл, а не страница с ошибкой
        content_type = response.headers.get('content-type', '')
        if 'html' in content_type.lower():
            logger.error(f"Получен HTML вместо торрент-файла. Возможно, требуется авторизация.")
            # Повторная авторизация и попытка скачивания
            if login_to_rutracker():
                response = rutracker_session.get(url, proxies=proxies, timeout=30)
                response.raise_for_status()
                if 'html' not in response.headers.get('content-type', '').lower():
                    return response.content
            return None
            
        return response.content
    except requests.exceptions.ProxyError as e:
        logger.error(f"Ошибка прокси при скачивании торрента {url}: {str(e)}")
        
        # Пробуем скачать без прокси, если это возможно
        try:
            logger.info("Пробуем скачать без прокси...")
            response = rutracker_session.get(url, timeout=30, proxies=None)
            response.raise_for_status()
            return response.content
        except Exception as e2:
            logger.error(f"Ошибка скачивания торрента без прокси {url}: {str(e2)}")
            return None
    except Exception as e:
        logger.error(f"Ошибка скачивания торрента {url}: {str(e)}")
        return None


# ===== ФУНКЦИИ ДЛЯ РАБОТЫ С QBITTORRENT =====

# Функция для добавления торрента в qBittorrent
def add_torrent_to_qbittorrent(torrent_data):
    global qbt_client
    try:
        if qbt_client is None:
            logger.error("Клиент qBittorrent не инициализирован, попытка переподключения...")
            if not init_qbittorrent():
                logger.error("Не удалось переподключиться к qBittorrent")
                return False

        qbt_client.torrents_add(torrent_files=torrent_data, category="from telegram")
        logger.info("Торрент добавлен в qBittorrent")
        return True
    except Exception as e:
        logger.error(f"Ошибка добавления торрента в qBittorrent: {str(e)}")
        qbt_client = None  # Сбрасываем клиент, чтобы при следующем обращении была попытка переподключения
        return False


# Функция для очистки категории "from telegram" в qBittorrent
def clear_telegram_category():
    global qbt_client
    try:
        if qbt_client is None:
            logger.error("Клиент qBittorrent не инициализирован, попытка переподключения...")
            if not init_qbittorrent():
                logger.error("Не удалось переподключиться к qBittorrent")
                return False
            
        torrents = qbt_client.torrents_info(category="from telegram")
        for torrent in torrents:
            qbt_client.torrents_delete(delete_files=False, hashes=torrent.hash)
        logger.info("Категория 'from telegram' очищена")
        return True
    except Exception as e:
        logger.error(f"Ошибка очистки категории: {str(e)}")
        qbt_client = None  # Сбрасываем клиент, чтобы при следующем обращении была попытка переподключения
        return False


# ===== ФУНКЦИИ ДЛЯ ФОНОВОГО МОНИТОРИНГА =====

# Функция для проверки обновлений раздач
def check_updates():
    # Проверка подключения к RuTracker перед выполнением
    if "bb_session" not in rutracker_session.cookies:
        logger.warning("Нет подключения к RuTracker, пробуем переподключиться перед проверкой...")
        if not login_to_rutracker():
            logger.error("Не удалось подключиться к RuTracker, проверка обновлений пропущена")
            return
        
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
            
            # Обновляем информацию в базе
            conn = sqlite3.connect("telemon.db")
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE torrents SET last_updated = ?, title = ? WHERE id = ?",
                (page_data["last_updated"], page_data["title"], torrent_id),
            )
            conn.commit()
            conn.close()

            # Скачиваем и добавляем торрент
            if page_data["dl_link"]:
                torrent_data = download_torrent(page_data["dl_link"])
                if torrent_data and add_torrent_to_qbittorrent(torrent_data):
                    try:
                        bot.send_message(
                            user_id,
                            f"🔄 *Обновление раздачи!*\n\n"
                            f"Название: {page_data['title']}\n"
                            f"Новое время обновления: {page_data['last_updated']}\n"
                            f"Торрент добавлен в qBittorrent.",
                            parse_mode="Markdown"
                        )
                    except Exception as e:
                        logger.error(f"Ошибка отправки сообщения: {e}")
                else:
                    try:
                        bot.send_message(
                            user_id,
                            f"🔄 *Обновление раздачи*, но не удалось добавить торрент в qBittorrent!\n\n"
                            f"Название: {page_data['title']}\n"
                            f"Новое время обновления: {page_data['last_updated']}",
                            parse_mode="Markdown"
                        )
                    except Exception as e:
                        logger.error(f"Ошибка отправки сообщения: {e}")
            else:
                try:
                    bot.send_message(
                        user_id,
                        f"🔄 *Обновление раздачи*, но ссылка на торрент не найдена!\n\n"
                        f"Название: {page_data['title']}\n"
                        f"Новое время обновления: {page_data['last_updated']}",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.error(f"Ошибка отправки сообщения: {e}")
                    
        time.sleep(5)  # Пауза между проверками раздач
    
    logger.info("Проверка обновлений завершена")


# Функция для периодической проверки обновлений
def monitor_updates():
    while not stop_event.is_set():
        try:
            check_updates()
        except Exception as e:
            logger.error(f"Ошибка при проверке обновлений: {e}")
        
        # Ждем следующую проверку или сигнал остановки
        for _ in range(CHECK_INTERVAL):
            if stop_event.is_set():
                break
            time.sleep(1)


# ===== ОБРАБОТЧИКИ КОМАНД ТЕЛЕГРАМ-БОТА =====

# Обработчик команды /start
@bot.message_handler(commands=['start'])
def handle_start(message):
    bot.send_message(
        message.chat.id,
        "Привет! Я бот для отслеживания обновлений раздач на RuTracker.\n"
        "Отправь мне ссылку на раздачу, и я буду следить за обновлениями.\n"
        "/help - показать справку\n"
        "/list - показать отслеживаемые раздачи\n"
        "/clear - очистить категорию 'from telegram' в qBittorrent\n"
        "/status - проверить статус подключений"
    )


# Обработчик команды /help
@bot.message_handler(commands=['help'])
def handle_help(message):
    bot.send_message(
        message.chat.id,
        "Список доступных команд:\n"
        "/start - начать работу с ботом\n"
        "/help - показать справку\n"
        "/list - показать отслеживаемые раздачи\n"
        "/clear - очистить категорию 'from telegram' в qBittorrent\n"
        "/status - проверить статус подключений\n\n"
        "Чтобы добавить раздачу для отслеживания, просто отправь мне ссылку на неё."
    )


# Обработчик команды /list
@bot.message_handler(commands=['list'])
def handle_list(message):
    user_id = message.from_user.id
    conn = sqlite3.connect("telemon.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, url FROM torrents WHERE added_by = ?", (user_id,))
    torrents = cursor.fetchall()
    conn.close()

    if not torrents:
        bot.send_message(message.chat.id, "У вас нет отслеживаемых раздач.")
        return

    response = "Ваши отслеживаемые раздачи:\n\n"
    for torrent_id, title, url in torrents:
        response += f"{torrent_id}. {title}\n{url}\n\n"

    bot.send_message(message.chat.id, response)


# Обработчик команды /clear
@bot.message_handler(commands=['clear'])
def handle_clear(message):
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("Да", callback_data="clear_yes"),
        InlineKeyboardButton("Нет", callback_data="clear_no")
    )
    bot.send_message(
        message.chat.id,
        "Вы уверены, что хотите очистить категорию 'from telegram' в qBittorrent?",
        reply_markup=markup
    )


# Обработчик команды /status
@bot.message_handler(commands=['status'])
def handle_status(message):
    status_msg = bot.send_message(message.chat.id, "Проверяю подключения...")
    
    results = check_connections()
    
    status_text = (
        f"Статус подключений:\n\n"
        f"Прокси: {'✅ Подключено' if results['proxy'] else '❌ Ошибка подключения'}\n"
        f"RuTracker: {'✅ Доступен' if results['rutracker'] else '❌ Недоступен'}\n"
        f"qBittorrent: {'✅ Подключено' if results['qbittorrent'] else '❌ Ошибка подключения'}\n"
        f"Текущий часовой пояс: {TIMEZONE}\n"
    )
    
    bot.edit_message_text(
        status_text,
        chat_id=message.chat.id,
        message_id=status_msg.message_id
    )


# Обработчик нажатий на кнопки
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.data == "clear_yes":
        if clear_telegram_category():
            bot.edit_message_text(
                "Категория 'from telegram' очищена.",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id
            )
        else:
            bot.edit_message_text(
                "Не удалось очистить категорию. Проверьте логи.",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id
            )
    elif call.data == "clear_no":
        bot.edit_message_text(
            "Операция отменена.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )


# Обработчик ссылок
@bot.message_handler(func=lambda message: message.text and message.text.startswith('http'))
def handle_url(message):
    url = message.text.strip()
    
    # Проверка, что это ссылка на rutracker
    if not re.match(r'https?://rutracker\.org/forum/viewtopic\.php\?t=\d+', url):
        bot.send_message(message.chat.id, "Пожалуйста, отправьте ссылку на раздачу rutracker.org")
        return
    
    # Сообщаем пользователю о начале обработки
    processing_msg = bot.send_message(message.chat.id, "Обрабатываю ссылку, пожалуйста подождите...")
    
    # Парсим страницу
    page_data = parse_rutracker_page(url)
    if not page_data:
        bot.edit_message_text(
            "Не удалось получить информацию о раздаче.",
            chat_id=message.chat.id,
            message_id=processing_msg.message_id
        )
        return
    
    user_id = message.from_user.id
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
                    bot.edit_message_text(
                        f"Раздача добавлена для отслеживания:\n"
                        f"Название: {page_data['title']}\n"
                        f"Последнее обновление: {page_data['last_updated']}\n"
                        f"Торрент добавлен в qBittorrent.",
                        chat_id=message.chat.id,
                        message_id=processing_msg.message_id
                    )
                else:
                    bot.edit_message_text(
                        f"Раздача добавлена для отслеживания, но не удалось добавить торрент в qBittorrent:\n"
                        f"Название: {page_data['title']}\n"
                        f"Последнее обновление: {page_data['last_updated']}",
                        chat_id=message.chat.id,
                        message_id=processing_msg.message_id
                    )
            else:
                bot.edit_message_text(
                    f"Раздача добавлена для отслеживания, но не удалось скачать торрент-файл:\n"
                    f"Название: {page_data['title']}\n"
                    f"Последнее обновление: {page_data['last_updated']}",
                    chat_id=message.chat.id,
                    message_id=processing_msg.message_id
                )
        else:
            bot.edit_message_text(
                f"Раздача добавлена для отслеживания, но ссылка на торрент не найдена:\n"
                f"Название: {page_data['title']}\n"
                f"Последнее обновление: {page_data['last_updated']}",
                chat_id=message.chat.id,
                message_id=processing_msg.message_id
            )
    except sqlite3.Error as e:
        logger.error(f"Ошибка базы данных: {str(e)}")
        bot.edit_message_text(
            f"Произошла ошибка при сохранении в базу данных: {str(e)}",
            chat_id=message.chat.id,
            message_id=processing_msg.message_id
        )
    finally:
        conn.close()


# ===== ОСНОВНАЯ ЛОГИКА =====

def main():
    # Инициализация базы данных
    init_db()
    
    # Проверка подключений - позволяем продолжить даже при неудаче
    logger.info("Проверка подключений...")
    results = check_connections()
    
    if not all(results.values()):
        logger.warning("Не все подключения успешны, но бот будет запущен. "
                      "Будут производиться повторные попытки подключения каждые 5 минут.")
    
    # Запуск фонового потока для мониторинга обновлений
    monitor_thread = threading.Thread(target=monitor_updates, name="MonitorThread")
    monitor_thread.daemon = True
    monitor_thread.start()
    
    # Запуск фонового потока для переподключений
    reconnect_thread = threading.Thread(target=reconnect_services, name="ReconnectThread")
    reconnect_thread.daemon = True
    reconnect_thread.start()
    
    # Запуск бота в бесконечном цикле
    logger.info("Бот запущен. Нажмите Ctrl+C для остановки.")
    
    try:
        # Запуск бота
        bot.polling(none_stop=True, interval=0)
    except KeyboardInterrupt:
        stop_event.set()  # Сигнал для остановки фоновых потоков
        logger.info("Остановка бота...")
    except Exception as e:
        logger.error(f"Ошибка работы бота: {e}")
        stop_event.set()
    
    # Дожидаемся завершения фоновых потоков
    threads = [monitor_thread, reconnect_thread]
    for thread in threads:
        if thread.is_alive():
            thread.join(timeout=5)


if __name__ == "__main__":
    main()
