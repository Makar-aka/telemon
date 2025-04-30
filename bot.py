import logging
from telebot import TeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import TELEGRAM_TOKEN, ADMIN_ID
from database import get_all_series, update_series, add_series, remove_series, get_all_users, add_user, remove_user, make_admin, series_exists, is_user_allowed, has_admins
from rutracker_client import RutrackerClient
from qbittorrent_client import QBittorrentClient
from functools import wraps

logger = logging.getLogger(__name__)
bot = TeleBot(TELEGRAM_TOKEN)
rutracker = RutrackerClient()
qbittorrent = QBittorrentClient()

# Словарь для хранения состояний пользователей
user_states = {}

# Состояния
class State:
    IDLE = 0
    WAITING_FOR_URL = 1
    WAITING_FOR_USER_ID = 2
    WAITING_FOR_ADMIN_ID = 3
    WAITING_FOR_USER_ID_TO_DELETE = 4
    WAITING_FOR_SERIES_ID = 5

# Декоратор для проверки доступа пользователя
def user_access_required(func):
    @wraps(func)
    def wrapper(message, *args, **kwargs):
        user_id = message.from_user.id
        
        # Если пользователь - главный администратор из .env
        if user_id == ADMIN_ID:
            # Если это первый запуск и нет администратора в базе
            if not has_admins():
                add_user(ADMIN_ID, message.from_user.username or str(ADMIN_ID), is_admin=True)
                bot.send_message(
                    message.chat.id,
                    "Вы добавлены как главный администратор."
                )
            return func(message, *args, **kwargs)
        
        # Проверяем, есть ли пользователь в базе данных
        if is_user_allowed(user_id):
            return func(message, *args, **kwargs)
        else:
            bot.send_message(
                message.chat.id,
                "У вас нет доступа к этому боту. Обратитесь к администратору для получения доступа."
            )
            logger.warning(f"Попытка несанкционированного доступа от пользователя {user_id}")
            return None
    return wrapper

# Декоратор для проверки прав администратора
def admin_required(func):
    @wraps(func)
    def wrapper(message, *args, **kwargs):
        user_id = message.from_user.id
        
        # Если пользователь - главный администратор из .env
        if user_id == ADMIN_ID:
            return func(message, *args, **kwargs)
        
        # Проверяем, является ли пользователь администратором в базе данных
        if is_user_allowed(user_id, admin_required=True):
            return func(message, *args, **kwargs)
        else:
            bot.send_message(
                message.chat.id,
                "У вас нет прав администратора для выполнения этой команды."
            )
            logger.warning(f"Попытка выполнения административной команды пользователем {user_id}")
            return None
    return wrapper

@bot.message_handler(commands=['start', 'help'])
@user_access_required
def handle_start_help(message):
    bot.send_message(
        message.chat.id,
        "Привет! Я бот для отслеживания обновлений сериалов на RuTracker.\n"
        "Доступные команды:\n"
        "/list - Показать список отслеживаемых сериалов\n"
        "/add - Добавить сериал для отслеживания\n"
        "/del - Удалить сериал\n"
        "/status - Проверить статус подключения\n"
        "/force_chk - Принудительная проверка обновлений\n"
        "/force_del - Удалить все торренты из qBittorrent\n"
        "/users - Просмотр списка пользователей\n" 
        "/adduser - Добавить пользователя\n"
        "/deluser - Удалить пользователя\n"
        "/addadmin - Сделать пользователя администратором"
    )
    user_states[message.from_user.id] = State.IDLE

# Обработчик для всех сообщений с ссылками
@bot.message_handler(func=lambda message: message.text and 
                     (message.text.startswith('http://') or message.text.startswith('https://')) and
                     'rutracker.org' in message.text.lower())
@user_access_required
def handle_all_links(message):
    url = message.text.strip()
    user_id = message.from_user.id
    
    # Проверяем корректность URL
    topic_id = rutracker.get_topic_id(url)
    if not topic_id:
        bot.send_message(
            message.chat.id,
            "Это не похоже на ссылку на раздачу RuTracker. Пожалуйста, проверьте URL."
        )
        return
    
    # Проверяем, не отслеживается ли уже этот сериал
    if series_exists(url):
        bot.send_message(message.chat.id, "Этот сериал уже отслеживается.")
        return
    
    # Получаем информацию о странице
    page_info = rutracker.get_page_info(url)
    if not page_info:
        bot.send_message(message.chat.id, "Не удалось получить информацию о странице. Проверьте ссылку.")
        return
    
    # Добавляем сериал в базу данных
    series_id = add_series(url, page_info["title"], page_info["time_text"], user_id)
    if series_id:
        bot.send_message(message.chat.id, f"Сериал \"{page_info['title']}\" добавлен для отслеживания.")
        
        # Скачиваем и добавляем торрент
        tag = f"id_{series_id}"
        torrent_data = rutracker.download_torrent(page_info["topic_id"])
        if torrent_data and qbittorrent.add_torrent(torrent_data, page_info["title"], tags=tag):
            bot.send_message(message.chat.id, "Торрент успешно добавлен в qBittorrent.")
        else:
            bot.send_message(message.chat.id, "Не удалось добавить торрент в qBittorrent.")
    else:
        bot.send_message(message.chat.id, "Не удалось добавить сериал в базу данных.")

