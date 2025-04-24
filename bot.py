from telebot import TeleBot
from telebot.types import Message
from config import TELEGRAM_TOKEN, ALLOWED_USERS
from database import add_torrent, get_all_torrents
from rutracker import RuTracker
from qbittorrent import QBittorrent

bot = TeleBot(TELEGRAM_TOKEN)
rutracker = RuTracker()
qbittorrent = QBittorrent()

@bot.message_handler(commands=["start"])
def handle_start(message: Message):
    bot.send_message(message.chat.id, "Привет! Я бот для отслеживания раздач.")

@bot.message_handler(commands=["list"])
def handle_list(message: Message):
    torrents = get_all_torrents()
    if not torrents:
        bot.send_message(message.chat.id, "Нет отслеживаемых раздач.")
    else:
        response = "\n".join([f"{t[2]} ({t[1]})" for t in torrents])
        bot.send_message(message.chat.id, response)

@bot.message_handler(commands=["help"])
def handle_help(message: Message):
    """Обработчик команды /help."""
    help_text = (
        "Список доступных команд:\n"
        "/start - Начать работу с ботом\n"
        "/help - Показать это сообщение\n"
        "/list - Показать отслеживаемые раздачи\n"
        "/clear - Очистить категорию 'from telegram' в qBittorrent\n"
        "/status - Проверить статус подключений\n\n"
        "Чтобы добавить раздачу для отслеживания, отправьте ссылку на неё."
    )
    bot.send_message(message.chat.id, help_text)
    logger.info(f"Пользователь {message.from_user.id} запросил справку (/help).")
