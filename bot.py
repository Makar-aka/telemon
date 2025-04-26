import logging
from telebot import TeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import TELEGRAM_TOKEN, PROXY_URL
from database import (
    init_db, add_user, get_user, remove_user, is_admin, make_admin, get_all_users, has_admins,
    add_series, remove_series, update_series, get_series, get_all_series, series_exists
)
from rutracker_client import RutrackerClient
from qbittorrent_client import QBittorrentClient

logger = logging.getLogger(__name__)

# Инициализация бота
bot = TeleBot(TELEGRAM_TOKEN)
rutracker = RutrackerClient()
qbittorrent = QBittorrentClient()

# Словарь для хранения состояний пользователей
user_states = {}

# Состояния (конечный автомат)
class State:
    IDLE = 0
    WAITING_FOR_URL = 1
    WAITING_FOR_USER_ID = 2
    WAITING_FOR_ADMIN_ID = 3
    WAITING_FOR_USER_ID_TO_DELETE = 4

# Декоратор для проверки доступа администратора
def admin_required(func):
    def wrapper(message, *args, **kwargs):
        user_id = message.from_user.id
        
        # Если администраторов нет, то первый пользователь становится администратором
        if not has_admins():
            user = get_user(user_id)
            if not user:
                add_user(user_id, message.from_user.username or str(user_id), is_admin=True)
                bot.send_message(
                    message.chat.id,
                    "Вы стали первым пользователем и получили права администратора."
                )
            else:
                make_admin(user_id)
                bot.send_message(
                    message.chat.id,
                    "Вы получили права администратора."
                )
            return func(message, *args, **kwargs)
        
        # Проверяем, является ли пользователь администратором
        if not is_admin(user_id):
            bot.send_message(
                message.chat.id,
                "У вас нет доступа к этому боту. Обратитесь к администратору."
            )
            logger.warning(f"Попытка несанкционированного доступа от пользователя {user_id}")
            return
        
        return func(message, *args, **kwargs)
    
    return wrapper

@bot.message_handler(commands=['start'])
@admin_required
def handle_start(message):
    bot.send_message(
        message.chat.id,
        "Привет! Я бот для отслеживания обновлений сериалов на RuTracker.\n"
        "Отправьте мне ссылку на страницу раздачи, чтобы начать отслеживание.\n"
        "Используйте /help для получения списка доступных команд."
    )
    user_states[message.from_user.id] = State.IDLE
    logger.info(f"Пользователь {message.from_user.id} запустил бота")

@bot.message_handler(commands=['help'])
@admin_required
def handle_help(message):
    help_text = (
        "Список доступных команд:\n"
        "/start - Начать работу с ботом\n"
        "/help - Показать это сообщение\n"
        "/list - Показать список отслеживаемых сериалов\n"
        "/force_dl - Принудительно загрузить все торренты\n"
        "/force_cl - Очистить категорию 'from telegram' в qBittorrent\n"
        "/add - Добавить сериал для отслеживания\n"
        "/users - Просмотр списка пользователей\n" 
        "/adduser - Добавить пользователя\n"
        "/deluser - Удалить пользователя\n"
        "/addadmin - Сделать пользователя администратором\n"
        "/status - Проверить статус подключения\n"
        "/force_chk - Принудительно проверить обновления для всех ссылок\n"
    )
    bot.send_message(message.chat.id, help_text)
    logger.info(f"Пользователь {message.from_user.id} запросил справку")

@bot.message_handler(commands=['list'])
@admin_required
def handle_list(message):
    series_list = get_all_series()
    if not series_list:
        bot.send_message(message.chat.id, "Нет отслеживаемых сериалов.")
        logger.info(f"Пользователь {message.from_user.id} запросил список сериалов (пусто)")
        return

    markup = InlineKeyboardMarkup()
    for series in series_list:
        series_id, url, title, created, edited, last_updated, added_by, added_at = series
        button_text = f"{title} (Обновлено: {last_updated})"
        markup.add(InlineKeyboardButton(button_text, callback_data=f"series_{series_id}"))

    bot.send_message(message.chat.id, "Список отслеживаемых сериалов:", reply_markup=markup)
    logger.info(f"Пользователь {message.from_user.id} запросил список сериалов")

