import logging
import threading
import time
from bot import bot, rutracker_client, qbittorrent_client
from database import init_db, get_all_series, update_series
from config import CHECK_INTERVAL

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Флаг для остановки фоновых потоков
stop_event = threading.Event()

def check_series_updates():
    """Проверка обновлений сериалов."""
    while not stop_event.is_set():
        try:
            logger.info("Запуск проверки обновлений сериалов...")
            
            # Получаем все сериалы из базы данных
            series_list = get_all_series()
            if not series_list:
                logger.info("Нет сериалов для проверки")
                time.sleep(CHECK_INTERVAL)
                continue
            
            # Проверяем каждый сериал на обновления
            for series in series_list:
                series_id, url, title, last_updated, added_by, added_at = series
                
                # Получаем актуальную информацию о странице
                page_info = rutracker.get_page_info(url)
                if not page_info:
                    logger.error(f"Не удалось получить информацию о странице {url}")
                    continue
                
                # Проверяем, изменилось ли время обновления
                if page_info["last_updated"] != last_updated:
                    logger.info(f"Обнаружено обновление для {title}")
                    
                    # Обновляем информацию в базе данных
                    update_series(series_id, title=page_info["title"], last_updated=page_info["last_updated"])
                    
                    # Скачиваем и добавляем торрент
                    torrent_data = rutracker.download_torrent(page_info["topic_id"])
                    if torrent_data and qbittorrent.add_torrent(torrent_data, page_info["title"]):
                        logger.info(f"Торрент для {title} добавлен в qBittorrent")
                    else:
                        logger.error(f"Не удалось добавить торрент для {title}")
                
                # Делаем паузу между запросами, чтобы не перегружать сервер
                time.sleep(5)
            
            logger.info("Проверка обновлений завершена")
        except Exception as e:
            logger.error(f"Ошибка при проверке обновлений: {e}")
        
        # Ждем до следующей проверки
        time.sleep(CHECK_INTERVAL)

def main():
    """Основная функция."""
    try:
        # Инициализация базы данных
        init_db()
        logger.info("База данных инициализирована")
        
        # Запуск фонового потока для проверки обновлений
        update_thread = threading.Thread(target=check_series_updates)
        update_thread.daemon = True
        update_thread.start()
        logger.info("Фоновый поток для проверки обновлений запущен")
        
        # Запуск бота
        logger.info("Запуск бота...")
        bot.polling(none_stop=True, interval=0)
    except KeyboardInterrupt:
        logger.info("Получен сигнал на остановку")
        stop_event.set()
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        stop_event.set()

if __name__ == "__main__":
    main()
