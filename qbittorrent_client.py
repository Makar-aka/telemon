import logging
from qbittorrent import Client
from config import QBITTORRENT_URL, QBITTORRENT_USERNAME, QBITTORRENT_PASSWORD

logger = logging.getLogger(__name__)

class QBittorrentClient:
    def __init__(self):
        self.url = QBITTORRENT_URL
        self.username = QBITTORRENT_USERNAME
        self.password = QBITTORRENT_PASSWORD
        self.client = None
        self.connect()

    def connect(self):
        """Подключение к qBittorrent."""
        try:
            self.client = Client(self.url)
            self.client.login(self.username, self.password)
            version = self.client.qbittorrent_version
            logger.info(f"Успешное подключение к qBittorrent. Версия: {version}")
            return True
        except Exception as e:
            logger.error(f"Ошибка подключения к qBittorrent: {e}")
            self.client = None
            return False

    def add_torrent(self, torrent_data, title=""):
        """Добавление торрента в qBittorrent."""
        try:
            if self.client is None:
                if not self.connect():
                    return False
            
            self.client.download_from_file(torrent_data, category="from telegram")
            logger.info(f"Торрент '{title}' добавлен в qBittorrent")
            return True
        except Exception as e:
            logger.error(f"Ошибка добавления торрента в qBittorrent: {e}")
            return False

    def clear_category(self):
        """Очистка категории 'from telegram'."""
        try:
            if self.client is None:
                if not self.connect():
                    return False
            
            # Получаем список торрентов в категории
            torrents = self.client.torrents(category="from telegram")
            if not torrents:
                logger.info("Категория 'from telegram' пуста")
                return True
            
            # Удаляем все торренты из категории
            for torrent in torrents:
                self.client.delete(torrent["hash"])
            
            logger.info("Категория 'from telegram' очищена")
            return True
        except Exception as e:
            logger.error(f"Ошибка очистки категории: {e}")
            return False

    def check_connection(self):
        """Проверка подключения к qBittorrent."""
        try:
            if self.client is None:
                return self.connect()
            version = self.client.qbittorrent_version
            logger.info(f"Подключение к qBittorrent активно. Версия: {version}")
            return True
        except Exception as e:
            logger.error(f"Ошибка проверки подключения к qBittorrent: {e}")
            return False
