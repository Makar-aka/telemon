import logging
import re
import requests
from bs4 import BeautifulSoup
from config import RUTRACKER_USERNAME, RUTRACKER_PASSWORD, PROXY_URL, PROXY_USERNAME, PROXY_PASSWORD

logger = logging.getLogger(__name__)

class RutrackerClient:
    def __init__(self):
        self.username = RUTRACKER_USERNAME
        self.password = RUTRACKER_PASSWORD
        self.session = requests.Session()
        self.proxies = {
            "http": f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_URL}",
            "https": f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_URL}",
        } if PROXY_URL else None
        self.is_logged_in = self.login()

    def login(self):
        """Авторизация на RuTracker."""
        try:
            response = self.session.post(
                "https://rutracker.org/forum/login.php",
                data={"login_username": self.username, "login_password": self.password, "login": "Вход"},
                proxies=self.proxies,
                timeout=20
            )
            response.raise_for_status()
            if "bb_session" in self.session.cookies:
                logger.info("Успешная авторизация на RuTracker")
                return True
            logger.error("Не удалось авторизоваться на RuTracker")
            return False
        except Exception as e:
            logger.error(f"Ошибка авторизации: {e}")
            return False

    def get_topic_id(self, url):
        """Получить ID темы из URL."""
        match = re.search(r't=(\d+)', url)
        return match.group(1) if match else None

    def get_page_info(self, url):
        """Получить информацию о странице раздачи."""
        try:
            if not self.is_logged_in and not self.login():
                return None

            topic_id = self.get_topic_id(url)
            if not topic_id:
                logger.error(f"Не удалось получить ID темы из URL: {url}")
                return None

            response = self.session.get(url, proxies=self.proxies, timeout=20)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            title = soup.select_one("h1.maintitle").text.strip()
            time_text = soup.select_one("p.post-time").text.strip() if soup.select_one("p.post-time") else "Неизвестно"

            logger.info(f"Заголовок: {title}, Время: {time_text}, ID темы: {topic_id}")
            return {"title": title, "time_text": time_text, "topic_id": topic_id}
        except Exception as e:
            logger.error(f"Ошибка получения информации о странице {url}: {e}")
            return None

    def download_torrent(self, topic_id):
        """Скачать торрент-файл."""
        try:
            if not self.is_logged_in and not self.login():
                return None

            response = self.session.get(f"https://rutracker.org/forum/dl.php?t={topic_id}", proxies=self.proxies, timeout=30)
            response.raise_for_status()
            if "html" in response.headers.get("content-type", "").lower():
                logger.error("Получен HTML вместо торрент-файла")
                return None
            logger.info(f"Торрент успешно скачан: {topic_id}")
            return response.content
        except Exception as e:
            logger.error(f"Ошибка скачивания торрента {topic_id}: {e}")
            return None
