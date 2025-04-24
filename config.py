import os
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
PROXY_URL = os.getenv("PROXY_URL")
PROXY_USERNAME = os.getenv("PROXY_USERNAME")
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD")
QBITTORRENT_URL = os.getenv("QBITTORRENT_URL")
QBITTORRENT_USERNAME = os.getenv("QBITTORRENT_USERNAME")
QBITTORRENT_PASSWORD = os.getenv("QBITTORRENT_PASSWORD")
RUTRACKER_USERNAME = os.getenv("RUTRACKER_USERNAME")
RUTRACKER_PASSWORD = os.getenv("RUTRACKER_PASSWORD")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "3600"))
TIMEZONE = os.getenv("TIMEZONE", "Europe/Moscow")
# Проверка обязательных переменных
REQUIRED_VARS = [
    "TELEGRAM_TOKEN", "QBITTORRENT_URL", "RUTRACKER_USERNAME", "RUTRACKER_PASSWORD"
]

for var in REQUIRED_VARS:
    if not os.getenv(var):
        raise EnvironmentError(f"Переменная окружения {var} не задана.")
