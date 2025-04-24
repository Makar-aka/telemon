import requests
from bs4 import BeautifulSoup
import logging
from config import RUTRACKER_USERNAME, RUTRACKER_PASSWORD, PROXY_URL, PROXY_USERNAME, PROXY_PASSWORD

logger = logging.getLogger(__name__)

class RuTracker:
    def __init__(self):
        self.session = requests.Session()
        self.proxies = {
            "http": f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_URL}",
            "https": f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_URL}",
        } if PROXY_URL else None

    def login(self) -> bool:
        """����������� �� RuTracker."""
        login_url = "https://rutracker.org/forum/login.php"
        payload = {
            "login_username": RUTRACKER_USERNAME,
            "login_password": RUTRACKER_PASSWORD,
            "login": "����",
        }
        try:
            response = self.session.post(login_url, data=payload, proxies=self.proxies, timeout=20)
            response.raise_for_status()
            if "bb_session" in self.session.cookies:
                logger.info("�������� ����������� �� RuTracker")
                return True
            else:
                logger.error("�� ������� �������������� �� RuTracker")
                return False
        except Exception as e:
            logger.error(f"������ ����������� �� RuTracker: {e}")
            return False

    def parse_page(self, url: str):
        """������� �������� �������."""
        try:
            response = self.session.get(url, proxies=self.proxies, timeout=20)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            title = soup.select_one("h1.maintitle").text.strip()
            last_updated = soup.select_one("p.post-time").text.strip()
            return {"title": title, "last_updated": last_updated}
        except Exception as e:
            logger.error(f"������ �������� �������� {url}: {e}")
            return None
