import logging
from telebot import TeleBot
from telebot.types import Message
from config import TELEGRAM_TOKEN, ALLOWED_USERS
from database import add_torrent, get_all_torrents
from rutracker import RuTracker
from qbittorrent import QBittorrent

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

bot = TeleBot(TELEGRAM_TOKEN)
rutracker = RuTracker()
qbittorrent = QBittorrent()

# Список администраторов
ADMINS = set()

# Декоратор для проверки администратора
def admin_required(func):
    def wrapper(message: Message, *args, **kwargs):
        if message.from_user.id not in ADMINS:
            bot.send_message(message.chat.id, "Эта команда доступна только администраторам.")
            logger.warning(f"Пользователь {message.from_user.id} попытался выполнить административную команду.")
            return
        return func(message, *args, **kwargs)
    return wrapper

@bot.message_handler(commands=["start"])
def handle_start(message: Message):
    bot.send_message(message.chat.id, "Привет! Я бот для отслеживания раздач.")
    logger.info(f"Пользователь {message.from_user.id} начал работу с ботом (/start).")

@bot.message_handler(commands=["add"])
def handle_add(message: Message):
    """Добавить страницу для отслеживания."""
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        url = args[1]
        # Логика добавления страницы
        bot.send_message(message.chat.id, f"Страница {url} добавлена для отслеживания.")
        logger.info(f"Пользователь {message.from_user.id} добавил страницу {url}.")
    else:
        bot.send_message(message.chat.id, "Отправьте ссылку на страницу для добавления.")
        logger.info(f"Пользователь {message.from_user.id} начал диалог для добавления страницы.")

@bot.message_handler(commands=["list"])
def handle_list(message: Message):
    torrents = get_all_torrents()
    if not torrents:
        bot.send_message(message.chat.id, "Нет отслеживаемых страниц.")
        logger.info(f"Пользователь {message.from_user.id} запросил список страниц, но список пуст.")
    else:
        response = "\n".join([f"{t[2]} ({t[1]})" for t in torrents])
        bot.send_message(message.chat.id, response)
        logger.info(f"Пользователь {message.from_user.id} запросил список страниц. Отправлено {len(torrents)} страниц.")

@bot.message_handler(commands=["update"])
def handle_update(message: Message):
    """Обновить страницу."""
    bot.send_message(message.chat.id, "Обновление страницы...")
    logger.info(f"Пользователь {message.from_user.id} запросил обновление страницы (/update).")
    # Логика обновления страницы

@bot.message_handler(commands=["check"])
def handle_check(message: Message):
    """Проверить страницы сейчас."""
    bot.send_message(message.chat.id, "Проверка всех страниц...")
    logger.info(f"Пользователь {message.from_user.id} запросил проверку страниц (/check).")
    # Логика проверки страниц

@bot.message_handler(commands=["help"])
def handle_help(message: Message):
    """Обработчик команды /help."""
    help_text = (
        "Список доступных команд:\n"
        "/start - Начать работу с ботом\n"
        "/help - Показать это сообщение\n"
        "/add <url> - Добавить страницу с аргументом\n"
        "/add - Начать диалог для добавления страницы\n"
        "/list - Показать отслеживаемые страницы\n"
        "/update - Обновить страницу\n"
        "/check - Проверить страницы сейчас\n"
        "/subscribe - Подписаться на обновления\n"
        "/status - Показать статус подписки\n"
        "/users - Список всех пользователей (административная команда)\n"
        "/makeadmin - Сделать пользователя администратором (административная команда)\n"
        "/removeadmin - Удалить пользователя из администраторов (административная команда)\n"
        "/adduser - Добавить пользователя (административная команда)\n"
        "/userdel - Удалить пользователя (административная команда)\n"
        "/force - Принудительно обновить страницу (административная команда)\n"
        "/clean - Очистка директории с файлами (административная команда)"
    )
    bot.send_message(message.chat.id, help_text)
    logger.info(f"Пользователь {message.from_user.id} запросил справку (/help).")

@bot.message_handler(commands=["subscribe"])
def handle_subscribe(message: Message):
    """Подписаться на обновления."""
    bot.send_message(message.chat.id, "Вы подписались на обновления.")
    logger.info(f"Пользователь {message.from_user.id} подписался на обновления (/subscribe).")

@bot.message_handler(commands=["status"])
def handle_status(message: Message):
    """Показать статус подписки."""
    bot.send_message(message.chat.id, "Ваш статус подписки: Активен.")
    logger.info(f"Пользователь {message.from_user.id} запросил статус подписки (/status).")

@bot.message_handler(commands=["users"])
@admin_required
def handle_users(message: Message):
    """Список всех пользователей (административная команда)."""
    bot.send_message(message.chat.id, "Список всех пользователей: ...")
    logger.info(f"Администратор {message.from_user.id} запросил список пользователей (/users).")

@bot.message_handler(commands=["makeadmin"])
@admin_required
def handle_makeadmin(message: Message):
    """Сделать пользователя администратором."""
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        user_id = int(args[1])
        ADMINS.add(user_id)
        bot.send_message(message.chat.id, f"Пользователь {user_id} добавлен в администраторы.")
        logger.info(f"Администратор {message.from_user.id} добавил пользователя {user_id} в администраторы.")
    else:
        bot.send_message(message.chat.id, "Укажите ID пользователя для добавления в администраторы.")

@bot.message_handler(commands=["removeadmin"])
@admin_required
def handle_removeadmin(message: Message):
    """Удалить пользователя из администраторов."""
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        user_id = int(args[1])
        ADMINS.discard(user_id)
        bot.send_message(message.chat.id, f"Пользователь {user_id} удалён из администраторов.")
        logger.info(f"Администратор {message.from_user.id} удалил пользователя {user_id} из администраторов.")
    else:
        bot.send_message(message.chat.id, "Укажите ID пользователя для удаления из администраторов.")

@bot.message_handler(commands=["adduser"])
@admin_required
def handle_adduser(message: Message):
    """Добавить пользователя (административная команда)."""
    bot.send_message(message.chat.id, "Добавление пользователя...")
    logger.info(f"Администратор {message.from_user.id} запросил добавление пользователя (/adduser).")

@bot.message_handler(commands=["userdel"])
@admin_required
def handle_userdel(message: Message):
    """Удалить пользователя (административная команда)."""
    bot.send_message(message.chat.id, "Удаление пользователя...")
    logger.info(f"Администратор {message.from_user.id} запросил удаление пользователя (/userdel).")

@bot.message_handler(commands=["force"])
@admin_required
def handle_force(message: Message):
    """Принудительно обновить страницу."""
    bot.send_message(message.chat.id, "Принудительное обновление страницы...")
    logger.info(f"Администратор {message.from_user.id} запросил принудительное обновление страницы (/force).")

@bot.message_handler(commands=["clean"])
@admin_required
def handle_clean(message: Message):
    """Очистка директории с файлами."""
    bot.send_message(message.chat.id, "Очистка директории с файлами...")
    logger.info(f"Администратор {message.from_user.id} запросил очистку директории (/clean).")
