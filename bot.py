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
        series_id, url, title, last_updated, added_by, added_at = series
        
        # Извлекаем текст до первого символа "/"
        title_part = title.split('/')[0].strip()
        
        button_text = f"{title_part} - {last_updated}"
        markup.add(InlineKeyboardButton(button_text, callback_data=f"series_{series_id}"))

    bot.send_message(message.chat.id, "Список отслеживаемых сериалов:", reply_markup=markup)
    logger.info(f"Пользователь {message.from_user.id} запросил список сериалов")


@bot.message_handler(commands=['force_dl'])
@admin_required
def handle_force_dl(message):
    bot.send_message(message.chat.id, "Начинаю принудительную загрузку всех торрентов...")
    
    series_list = get_all_series()
    if not series_list:
        bot.send_message(message.chat.id, "Нет отслеживаемых сериалов.")
        return
    
    success_count = 0
    fail_count = 0
    
    for series in series_list:
        series_id, url, title, last_updated, added_by, added_at = series
        topic_id = rutracker.get_topic_id(url)
        if not topic_id:
            continue
        
        # Тег для идентификации торрента
        tag = f"id_{series_id}"
        
        # Удаляем старую загрузку
        qbittorrent.delete_torrent_by_tag(tag, delete_files=False)
        
        # Скачиваем и добавляем новый торрент
        torrent_data = rutracker.download_torrent(topic_id)
        if torrent_data and qbittorrent.add_torrent(torrent_data, title, tags=tag):
            success_count += 1
        else:
            fail_count += 1
    
    bot.send_message(
        message.chat.id, 
        f"Принудительная загрузка завершена. Успешно: {success_count}, С ошибками: {fail_count}"
    )

@bot.message_handler(commands=['force_cl'])
@admin_required
def handle_force_cl(message):
    if qbittorrent.clear_category():
        bot.send_message(message.chat.id, "Категория 'from telegram' очищена.")
    else:
        bot.send_message(
            message.chat.id,
            "Не удалось очистить категорию. Проверьте подключение к qBittorrent."
        )
    logger.info(f"Пользователь {message.from_user.id} запустил очистку категории")

@bot.message_handler(commands=['add'])
@admin_required
def handle_add(message):
    bot.send_message(
        message.chat.id,
        "Отправьте ссылку на страницу раздачи на RuTracker."
    )
    user_states[message.from_user.id] = State.WAITING_FOR_URL
    logger.info(f"Пользователь {message.from_user.id} начал добавление сериала")

@bot.message_handler(commands=['users'])
@admin_required
def handle_users(message):
    """Отображение списка всех пользователей."""
    users = get_all_users()
    if not users:
        bot.send_message(message.chat.id, "В базе данных нет зарегистрированных пользователей.")
        logger.info(f"Пользователь {message.from_user.id} запросил список пользователей, но список пуст.")
        return

    response = "Список пользователей:\n\n"
    for user_id, username, is_admin in users:
        status = "👑 Администратор" if is_admin else "👤 Пользователь"
        response += f"{status}: {username} (ID: {user_id})\n"

    bot.send_message(message.chat.id, response)
    logger.info(f"Пользователь {message.from_user.id} запросил список пользователей.")

@bot.message_handler(commands=['adduser'])
@admin_required
def handle_adduser(message):
    bot.send_message(
        message.chat.id,
        "Укажите ID пользователя для добавления."
    )
    user_states[message.from_user.id] = State.WAITING_FOR_USER_ID
    logger.info(f"Пользователь {message.from_user.id} начал добавление пользователя")

@bot.message_handler(commands=['deluser'])
@admin_required
def handle_deluser(message):
    bot.send_message(
        message.chat.id,
        "Укажите ID пользователя для удаления."
    )
    user_states[message.from_user.id] = State.WAITING_FOR_USER_ID_TO_DELETE
    logger.info(f"Пользователь {message.from_user.id} начал удаление пользователя")

@bot.message_handler(commands=['addadmin'])
@admin_required
def handle_addadmin(message):
    bot.send_message(
        message.chat.id,
        "Укажите ID пользователя для назначения администратором."
    )
    user_states[message.from_user.id] = State.WAITING_FOR_ADMIN_ID
    logger.info(f"Пользователь {message.from_user.id} начал назначение администратора")

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
    if not page_info:
        bot.send_message(
            message.chat.id,
            "Не удалось получить информацию о странице. Проверьте ссылку и доступ к RuTracker."
        )
        return
    
    # Добавляем сериал в базу данных
    series_id = add_series(url, page_info["title"], page_info["last_updated"], message.from_user.id)
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


