import logging
from bot import bot
from database import init_db

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

def main():
    try:
        logger.info("Инициализация базы данных...")
        init_db()
        logger.info("База данных успешно инициализирована.")

        logger.info("Запуск Telegram-бота...")
        bot.polling(none_stop=True)
    except KeyboardInterrupt:
        logger.info("Остановка приложения (KeyboardInterrupt).")
    except Exception as e:
        logger.error(f"Ошибка при запуске приложения: {e}", exc_info=True)

if __name__ == "__main__":
    main()
