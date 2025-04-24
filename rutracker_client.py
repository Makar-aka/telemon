import logging
import re
import requests
import pytz
from bs4 import BeautifulSoup
from datetime import datetime
from config import RUTRACKER_USERNAME, RUTRACKER_PASSWORD, PROXY_URL, PROXY_USERNAME, PROXY_PASSWORD, TIMEZONE

logger = logging.getLogger(__name__)

class RutrackerClient:
    def __init__(self):
        self.username = RUTRACKER_USERNAME
        self.password = RUTRACKER_PASSWORD
        self.session = requests.Session()
        
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
            login_url = "https://rutracker.org/forum/login.php"
            payload = {
                "login_username": self.username,
                "login_password": self.password,
                "login": "Вход",
            }
            response = self.session.post(login_url, data=payload, proxies=self.proxies, timeout=20)
            response.raise_for_status()
            
            if "bb_session" in self.session.cookies:
                logger.info("Успешная авторизация на RuTracker")
                return True
            else:
                logger.error("Не удалось авторизоваться на RuTracker")
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

        response = self.session.get(url, proxies=self.proxies, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        # Получаем заголовок
        title_element = soup.select_one("h1.maintitle")
        if not title_element:
            logger.error(f"Не удалось найти заголовок раздачи на странице {url}")
            return None
        
        full_title = title_element.text.strip()
        
        # Берем только часть до первого символа "/"
        title = full_title.split('/')[0].strip() if '/' in full_title else full_title.strip()

        # Получаем время обновления страницы
        current_time = datetime.now(pytz.timezone(TIMEZONE)).strftime("%d.%m.%Y %H:%M")
        last_updated = current_time  # По умолчанию используем текущее время
        
        # Пытаемся найти время последнего обновления в основном посте
        update_info = soup.select_one("p.post-time")
        if update_info:
            last_updated = update_info.text.strip()
        
        return {
            "title": title,
            "last_updated": last_updated,
            "topic_id": topic_id
        }
    except Exception as e:
        logger.error(f"Ошибка получения информации о странице {url}: {e}")
        return None



    def download_torrent(self, topic_id):
        """Скачать торрент-файл."""
        try:
            if not self.is_logged_in:
                self.is_logged_in = self.login()
                if not self.is_logged_in:
                    logger.error("Не удалось авторизоваться для скачивания торрента")
                    return None

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

            logger.info(f"Торрент успешно скачан: {topic_id}")
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
