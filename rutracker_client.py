import logging
import re
import requests
from bs4 import BeautifulSoup
from config import RUTRACKER_USERNAME, RUTRACKER_PASSWORD, PROXY_URL, PROXY_USERNAME, PROXY_PASSWORD

logger = logging.getLogger(__name__)

def get_proxy_dict():
    """Формирует словарь прокси для requests на основе переменных окружения."""
    if PROXY_URL:
        if PROXY_USERNAME and PROXY_PASSWORD:
            # Вставляем логин и пароль в url
            from urllib.parse import urlparse, urlunparse
            parsed = list(urlparse(PROXY_URL))
            parsed[1] = f"{PROXY_USERNAME}:{PROXY_PASSWORD}@{parsed[1]}"
            proxy_url = urlunparse(parsed)
        else:
            proxy_url = PROXY_URL
        return {
            "http": proxy_url,
            "https": proxy_url,
        }
    return {}

class RutrackerClient:
    def __init__(self):
        self.username = RUTRACKER_USERNAME
        self.password = RUTRACKER_PASSWORD
        self.session = requests.Session()
        self.proxies = get_proxy_dict()
        self.is_logged_in = self.login()

    def login(self):
        """Авторизация на RuTracker."""
        try:
            response = self.session.post(
                "https://rutracker.org/forum/login.php",
                data={"login_username": self.username, "login_password": self.password, "login": "Вход"},
                proxies=self.proxies if self.proxies else None,
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

            response = self.session.get(url, proxies=self.proxies if self.proxies else None, timeout=20)
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

            response = self.session.get(
                f"https://rutracker.org/forum/dl.php?t={topic_id}",
                proxies=self.proxies if self.proxies else None,
                timeout=30
            )
            response.raise_for_status()
            if "html" in response.headers.get("content-type", "").lower():
                logger.error("Получен HTML вместо торрент-файла")
                return None
            logger.info(f"Торрент успешно скачан: {topic_id}")
            return response.content
        except Exception as e:
            logger.error(f"Ошибка скачивания торрента {topic_id}: {e}")
            return None