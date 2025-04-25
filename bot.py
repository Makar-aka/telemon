import logging
from telebot import TeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import TELEGRAM_TOKEN
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

    logger.info(f"Список сериалов: {series_list}")  # Логируем данные из базы

    markup = InlineKeyboardMarkup()
    for series in series_list:
        # Учитываем все 8 значений, возвращаемых из базы
        series_id, url, title, created, edited, last_updated, added_by, added_at = series
        
        # Извлекаем текст до первого символа "/"
        title_part = title.split('/')[0].strip()
        
        # Используем поле `edited` для отображения времени последнего редактирования
        button_text = f"{title_part} - {edited}"
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
        
        # Извлекаем текст до первого символа "/"
        title_part = title.split('/')[0].strip()
        
        button_text = f"{title_part} - {edited}"
        markup.add(InlineKeyboardButton(button_text, callback_data=f"series_{series_id}"))

    bot.edit_message_text(
        "Список отслеживаемых сериалов:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup
    )

@bot.message_handler(func=lambda message: message.text and message.text.startswith('http'))
@admin_required
def handle_url(message):
    url = message.text.strip()
    
    # Проверяем, что это URL на RuTracker
    if not rutracker.get_topic_id(url):
        bot.send_message(
            message.chat.id,
            "Это не похоже на ссылку на раздачу RuTracker. Пожалуйста, проверьте ссылку."
        )
        return
    
    # Проверяем, не отслеживается ли уже этот сериал
    if series_exists(url):
        bot.send_message(
            message.chat.id,
            "Этот сериал уже отслеживается."
        )
        return
    
    # Получаем информацию о странице
    page_info = rutracker.get_page_info(url)
    if not page_info or not page_info.get("title") or not page_info.get("topic_id"):
        bot.send_message(
            message.chat.id,
            "Не удалось получить информацию о странице. Проверьте ссылку."
        )
        return
    
    # Добавляем сериал в базу данных
    series_id = add_series(
        url,
        page_info["title"],
        page_info["created"],
        page_info["edited"],
        page_info["last_updated"],
        message.from_user.id
    )
    if series_id:
        bot.send_message(
            message.chat.id,
            f"Сериал \"{page_info['title']}\" добавлен для отслеживания."
        )
        
        # Создаем тег в формате "id_XXX"
        tag = f"id_{series_id}"
        
        # Скачиваем и добавляем торрент
        torrent_data = rutracker.download_torrent(page_info["topic_id"])
        if torrent_data and qbittorrent.add_torrent(torrent_data, page_info["title"], tags=tag):
            bot.send_message(
                message.chat.id,
                "Торрент успешно добавлен в qBittorrent."
            )
        else:
            bot.send_message(
                message.chat.id,
                "Не удалось добавить торрент в qBittorrent."
            )
    else:
        bot.send_message(
            message.chat.id,
            "Не удалось добавить сериал в базу данных."
        )
    
    logger.info(f"Пользователь {message.from_user.id} добавил сериал: {url}")
