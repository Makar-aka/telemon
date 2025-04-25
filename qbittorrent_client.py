import logging
import qbittorrentapi
from config import QBITTORRENT_URL, QBITTORRENT_USERNAME, QBITTORRENT_PASSWORD, QBITTORRENT_SAVE_PATH

# Инициализация логгера
logger = logging.getLogger(__name__)

class QBittorrentClient:
    def __init__(self):
        self.url = QBITTORRENT_URL
        self.username = QBITTORRENT_USERNAME
        self.password = QBITTORRENT_PASSWORD
        self.save_path = QBITTORRENT_SAVE_PATH if 'QBITTORRENT_SAVE_PATH' in globals() else ""
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
        
        Args:
            torrent_data: Содержимое торрент-файла
            title: Название раздачи для логирования
            tags: Теги для торрента (для легкой идентификации)
        
        Returns:
            bool: True в случае успеха, False в случае ошибки
        """
        try:
            if self.client is None:
                if not self.connect():
                    return False
            
            # Параметры для добавления торрента
            options = {
                'category': 'from telegram',
                'tags': tags
            }
            
            # Добавляем путь сохранения, если он указан
            if hasattr(self, 'save_path') and self.save_path:
                options['savepath'] = self.save_path
            
            # Добавляем торрент с указанными опциями
            self.client.torrents_add(
                torrent_files=torrent_data,
                **options
            )
            logger.info(f"Торрент '{title}' добавлен в qBittorrent с тегами: {tags}")
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
            torrents = self.client.torrents_info(category="from telegram")
            if not torrents:
                logger.info("Категория 'from telegram' пуста")
                return True
            
            # Удаляем все торренты из категории
            for torrent in torrents:
                self.client.torrents_delete(delete_files=False, hashes=torrent.hash)
            
            logger.info("Категория 'from telegram' очищена")
            return True
        except Exception as e:
            logger.error(f"Ошибка очистки категории: {e}")
            return False

    def delete_torrent_by_tag(self, tag, delete_files=False):
        """
        Удаляет все торренты с указанным тегом.
    
        Args:
            tag: Тег для поиска торрентов
            delete_files: Удалять ли файлы вместе с торрентом
    
        Returns:
            bool: True если хотя бы один торрент был удален, False в противном случае
        """
        try:
            if self.client is None:
                if not self.connect():
                    return False
        
            # Получаем список торрентов с указанным тегом
            torrents = self.client.torrents_info(tag=tag)
            if not torrents:
                logger.info(f"Торренты с тегом '{tag}' не найдены")
                return False
        
            # Удаляем торренты
            for torrent in torrents:
                logger.info(f"Удаляю торрент: {torrent.name}")
                self.client.torrents_delete(delete_files=delete_files, hashes=torrent.hash)
        
            logger.info(f"Торрент(ы) с тегом '{tag}' успешно удалены")
            return True
        except Exception as e:
            logger.error(f"Ошибка удаления торрентов по тегу: {e}")
            return False

