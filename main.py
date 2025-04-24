import logging
from bot import bot
from database import init_db

# ��������� �����������
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

def main():
    try:
        logger.info("������������� ���� ������...")
        init_db()
        logger.info("���� ������ ������� ����������������.")

        logger.info("������ Telegram-����...")
        bot.polling(none_stop=True)
    except KeyboardInterrupt:
        logger.info("��������� ���������� (KeyboardInterrupt).")
    except Exception as e:
        logger.error(f"������ ��� ������� ����������: {e}", exc_info=True)

if __name__ == "__main__":
    main()
