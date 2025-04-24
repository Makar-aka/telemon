import logging
import re
import requests
from rutracker_api import RutrackerApi
from bs4 import BeautifulSoup
from datetime import datetime
from config import RUTRACKER_USERNAME, RUTRACKER_PASSWORD, PROXY_URL, PROXY_USERNAME, PROXY_PASSWORD

logger = logging.getLogger(__name__)

class RutrackerClient:
    def __init__(self):
        self.username = RUTRACKER_USERNAME
        self.password = RUTRACKER_PASSWORD
        self.session = requests.Session()
        self.api = RutrackerApi()
        
        # Настройка прокси для requests
        self.proxies = None
        if PROXY_URL:
            self.proxies = {
                "http": f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_URL}",
                "https": f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_URL}",
            }
            logger.info(f"Прокси настроен: {PROXY_URL}")
        
        # Попытка авторизации при инициализации
        self.is_logged_in = self.login()
    
    def login(self):
        """Авторизация на RuTracker."""
        try:
            self.api.login(self.username, self.password)
            logger.info("Успешная авторизация через API")
            
            # Дополнительная авторизация через requests для скачивания торрентов
            login_url = "https://rutracker.org/forum/login.php"
            payload = {
                "login_username": self.username,
                "login_password": self.password,
                "login": "Вход",
            }
            response = self.session.post(login_url, data=payload, proxies=self.proxies, timeout=20)
            response.raise_for_status()
            
            if "bb_session" in self.session.cookies:
                logger.info("Успешная авторизация через requests")
                return True
            else:
                logger.error("Не удалось авторизоваться через requests")
                return False
        except Exception as e:
            logger.error(f"Ошибка авторизации: {e}")
            return False

    def get_topic_id(self, url):
        """Получить ID темы из URL."""
        match = re.search(r't=(\d+)', url)
        if match:
            return match.group(1)
        return None

    def get_page_info(self, url):
        """Получить информацию о странице раздачи."""
        try:
            # Если нет активной сессии, пытаемся переподключиться
            if not self.is_logged_in:
                self.is_logged_in = self.login()
                if not self.is_logged_in:
                    logger.error("Не удалось авторизоваться для получения информации о странице")
                    return None

            topic_id = self.get_topic_id(url)
            if not topic_id:
                logger.error(f"Не удалось получить ID темы из URL: {url}")
                return None

            # Получение информации о теме через API
            topic = self.api.get_topic(topic_id)
            if not topic:
                logger.error(f"Не удалось получить информацию о теме через API: {topic_id}")
                # Попробуем получить через requests
                return self._get_page_info_via_requests(url, topic_id)

            return {
                "title": topic.title,
                "last_updated": topic.updated_at,
                "topic_id": topic_id
            }
        except Exception as e:
            logger.error(f"Ошибка получения информации о странице {url}: {e}")
            # Если API не сработал, пробуем через requests
            return self._get_page_info_via_requests(url, self.get_topic_id(url))

    def _get_page_info_via_requests(self, url, topic_id):
        """Запасной метод получения информации через requests."""
        try:
            response = self.session.get(url, proxies=self.proxies, timeout=20)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            title = soup.select_one("h1.maintitle")
            if not title:
                logger.error(f"Не удалось найти заголовок раздачи на странице {url}")
                return None
            title = title.text.strip()

            update_info = soup.select_one("p.post-time")
            last_updated = update_info.text.strip() if update_info else datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            return {
                "title": title,
                "last_updated": last_updated,
                "topic_id": topic_id
            }
        except Exception as e:
            logger.error(f"Ошибка получения информации через requests: {e}")
            return None

    def download_torrent(self, topic_id):
        """Скачать торрент-файл."""
        try:
            if not self.is_logged_in:
                self.is_logged_in = self.login()
                if not self.is_logged_in:
                    logger.error("Не удалось авторизоваться для скачивания торрента")
                    return None

            # Сначала пробуем через API
            try:
                torrent_content = self.api.download_torrent(topic_id)
                if torrent_content:
                    logger.info(f"Торрент успешно скачан через API: {topic_id}")
                    return torrent_content
            except Exception as e:
                logger.error(f"Не удалось скачать торрент через API: {e}")

            # Если API не сработал, пробуем через requests
            dl_url = f"https://rutracker.org/forum/dl.php?t={topic_id}"
            response = self.session.get(dl_url, proxies=self.proxies, timeout=30)
            response.raise_for_status()

            # Проверка, что действительно получен торрент-файл
            content_type = response.headers.get('content-type', '')
            if 'html' in content_type.lower():
                logger.error("Получен HTML вместо торрент-файла")
                # Повторная авторизация и попытка скачивания
                if self.login():
                    response = self.session.get(dl_url, proxies=self.proxies, timeout=30)
                    response.raise_for_status()
                    if 'html' not in response.headers.get('content-type', '').lower():
                        return response.content
                return None

            logger.info(f"Торрент успешно скачан через requests: {topic_id}")
            return response.content
        except Exception as e:
            logger.error(f"Ошибка скачивания торрента {topic_id}: {e}")
            return None

    def check_connection(self):
        """Проверить подключение к RuTracker."""
        try:
            response = self.session.get("https://rutracker.org", proxies=self.proxies, timeout=10)
            if response.status_code == 200:
                logger.info("Подключение к RuTracker успешно")
                return True
            else:
                logger.error(f"Не удалось подключиться к RuTracker. Код статуса: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Ошибка подключения к RuTracker: {e}")
            return False