@bot.message_handler(commands=['list'])
@user_access_required
def handle_list(message):
    series_list = get_all_series()
    if not series_list:
        bot.send_message(message.chat.id, "Нет отслеживаемых сериалов.")
        return

    markup = InlineKeyboardMarkup()
    for series in series_list:
        series_id, url, title, last_updated, added_by, added_at = series
        button_text = f"{title} (Обновлено: {last_updated})"
        markup.add(InlineKeyboardButton(button_text, callback_data=f"series_{series_id}"))

    bot.send_message(message.chat.id, "Список отслеживаемых сериалов:", reply_markup=markup)

@bot.message_handler(commands=['add'])
@user_access_required
def handle_add(message):
    bot.send_message(message.chat.id, "Отправьте ссылку на раздачу для добавления.")
    user_states[message.from_user.id] = State.WAITING_FOR_URL

@bot.message_handler(commands=['del'])
@user_access_required
def handle_del(message):
    bot.send_message(message.chat.id, "Отправьте ID сериала для удаления.")
    user_states[message.from_user.id] = State.WAITING_FOR_SERIES_ID

@bot.message_handler(commands=['status'])
@user_access_required
def handle_status(message):
    status_message = (
        f"Статус подключения:\n"
        f"RuTracker: {'Успешно' if rutracker.is_logged_in else 'Ошибка'}\n"
        f"qBittorrent: {'Успешно' if qbittorrent.client else 'Ошибка'}"
    )
    bot.send_message(message.chat.id, status_message)

@bot.message_handler(commands=['force_del'])
@admin_required
def handle_force_del(message):
    """Удаляет все торренты из категории 'from telegram' в qBittorrent."""
    bot.send_message(message.chat.id, "Удаление всех торрентов из категории 'from telegram'...")
    
    if qbittorrent.clear_category():
        bot.send_message(message.chat.id, "Все торренты успешно удалены из qBittorrent.")
    else:
        bot.send_message(message.chat.id, "Не удалось удалить торренты из qBittorrent.")

@bot.message_handler(commands=['force_chk'])
@admin_required
def handle_force_chk(message):
    bot.send_message(message.chat.id, "Начинаю проверку всех ссылок на обновления...")
    
    series_list = get_all_series()
    if not series_list:
        bot.send_message(message.chat.id, "Нет отслеживаемых сериалов.")
        return
    
    for series in series_list:
        series_id, url, title, last_updated, added_by, added_at = series
        
        # Получаем актуальную информацию о странице
        page_info = rutracker.get_page_info(url)
        if not page_info:
            bot.send_message(message.chat.id, f"Не удалось получить информацию о странице: {title}")
            continue
        
        # Проверяем, изменилось ли время редактирования
        if page_info["time_text"] != last_updated:
            # Удаляем старую загрузку в qBittorrent
            tag = f"id_{series_id}"
            qbittorrent.delete_torrent_by_tag(tag, delete_files=False)
            
            # Обновляем информацию в базе данных
            update_series(series_id, title=page_info["title"], last_updated=page_info["time_text"])
            
            # Скачиваем и добавляем новый торрент
            torrent_data = rutracker.download_torrent(page_info["topic_id"])
            if torrent_data and qbittorrent.add_torrent(torrent_data, page_info["title"], tags=tag):
                bot.send_message(message.chat.id, f"Сериал обновлен: {title}")
            else:
                bot.send_message(message.chat.id, f"Не удалось обновить сериал: {title}")
    bot.send_message(message.chat.id, "Проверка завершена.")

@bot.message_handler(commands=['users'])
@admin_required
def handle_users(message):
    users = get_all_users()
    if not users:
        bot.send_message(message.chat.id, "Нет зарегистрированных пользователей.")
        return

    user_list = "\n".join([f"{user[0]}: {user[1]} (Admin: {'Да' if user[2] else 'Нет'})" for user in users])
    bot.send_message(message.chat.id, f"Список пользователей:\n{user_list}")

