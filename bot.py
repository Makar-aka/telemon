import logging
from telebot import TeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import TELEGRAM_TOKEN
from database import get_all_series, update_series, add_series, remove_series
from rutracker_client import RutrackerClient
from qbittorrent_client import QBittorrentClient

logger = logging.getLogger(__name__)
bot = TeleBot(TELEGRAM_TOKEN)
rutracker = RutrackerClient()
qbittorrent = QBittorrentClient()

@bot.message_handler(commands=['start', 'help'])
def handle_start_help(message):
    bot.send_message(
        message.chat.id,
        "Привет! Я бот для отслеживания обновлений сериалов на RuTracker.\n"
        "Доступные команды:\n"
        "/list - Показать список сериалов\n"
        "/add - Добавить сериал\n"
        "/status - Проверить статус\n"
        "/force_chk - Принудительная проверка обновлений"
    )

@bot.message_handler(commands=['list'])
def handle_list(message):
    series_list = get_all_series()
    if not series_list:
        bot.send_message(message.chat.id, "Нет отслеживаемых сериалов.")
        return

    markup = InlineKeyboardMarkup()
    for series in series_list:
        series_id, url, title, _, _, last_updated, _, _ = series
        button_text = f"{title} (Обновлено: {last_updated})"
        markup.add(InlineKeyboardButton(button_text, callback_data=f"series_{series_id}"))

    bot.send_message(message.chat.id, "Список отслеживаемых сериалов:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('series_'))
def handle_series_callback(call):
    series_id = int(call.data.split('_')[1])
    series = get_all_series(series_id=series_id)
    if not series:
        bot.send_message(call.message.chat.id, "Сериал не найден.")
        return

    series_id, url, title, _, _, last_updated, _, _ = series
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔄 Обновить", callback_data=f"update_{series_id}"))
    markup.add(InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_{series_id}"))
    bot.edit_message_text(
        f"Сериал: {title}\nПоследнее обновление: {last_updated}",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('update_'))
def handle_update_callback(call):
    series_id = int(call.data.split('_')[1])
    series = get_all_series(series_id=series_id)
    if not series:
        bot.answer_callback_query(call.id, "Сериал не найден.")
        return

    _, url, title, _, _, last_updated, _, _ = series
    page_info = rutracker.get_page_info(url)
    if not page_info:
        bot.answer_callback_query(call.id, "Не удалось получить информацию о странице.")
        return

    if page_info["time_text"] != last_updated:
        update_series(series_id, title=page_info["title"], last_updated=page_info["time_text"])
        bot.answer_callback_query(call.id, "Сериал обновлен.")
    else:
        bot.answer_callback_query(call.id, "Обновлений нет.")

@bot.message_handler(commands=['add'])
def handle_add(message):
    bot.send_message(message.chat.id, "Отправьте ссылку на раздачу для добавления.")
    # Логика добавления раздачи

@bot.message_handler(commands=['status'])
def handle_status(message):
    bot.send_message(message.chat.id, "Проверка статуса...")
    # Логика проверки статуса

@bot.message_handler(commands=['force_chk'])
def handle_force_chk(message):
    bot.send_message(message.chat.id, "Принудительная проверка обновлений...")
    # Логика принудительной проверки
