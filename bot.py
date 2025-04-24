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