@bot.message_handler(commands=['adduser'])
@admin_required
def handle_adduser(message):
    bot.send_message(message.chat.id, "Отправьте ID и имя пользователя для добавления в формате: ID Имя")
    user_states[message.from_user.id] = State.WAITING_FOR_USER_ID

@bot.message_handler(commands=['deluser'])
@admin_required
def handle_deluser(message):
    bot.send_message(message.chat.id, "Отправьте ID пользователя для удаления.")
    user_states[message.from_user.id] = State.WAITING_FOR_USER_ID_TO_DELETE

@bot.message_handler(commands=['addadmin'])
@admin_required
def handle_addadmin(message):
    bot.send_message(message.chat.id, "Отправьте ID пользователя для назначения администратором.")
    user_states[message.from_user.id] = State.WAITING_FOR_ADMIN_ID

@bot.callback_query_handler(func=lambda call: call.data.startswith('series_'))
@user_access_required
def handle_series_callback(call):
    series_id = int(call.data.split('_')[1])
    series = get_all_series(series_id=series_id)
    if not series:
        bot.send_message(call.message.chat.id, "Сериал не найден.")
        return

    series_id, url, title, last_updated, added_by, added_at = series
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔄 Обновить", callback_data=f"update_{series_id}"))
    markup.add(InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_{series_id}"))
    markup.add(InlineKeyboardButton("🔗 Ссылка", url=url))
    markup.add(InlineKeyboardButton("⬅️ Назад", callback_data="back_to_list"))
    
    bot.edit_message_text(
        f"Сериал: {title}\nПоследнее обновление: {last_updated}",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('update_'))
@user_access_required
def handle_update_callback(call):
    series_id = int(call.data.split('_')[1])
    series = get_all_series(series_id=series_id)
    if not series:
        bot.answer_callback_query(call.id, "Сериал не найден.")
        return

    _, url, title, last_updated, _, _ = series
    page_info = rutracker.get_page_info(url)
    if not page_info:
        bot.answer_callback_query(call.id, "Не удалось получить информацию о странице.")
        return

    if page_info["time_text"] != last_updated:
        tag = f"id_{series_id}"
        qbittorrent.delete_torrent_by_tag(tag, delete_files=False)
        update_series(series_id, title=page_info["title"], last_updated=page_info["time_text"])
        torrent_data = rutracker.download_torrent(page_info["topic_id"])
        if torrent_data and qbittorrent.add_torrent(torrent_data, page_info["title"], tags=tag):
            bot.answer_callback_query(call.id, "Сериал обновлен и торрент добавлен в qBittorrent.")
        else:
            bot.answer_callback_query(call.id, "Сериал обновлен, но не удалось добавить торрент.")
    else:
        bot.answer_callback_query(call.id, "Обновлений нет.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('delete_'))
@user_access_required
def handle_delete_callback(call):
    series_id = int(call.data.split('_')[1])
    
    # Удаляем сериал из базы данных
    if remove_series(series_id):
        # Удаляем торрент по тегу
        tag = f"id_{series_id}"
        if qbittorrent.delete_torrent_by_tag(tag, delete_files=False):
            bot.answer_callback_query(call.id, "Сериал и соответствующий торрент удалены.")
        else:
            bot.answer_callback_query(call.id, "Сериал удален, но соответствующий торрент не найден.")
        
        # Возвращаемся к списку
        handle_list_callback(call)
    else:
        bot.answer_callback_query(call.id, "Не удалось удалить сериал.")

@bot.callback_query_handler(func=lambda call: call.data == 'back_to_list')
@user_access_required
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
        series_id, url, title, last_updated, added_by, added_at = series
        button_text = f"{title} (Обновлено: {last_updated})"
        markup.add(InlineKeyboardButton(button_text, callback_data=f"series_{series_id}"))

    bot.edit_message_text(
        "Список отслеживаемых сериалов:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup
    )

@bot.message_handler(func=lambda message: message.from_user.id in user_states and user_states[message.from_user.id] == State.WAITING_FOR_URL)
@user_access_required
def handle_url(message):
    url = message.text.strip()
    user_id = message.from_user.id
    
    # Сбрасываем состояние
    user_states[user_id] = State.IDLE
    
    # Проверяем корректность URL
    topic_id = rutracker.get_topic_id(url)
    if not topic_id:
        bot.send_message(
            message.chat.id,
            "Это не похоже на ссылку на раздачу RuTracker. Пожалуйста, проверьте URL."
        )
        return
    
    # Проверяем, не отслеживается ли уже этот сериал
    if series_exists(url):
        bot.send_message(message.chat.id, "Этот сериал уже отслеживается.")
        return
    
    # Получаем информацию о странице
    page_info = rutracker.get_page_info(url)
    if not page_info:
        bot.send_message(message.chat.id, "Не удалось получить информацию о странице. Проверьте ссылку.")
        return
    
    # Добавляем сериал в базу данных
    series_id = add_series(url, page_info["title"], page_info["time_text"], user_id)
    if series_id:
        bot.send_message(message.chat.id, f"Сериал \"{page_info['title']}\" добавлен для отслеживания.")
        
        # Скачиваем и добавляем торрент
        tag = f"id_{series_id}"
        torrent_data = rutracker.download_torrent(page_info["topic_id"])
        if torrent_data and qbittorrent.add_torrent(torrent_data, page_info["title"], tags=tag):
            bot.send_message(message.chat.id, "Торрент успешно добавлен в qBittorrent.")
        else:
            bot.send_message(message.chat.id, "Не удалось добавить торрент в qBittorrent.")
    else:
        bot.send_message(message.chat.id, "Не удалось добавить сериал в базу данных.")

@bot.message_handler(func=lambda message: message.from_user.id in user_states and user_states[message.from_user.id] == State.WAITING_FOR_SERIES_ID)
@user_access_required
def process_series_id_to_delete(message):
    try:
        series_id = int(message.text.strip())
        
        # Сбрасываем состояние
        user_states[message.from_user.id] = State.IDLE
        
        # Удаляем сериал из базы данных и торрент из qBittorrent
        if remove_series(series_id):
            tag = f"id_{series_id}"
            if qbittorrent.delete_torrent_by_tag(tag, delete_files=False):
                bot.send_message(message.chat.id, "Сериал и соответствующий торрент удалены.")
            else:
                bot.send_message(message.chat.id, "Сериал удален, но соответствующий торрент не найден.")
        else:
            bot.send_message(message.chat.id, "Не удалось удалить сериал. Проверьте ID.")
    except ValueError:
        bot.send_message(message.chat.id, "ID должен быть числом.")

@bot.message_handler(func=lambda message: message.from_user.id in user_states and user_states[message.from_user.id] == State.WAITING_FOR_USER_ID)
@admin_required
def process_user_id(message):
    try:
        parts = message.text.split(' ', 1)
        if len(parts) != 2:
            bot.send_message(message.chat.id, "Неверный формат. Используйте: ID Имя")
            return
        
        user_id = int(parts[0])
        username = parts[1]
        
        # Сбрасываем состояние
        user_states[message.from_user.id] = State.IDLE
        
        if add_user(user_id, username):
            bot.send_message(message.chat.id, f"Пользователь {username} (ID: {user_id}) добавлен.")
        else:
            bot.send_message(message.chat.id, "Не удалось добавить пользователя.")
    except ValueError:
        bot.send_message(message.chat.id, "ID должен быть числом.")

@bot.message_handler(func=lambda message: message.from_user.id in user_states and user_states[message.from_user.id] == State.WAITING_FOR_USER_ID_TO_DELETE)
@admin_required
def process_user_id_to_delete(message):
    try:
        user_id = int(message.text.strip())
        
        # Сбрасываем состояние
        user_states[message.from_user.id] = State.IDLE
        
        if remove_user(user_id):
            bot.send_message(message.chat.id, f"Пользователь с ID {user_id} удален.")
        else:
            bot.send_message(message.chat.id, "Не удалось удалить пользователя. Проверьте ID.")
    except ValueError:
        bot.send_message(message.chat.id, "ID должен быть числом.")

@bot.message_handler(func=lambda message: message.from_user.id in user_states and user_states[message.from_user.id] == State.WAITING_FOR_ADMIN_ID)
@admin_required
def process_admin_id(message):
    try:
        user_id = int(message.text.strip())
        
        # Сбрасываем состояние
        user_states[message.from_user.id] = State.IDLE
        
        if make_admin(user_id):
            bot.send_message(message.chat.id, f"Пользователь с ID {user_id} назначен администратором.")
        else:
            bot.send_message(message.chat.id, "Не удалось назначить администратора. Проверьте ID.")
    except ValueError:
        bot.send_message(message.chat.id, "ID должен быть числом.")

# Обработчик для неизвестных команд
@bot.message_handler(func=lambda message: True)
def handle_unknown(message):
    if message.from_user.id == ADMIN_ID or is_user_allowed(message.from_user.id):
        bot.send_message(message.chat.id, "Неизвестная команда. Используйте /help для получения списка команд.")
