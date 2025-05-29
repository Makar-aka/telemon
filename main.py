import logging
from logging.handlers import RotatingFileHandler
import os
import threading
import time
from bot import bot
from database import init_db, get_all_series, update_series
from rutracker_client import RutrackerClient
from qbittorrent_client import QBittorrentClient
from config import CHECK_INTERVAL

# --- Настройка логирования ---
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FILE = "bot.log"

formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=5, encoding='utf-8')
file_handler.setFormatter(formatter)
file_handler.setLevel(LOG_LEVEL)

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
console_handler.setLevel(LOG_LEVEL)

logging.basicConfig(level=LOG_LEVEL, handlers=[file_handler, console_handler])

logger = logging.getLogger(__name__)

# Флаг для остановки фоновых потоков
stop_event = threading.Event()

def check_series_updates(rutracker, qbittorrent):
    """Проверка обновлений сериалов."""
    while not stop_event.is_set():
        try:
            logger.info("Запуск проверки обновлений сериалов...")
            series_list = get_all_series()
            if not series_list:
                logger.info("Нет сериалов для проверки")
                time.sleep(CHECK_INTERVAL)
                continue

            for series in series_list:
                series_id, url, title, last_updated, added_by, added_at = series
                logger.info(f"Проверка сериала: {title}, последнее обновление: {last_updated}")

                if rutracker is None:
                    logger.error("RutrackerClient не инициализирован")
                    continue
                if qbittorrent is None:
                    logger.error("QBittorrentClient не инициализирован")
                    continue

                page_info = rutracker.get_page_info(url)
                if not page_info:
                    logger.error(f"Не удалось получить информацию о странице {url}")
                    continue

                if page_info["time_text"] != last_updated:
                    logger.info(f"Обнаружено обновление для {title}")
                    tag = f"id_{series_id}"
                    qbittorrent.delete_torrent_by_tag(tag, delete_files=False)
                    update_series(series_id, title=page_info["title"], last_updated=page_info["time_text"])
                    torrent_data = rutracker.download_torrent(page_info["topic_id"])
                    if torrent_data and qbittorrent.add_torrent(torrent_data, page_info["title"], tags=tag):
                        logger.info(f"Торрент для {title} добавлен в qBittorrent")
                    else:
                        logger.error(f"Не удалось добавить торрент для {title}")

                time.sleep(5)

            logger.info("Проверка обновлений завершена")
        except Exception as e:
            logger.error(f"Ошибка при проверке обновлений: {e}")
            time.sleep(30)  # Задержка при ошибке
        time.sleep(CHECK_INTERVAL)

def main():
    """Основная функция."""
    while True:
        try:
            init_db()
            logger.info("База данных инициализирована")

            try:
                rutracker = RutrackerClient()
            except Exception as e:
                logger.error(f"Ошибка инициализации RutrackerClient: {e}")
                rutracker = None

            try:
                qbittorrent = QBittorrentClient()
            except Exception as e:
                logger.error(f"Ошибка инициализации QBittorrentClient: {e}")
                qbittorrent = None

            if rutracker is None or qbittorrent is None:
                logger.error("Один из клиентов не инициализирован. Бот будет работать только с доступными функциями.")

            update_thread = threading.Thread(target=check_series_updates, args=(rutracker, qbittorrent), daemon=True)
            update_thread.start()
            logger.info("Фоновый поток для проверки обновлений запущен")

            logger.info("Запуск бота...")
            bot.polling(none_stop=True, interval=0)
        except KeyboardInterrupt:
            logger.info("Получен сигнал на остановку")
            stop_event.set()
            break
        except Exception as e:
            logger.error(f"Ошибка в главном цикле: {e}")
            time.sleep(30)  # Задержка перед повторным запуском

if __name__ == "__main__":
    main()