from qbittorrentapi import Client
import logging
from config import QBITTORRENT_URL, QBITTORRENT_USERNAME, QBITTORRENT_PASSWORD

logger = logging.getLogger(__name__)

class QBittorrent:
    def __init__(self):
        self.client = None

    def connect(self) -> bool:
        """Подключение к qBittorrent."""
        try:
            self.client = Client(
                host=QBITTORRENT_URL,
                username=QBITTORRENT_USERNAME,
                password=QBITTORRENT_PASSWORD,
            )
            self.client.auth_log_in()
            logger.info(f"Успешное подключение к qBittorrent. Версия: {self.client.app.version}")
            return True
        except Exception as e:
            logger.error(f"Ошибка подключения к qBittorrent: {e}")
            return False

    def add_torrent(self, torrent_data: bytes) -> bool:
        """Добавление торрента в qBittorrent."""
        try:
            self.client.torrents_add(torrent_files=torrent_data, category="from telegram")
            logger.info("Торрент добавлен в qBittorrent")
            return True
        except Exception as e:
            logger.error(f"Ошибка добавления торрента в qBittorrent: {e}")
            return False
