import logging
import qbittorrentapi
from config import QBITTORRENT_URL, QBITTORRENT_USERNAME, QBITTORRENT_PASSWORD, QBITTORRENT_SAVE_PATH

logger = logging.getLogger(__name__)

class QBittorrentClient:
    def __init__(self):
        self.url = QBITTORRENT_URL
        self.username = QBITTORRENT_USERNAME
        self.password = QBITTORRENT_PASSWORD
        self.save_path = QBITTORRENT_SAVE_PATH
        self.client = None
        self.connect()

    def connect(self):
        """Подключение к qBittorrent."""
        try:
            self.client = qbittorrentapi.Client(
                host=self.url,
                username=self.username,
                password=self.password
            )
            self.client.auth_log_in()
            version = self.client.app.version
            logger.info(f"Успешное подключение к qBittorrent. Версия: {version}")
            return True
        except Exception as e:
            logger.error(f"Ошибка подключения к qBittorrent: {e}")
            self.client = None
            return False

    def add_torrent(self, torrent_data, title="", tags=""):
        """
        Добавление торрента в qBittorrent.
        """
        try:
            if self.client is None:
                if not self.connect():
                    return False

            options = {}
            if tags:
                options['tags'] = tags
            if hasattr(self, 'save_path') and self.save_path:
                options['savepath'] = self.save_path

            self.client.torrents_add(
                torrent_files=torrent_data,
                **options
            )
            logger.info(f"Торрент '{title}' добавлен в qBittorrent с тегами: {tags}")
            return True
        except Exception as e:
            logger.error(f"Ошибка добавления торрента в qBittorrent: {e}")
            return False

    def delete_torrent_by_tag(self, tag, delete_files=False):
        """
        Удаляет все торренты с указанным тегом.
        """
        try:
            if self.client is None:
                if not self.connect():
                    return False

            torrents = self.client.torrents_info(tag=tag)
            if not torrents:
                logger.info(f"Торренты с тегом '{tag}' не найдены")
                return False

            for torrent in torrents:
                logger.info(f"Удаляю торрент: {torrent.name}")
                self.client.torrents_delete(delete_files=delete_files, hashes=torrent.hash)

            logger.info(f"Торрент(ы) с тегом '{tag}' успешно удалены")
            return True
        except Exception as e:
            logger.error(f"Ошибка удаления торрентов по тегу: {e}")
            return False

    def remove_tag_and_category_by_tag(self, tag):
        """
        Удаляет тег и категорию у всех торрентов с указанным тегом.
        """
        try:
            if self.client is None:
                if not self.connect():
                    return False

            torrents = self.client.torrents_info(tag=tag)
            if not torrents:
                logger.info(f"Торренты с тегом '{tag}' не найдены")
                return False

            success = True
            for torrent in torrents:
                try:
                    self.client.torrents.add_tags(torrent.hash, "")      # Удалить все теги
                    self.client.torrents.set_category(torrent.hash, "")  # Удалить категорию
                    logger.info(f"Сброшены тег и категория для торрента: {torrent.name}")
                except Exception as e:
                    logger.error(f"Ошибка при сбросе тега/категории для {torrent.name}: {e}")
                    success = False
            return success
        except Exception as e:
            logger.error(f"Ошибка при удалении тегов и категории по тегу: {e}")
            return False

    def clear_category(self, category='from telegram', delete_files=False):
        """
        Удаляет все торренты из указанной категории.
        """
        try:
            if self.client is None:
                if not self.connect():
                    return False

            torrents = self.client.torrents_info(category=category)
            if not torrents:
                logger.info(f"Торренты в категории '{category}' не найдены")
                return True  # Нет торрентов — значит, всё удалено

            for torrent in torrents:
                logger.info(f"Удаляю торрент: {torrent.name}")
                self.client.torrents_delete(delete_files=delete_files, hashes=torrent.hash)

            logger.info(f"Все торренты из категории '{category}' успешно удалены")
            return True
        except Exception as e:
            logger.error(f"Ошибка при удалении торрентов из категории '{category}': {e}")
            return False