@bot.message_handler(func=lambda message: True)
@admin_required
def handle_text(message):
    user_id = message.from_user.id
    state = user_states.get(user_id, State.IDLE)
    
    if state == State.WAITING_FOR_URL:
        bot.send_message(
            message.chat.id,
            "Это не похоже на URL. Пожалуйста, отправьте ссылку на раздачу."
        )
        user_states[user_id] = State.IDLE
    
    elif state == State.WAITING_FOR_USER_ID:
        try:
            new_user_id = int(message.text.strip())
            if add_user(new_user_id, f"User_{new_user_id}"):
                bot.send_message(
                    message.chat.id,
                    f"Пользователь с ID {new_user_id} добавлен."
                )
            else:
                bot.send_message(
                    message.chat.id,
                    "Не удалось добавить пользователя."
                )
        except ValueError:
            bot.send_message(
                message.chat.id,
                "Некорректный ID пользователя. Должно быть число."
            )
        user_states[user_id] = State.IDLE
    
    elif state == State.WAITING_FOR_USER_ID_TO_DELETE:
        try:
            user_id_to_delete = int(message.text.strip())
            if remove_user(user_id_to_delete):
                bot.send_message(
                    message.chat.id,
                    f"Пользователь с ID {user_id_to_delete} удалён."
                )
            else:
                bot.send_message(
                    message.chat.id,
                    "Не удалось удалить пользователя."
                )
        except ValueError:
            bot.send_message(
                message.chat.id,
                "Некорректный ID пользователя. Должно быть число."
            )
        user_states[user_id] = State.IDLE
    
    elif state == State.WAITING_FOR_ADMIN_ID:
        try:
            admin_user_id = int(message.text.strip())
            # Проверяем, существует ли пользователь
            user = get_user(admin_user_id)
            if not user:
                add_user(admin_user_id, f"Admin_{admin_user_id}", is_admin=True)
                bot.send_message(
                    message.chat.id,
                    f"Создан новый пользователь с ID {admin_user_id} и правами администратора."
                )
            elif make_admin(admin_user_id):
                bot.send_message(
                    message.chat.id,
                    f"Пользователь с ID {admin_user_id} теперь администратор."
                )
            else:
                bot.send_message(
                    message.chat.id,
                    "Не удалось назначить пользователя администратором."
                )
        except ValueError:
            bot.send_message(
                message.chat.id,
                "Некорректный ID пользователя. Должно быть число."
            )
        user_states[user_id] = State.IDLE
    
    else:
        bot.send_message(
            message.chat.id,
            "Я не понимаю эту команду. Используйте /help для получения списка команд."
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith('update_'))
@admin_required
def handle_update_callback(call):
    series_id = int(call.data.split('_')[1])
    series = get_series(series_id=series_id)
    if not series:
        bot.send_message(call.message.chat.id, "Сериал не найден.")
        return
    
    series_id, url, title, last_updated, added_by, added_at = series
    
    # Тег для идентификации торрента
    tag = f"id_{series_id}"
    
    # Получаем актуальную информацию о странице
    page_info = rutracker.get_page_info(url)
    if not page_info:
        bot.answer_callback_query(call.id, "Не удалось получить информацию о странице.")
        return
    
    # Удаляем старую загрузку в qBittorrent
    if not qbittorrent.delete_torrent_by_tag(tag, delete_files=False):
        bot.answer_callback_query(call.id, "Не удалось удалить старый торрент.")
        return
    
    # Скачиваем и добавляем новый торрент
    torrent_data = rutracker.download_torrent(page_info["topic_id"])
    if torrent_data and qbittorrent.add_torrent(torrent_data, page_info["title"], tags=tag):
        # Обновляем информацию в базе данных
        update_series(series_id, title=page_info["title"], last_updated=page_info["last_updated"])
        bot.answer_callback_query(call.id, "Сериал обновлен и торрент добавлен в qBittorrent.")
    else:
        bot.answer_callback_query(call.id, "Не удалось обновить сериал.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('update_'))
@admin_required
def handle_update_callback(call):
    series_id = int(call.data.split('_')[1])
    series = get_series(series_id=series_id)
    if not series:
        bot.send_message(call.message.chat.id, "Сериал не найден.")
        return
    
    series_id, url, title, last_updated, added_by, added_at = series
    
    # Тег для идентификации торрента
    tag = f"id_{series_id}"
    
    # Получаем актуальную информацию о странице
    page_info = rutracker.get_page_info(url)
    if not page_info:
        bot.answer_callback_query(call.id, "Не удалось получить информацию о странице.")
        return
    
    # Обновляем информацию в базе данных
    update_result = update_series(series_id, title=page_info["title"], last_updated=page_info["last_updated"])
    
    # Скачиваем и добавляем торрент
    torrent_data = rutracker.download_torrent(page_info["topic_id"])
    if torrent_data and qbittorrent.add_torrent(torrent_data, page_info["title"], tags=tag):
        bot.answer_callback_query(call.id, "Сериал обновлен и торрент добавлен в qBittorrent.")
    else:
        bot.answer_callback_query(call.id, "Сериал обновлен, но не удалось добавить торрент.")
    
    # Проверяем, изменилось ли что-то
    if update_result and (page_info["title"] != title or page_info["last_updated"] != last_updated):
        # Обновляем информацию в сообщении
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔄 Обновить", callback_data=f"update_{series_id}"))
        markup.add(InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_{series_id}"))
        markup.add(InlineKeyboardButton("🔗 Ссылка", url=url))
        markup.add(InlineKeyboardButton("⬅️ Назад", callback_data="back_to_list"))
        
        try:
            bot.edit_message_text(
                f"Серия: {page_info['title']}\n"
                f"Последнее обновление: {page_info['last_updated']}\n"
                f"Добавлена: {added_at}",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=markup
            )
        except Exception as e:
            logger.error(f"Ошибка при обновлении сообщения: {e}")
            # Если ошибка всё еще возникает, попробуем отправить новое сообщение вместо обновления
            bot.send_message(
                call.message.chat.id,
                f"Серия: {page_info['title']}\n"
                f"Последнее обновление: {page_info['last_updated']}\n"
                f"Добавлена: {added_at}",
                reply_markup=markup
            )
    else:
        # Если нет изменений, просто уведомляем
        bot.answer_callback_query(call.id, "Нет новых обновлений для этого сериала.")



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
        series_id, url, title, last_updated, added_by, added_at = series
        
        # Извлекаем текст до первого символа "/"
        title_part = title.split('/')[0].strip()
        
        button_text = f"{title_part} - {last_updated}"
        markup.add(InlineKeyboardButton(button_text, callback_data=f"series_{series_id}"))

    bot.edit_message_text(
        "Список отслеживаемых сериалов:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup
    )