@bot.callback_query_handler(func=lambda call: call.data.startswith('series_'))
@admin_required
def handle_series_callback(call):
    series_id = int(call.data.split('_')[1])
    series = get_series(series_id=series_id)
    if not series:
        bot.send_message(call.message.chat.id, "Сериал не найден.")
        return
    
    series_id, url, title, created, edited, last_updated, added_by, added_at = series
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔄 Обновить", callback_data=f"update_{series_id}"))
    markup.add(InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_{series_id}"))
    markup.add(InlineKeyboardButton("🔗 Ссылка", url=url))
    markup.add(InlineKeyboardButton("⬅️ Назад", callback_data="back_to_list"))
    
    bot.edit_message_text(
        f"Серия: {title}\n"
        f"Создана: {created}\n"
        f"Последнее редактирование: {edited}\n"
        f"Добавлена: {added_at}",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('delete_'))
@admin_required
def handle_delete_callback(call):
    series_id = int(call.data.split('_')[1])
    
    # Тег для идентификации торрента
    tag = f"id_{series_id}"
    
    # Удаляем сериал из БД
    if remove_series(series_id=series_id):
        # Удаляем торрент по тегу
        if qbittorrent.delete_torrent_by_tag(tag, delete_files=False):
            bot.answer_callback_query(call.id, "Сериал и соответствующий торрент удалены.")
        else:
            bot.answer_callback_query(call.id, "Сериал удален, но соответствующий торрент не найден.")
        
        # Возвращаемся к списку
        handle_list_callback(call)
    else:
        bot.answer_callback_query(call.id, "Не удалось удалить сериал.")

@bot.callback_query_handler(func=lambda call: call.data == 'back_to_list')
@admin_required
def handle_list_callback(call):
    series_list = get_all_series()
    if not series_list:
        bot.edit_message_text(
            "Нет отслеживаемых сериалов.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )
        return

    markup = InlineKeyboardMarkup()
    for series in series_list:
        series_id, url, title, created, edited, last_updated, added_by, added_at = series
        button_text = f"{title} (Обновлено: {last_updated})"
        markup.add(InlineKeyboardButton(button_text, callback_data=f"series_{series_id}"))

    bot.edit_message_text(
        "Список отслеживаемых сериалов:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup
    )

@bot.message_handler(commands=['status'])
@admin_required
def handle_status(message):
    # Проверяем подключение к RuTracker
    rutracker_status = "Успешно" if rutracker.check_connection() else "Ошибка"
    
    # Проверяем подключение к qBittorrent
    qbittorrent_status = "Успешно" if qbittorrent.connect() else "Ошибка"
    
    # Проверяем прокси
    proxy_status = "Настроен" if PROXY_URL else "Не настроен"
    
    # Формируем сообщение
    status_message = (
        f"Статус подключения:\n"
        f"RuTracker: {rutracker_status}\n"
        f"Прокси: {proxy_status}\n"
        f"qBittorrent: {qbittorrent_status}"
    )
    bot.send_message(message.chat.id, status_message)

@bot.message_handler(commands=['force_chk'])
@admin_required
def handle_force_chk(message):
    bot.send_message(message.chat.id, "Начинаю проверку всех ссылок на обновления...")
    
    series_list = get_all_series()
    if not series_list:
        bot.send_message(message.chat.id, "Нет отслеживаемых сериалов.")
        return
    
    for series in series_list:
        series_id, url, title, created, edited, last_updated, added_by, added_at = series
        
        # Получаем актуальную информацию о странице
        page_info = rutracker.get_page_info(url)
        if not page_info:
            bot.send_message(message.chat.id, f"Не удалось получить информацию о странице: {title}")
            continue
        
        # Проверяем, изменилось ли время редактирования
        if page_info["edited"] != edited:
            # Удаляем старую загрузку в qBittorrent
            tag = f"id_{series_id}"
            qbittorrent.delete_torrent_by_tag(tag, delete_files=False)
            
            # Обновляем информацию в базе данных
            update_series(series_id, title=page_info["title"], created=page_info["created"], edited=page_info["edited"], last_updated=page_info["edited"])
            
            # Скачиваем и добавляем новый торрент
            torrent_data = rutracker.download_torrent(page_info["topic_id"])
            if torrent_data and qbittorrent.add_torrent(torrent_data, page_info["title"], tags=tag):
                bot.send_message(message.chat.id, f"Сериал обновлен: {title}")
            else:
                bot.send_message(message.chat.id, f"Не удалось обновить сериал: {title}")
    bot.send_message(message.chat.id, "Проверка завершена.")
