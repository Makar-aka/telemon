# ===== ФУНКЦИИ ДЛЯ РАБОТЫ С RUTRACKER =====

# Функция для получения ID темы из URL
def get_topic_id(url):
    match = re.search(r't=(\d+)', url)
    if match:
        return match.group(1)
    return None

# Функция для парсинга страницы раздачи
def parse_rutracker_page(url):
    try:
        # Если нет активной сессии, пытаемся переподключиться
        if "bb_session" not in rutracker_session.cookies:
            logger.warning("Сессия RuTracker не активна, попытка переподключения...")
            if not login_to_rutracker():
                logger.error("Не удалось переподключиться к RuTracker")
                return None
        
        response = rutracker_session.get(url, proxies=proxies, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        title = soup.select_one("h1.maintitle")
        if not title:
            logger.error(f"Не удалось найти заголовок раздачи на странице {url}")
            return None
        title = title.text.strip()
        
        update_info = soup.select_one("p.post-time")
        last_updated = update_info.text.strip() if update_info else "Неизвестно"
        
        topic_id = get_topic_id(url)
        if not topic_id:
            logger.error(f"Не удалось извлечь ID темы из URL {url}")
            return None
            
        dl_link = f"https://rutracker.org/forum/dl.php?t={topic_id}"
        
        return {"title": title, "last_updated": last_updated, "dl_link": dl_link}
    except Exception as e:
        logger.error(f"Ошибка парсинга страницы {url}: {str(e)}")
        return None

# Функция для скачивания торрент-файла
def download_torrent(url):
    try:
        # Если нет активной сессии, пытаемся переподключиться
        if "bb_session" not in rutracker_session.cookies:
            logger.warning("Сессия RuTracker не активна, попытка переподключения...")
            if not login_to_rutracker():
                logger.error("Не удалось переподключиться к RuTracker")
                return None
                
        logger.info(f"Скачивание торрента: {url}")
        response = rutracker_session.get(url, proxies=proxies, timeout=30)
        response.raise_for_status()
        
        # Проверка, что действительно получен торрент-файл, а не страница с ошибкой
        content_type = response.headers.get('content-type', '')
        if 'html' in content_type.lower():
            logger.error(f"Получен HTML вместо торрент-файла. Возможно, требуется авторизация.")
            # Повторная авторизация и попытка скачивания
            if login_to_rutracker():
                response = rutracker_session.get(url, proxies=proxies, timeout=30)
                response.raise_for_status()
                if 'html' not in response.headers.get('content-type', '').lower():
                    return response.content
            return None
            
        return response.content
    except requests.exceptions.ProxyError as e:
        logger.error(f"Ошибка прокси при скачивании торрента {url}: {str(e)}")
        
        # Пробуем скачать без прокси, если это возможно
        try:
            logger.info("Пробуем скачать без прокси...")
            response = rutracker_session.get(url, timeout=30, proxies=None)
            response.raise_for_status()
            return response.content
        except Exception as e2:
            logger.error(f"Ошибка скачивания торрента без прокси {url}: {str(e2)}")
            return None
    except Exception as e:
        logger.error(f"Ошибка скачивания торрента {url}: {str(e)}")
        return None

# ===== ФУНКЦИИ ДЛЯ РАБОТЫ С QBITTORRENT =====

# Функция для добавления торрента в qBittorrent
def add_torrent_to_qbittorrent(torrent_data):
    global qbt_client
    try:
        if qbt_client is None:
            logger.error("Клиент qBittorrent не инициализирован, попытка переподключения...")
            if not init_qbittorrent():
                logger.error("Не удалось переподключиться к qBittorrent")
                return False

        qbt_client.torrents_add(torrent_files=torrent_data, category="from telegram")
        logger.info("Торрент добавлен в qBittorrent")
        return True
    except Exception as e:
        logger.error(f"Ошибка добавления торрента в qBittorrent: {str(e)}")
        qbt_client = None  # Сбрасываем клиент, чтобы при следующем обращении была попытка переподключения
        return False

# Функция для очистки категории "from telegram" в qBittorrent
def clear_telegram_category():
    global qbt_client
    try:
        if qbt_client is None:
            logger.error("Клиент qBittorrent не инициализирован, попытка переподключения...")
            if not init_qbittorrent():
                logger.error("Не удалось переподключиться к qBittorrent")
                return False
            
        torrents = qbt_client.torrents_info(category="from telegram")
        for torrent in torrents:
            qbt_client.torrents_delete(delete_files=False, hashes=torrent.hash)
        logger.info("Категория 'from telegram' очищена")
        return True
    except Exception as e:
        logger.error(f"Ошибка очистки категории: {str(e)}")
        qbt_client = None  # Сбрасываем клиент, чтобы при следующем обращении была попытка переподключения
        return False

# ===== ФУНКЦИИ ДЛЯ ФОНОВОГО МОНИТОРИНГА =====

# Функция для проверки обновлений раздач
def check_updates():
    # Проверка подключения к RuTracker перед выполнением
    if "bb_session" not in rutracker_session.cookies:
        logger.warning("Нет подключения к RuTracker, пробуем переподключиться перед проверкой...")
        if not login_to_rutracker():
            logger.error("Не удалось подключиться к RuTracker, проверка обновлений пропущена")
            return
        
    logger.info("Проверка обновлений...")
    
    conn = sqlite3.connect("telemon.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, url, title, last_updated, added_by FROM torrents")
    torrents = cursor.fetchall()
    conn.close()

    for torrent_id, url, title, last_updated, user_id in torrents:
        page_data = parse_rutracker_page(url)
        if not page_data:
            continue

        if page_data["last_updated"] != last_updated:
            logger.info(f"Обнаружено обновление для {title}")
            
            # Обновляем информацию в базе
            conn = sqlite3.connect("telemon.db")
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE torrents SET last_updated = ?, title = ? WHERE id = ?",
                (page_data["last_updated"], page_data["title"], torrent_id),
            )
            conn.commit()
            conn.close()

            # Скачиваем и добавляем торрент
            if page_data["dl_link"]:
                torrent_data = download_torrent(page_data["dl_link"])
                if torrent_data and add_torrent_to_qbittorrent(torrent_data):
                    try:
                        bot.send_message(
                            user_id,
                            f"🔄 *Обновление раздачи!*\n\n"
                            f"Название: {page_data['title']}\n"
                            f"Новое время обновления: {page_data['last_updated']}\n"
                            f"Торрент добавлен в qBittorrent.",
                            parse_mode="Markdown"
                        )
                    except Exception as e:
                        logger.error(f"Ошибка отправки сообщения: {e}")
                else:
                    try:
                        bot.send_message(
                            user_id,
                            f"🔄 *Обновление раздачи*, но не удалось добавить торрент в qBittorrent!\n\n"
                            f"Название: {page_data['title']}\n"
                            f"Новое время обновления: {page_data['last_updated']}",
                            parse_mode="Markdown"
                        )
                    except Exception as e:
                        logger.error(f"Ошибка отправки сообщения: {e}")
            else:
                try:
                    bot.send_message(
                        user_id,
                        f"🔄 *Обновление раздачи*, но ссылка на торрент не найдена!\n\n"
                        f"Название: {page_data['title']}\n"
                        f"Новое время обновления: {page_data['last_updated']}",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.error(f"Ошибка отправки сообщения: {e}")
                    
        time.sleep(5)  # Пауза между проверками раздач
    
    logger.info("Проверка обновлений завершена")

# Функция для периодической проверки обновлений
def monitor_updates():
    while not stop_event.is_set():
        try:
            logger.info("Запуск проверки обновлений...")
            check_updates()
        except Exception as e:
            logger.error(f"Ошибка при проверке обновлений: {e}")
        
        # Ждём следующую проверку или сигнал остановки
        for _ in range(CHECK_INTERVAL):
            if stop_event.is_set():
                return
            time.sleep(1)

# Функция для периодической проверки подключений и переподключения
def reconnect_services():
    global qbt_client
    
    while not stop_event.is_set():
        try:
            reconnected = False
            
            # Проверяем подключение к RuTracker и переподключаемся при необходимости
            if should_reconnect("rutracker"):
                logger.info("Попытка переподключения к RuTracker...")
                if login_to_rutracker():
                    logger.info("Успешное переподключение к RuTracker")
                    reconnected = True
                else:
                    logger.warning("Не удалось переподключиться к RuTracker, следующая попытка через 5 минут")
            
            # Проверяем подключение к qBittorrent и переподключаемся при необходимости
            if should_reconnect("qbittorrent") and qbt_client is None:
                logger.info("Попытка переподключения к qBittorrent...")
                if init_qbittorrent():
                    logger.info("Успешное переподключение к qBittorrent")
                    reconnected = True
                else:
                    logger.warning("Не удалось переподключиться к qBittorrent, следующая попытка через 5 минут")
            
            # Если были успешные переподключения, обновляем статус
            if reconnected:
                results = {
                    "proxy": check_proxy_connection(),
                    "rutracker": "bb_session" in rutracker_session.cookies,
                    "qbittorrent": qbt_client is not None,
                }
                logger.info("===== Обновленный статус подключений =====")
                for service, status in results.items():
                    status_text = "✅ ПОДКЛЮЧЕНО" if status else "❌ ОШИБКА"
                    logger.info(f"{service.upper()}: {status_text}")
                logger.info("===================================")
        except Exception as e:
            logger.error(f"Ошибка при переподключении к сервисам: {e}")
        
        # Ждем следующую проверку или сигнал остановки
        for _ in range(60):  # Проверка каждую минуту на случай остановки потока
            if stop_event.is_set():
                break
            time.sleep(1)
