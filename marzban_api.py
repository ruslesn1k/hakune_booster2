import aiohttp
import asyncio
import time
import logging
from datetime import datetime, timedelta
from config import MARZBAN_URL, MARZBAN_USERNAME, MARZBAN_PASSWORD

# Храним текущий токен и время его истечения
_token: str | None = None
_token_expire: datetime | None = None

def _now_utc() -> datetime:
    return datetime.utcnow()

async def refresh_token() -> bool:
    """Запрашивает новый токен у Marzban."""
    global _token, _token_expire
    try:
        base = MARZBAN_URL.rstrip("/")
        async with aiohttp.ClientSession() as session:
            # ВАЖНО: используем data= (application/x-www-form-urlencoded), НЕ json=
            async with session.post(
                f"{base}/api/admin/token",
                data={
                    "username": MARZBAN_USERNAME,
                    "password": MARZBAN_PASSWORD,
                    # "grant_type": "password",  # обычно не требуется, но можно оставить
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                text = await resp.text()
                if resp.status == 200:
                    data = await resp.json()
                    _token = data.get("access_token")
                    # Если сервер вернул expires_in (секунды) — используем его; иначе час по умолчанию
                    expires_in = data.get("expires_in", 3600)
                    # Обновляем с небольшим запасом (минус 5 минут), чтобы не протух впритык
                    _token_expire = _now_utc() + timedelta(seconds=max(60, expires_in - 300))
                    logging.info("🔐 Получен новый токен Marzban")
                    return True
                logging.error(f"❌ Ошибка получения токена: {resp.status} {text}")
    except Exception as e:  # pragma: no cover - логирование ошибок сети
        logging.error(f"❌ Ошибка получения токена: {e}")
    return False

async def get_headers() -> dict:
    """Возвращает заголовки с актуальным токеном."""
    global _token, _token_expire
    # Обновлять токен заранее, если осталось <5 минут
    need_refresh = (
        not _token
        or not _token_expire
        or _now_utc() >= _token_expire
        or (_token_expire - _now_utc()) <= timedelta(minutes=5)
    )
    if need_refresh:
        ok = await refresh_token()
        if not ok:
            return {}
    return {"Authorization": f"Bearer {_token}"}

async def token_refresher():
    """Периодически обновляет токен — спит до момента, когда пора обновить."""
    while True:
        # Спим до момента, когда останется 5 минут до истечения
        if _token_expire:
            sleep_for = max(30, (_token_expire - _now_utc() - timedelta(minutes=5)).total_seconds())
        else:
            sleep_for = 60
        await asyncio.sleep(sleep_for)
        await refresh_token()

async def check_connection() -> bool:
    """Проверка подключения к Marzban API"""
    try:
        base = MARZBAN_URL.rstrip("/")
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{base}/api/admin",
                headers=await get_headers(),
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                text = await resp.text()
                if resp.status == 200:
                    data = await resp.json()
                    logging.info(f"✅ Подключение к Marzban API. Версия: {data.get('version')}")
                    return True
                logging.error(f"❌ Ошибка подключения: {resp.status} {text}")
                return False
    except Exception as e:  # pragma: no cover - только логирование
        logging.error(f"❌ Ошибка подключения к Marzban API: {e}")
        return False

async def api_request(method: str, endpoint: str, payload: dict | None = None):
    """Базовый запрос к API (JSON-эндпоинты)."""
    base = MARZBAN_URL.rstrip("/")
    url = f"{base}/api{endpoint}"
    async with aiohttp.ClientSession() as session:
        async with session.request(
            method,
            url,
            headers=await get_headers(),
            json=payload,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            text = await resp.text()
            if resp.status in (200, 201):
                # Может быть пустой ответ — тогда просто вернём текст
                try:
                    return await resp.json()
                except Exception:
                    return text
            logging.error(f"❌ Ошибка API [{method} {endpoint}]: {resp.status} {text}")
            return None

async def create_trial_user(nickname: str, sub_number: int):
    """
    Создание trial-пользователя на 14 дней в on_hold
    """
    username = f"{nickname}"
    payload = {
        "username": username,
        "status": "on_hold",
        "expire": 0,  # expire не нужен для trial
        "data_limit": 0,
        "data_limit_reset_strategy": "no_reset",
        "proxies": {
            "vless": {}
        },
        "inbounds": {
            "vless": ["Steal", "XTLS"]
        },
        "note": f"Trial подписка 14 дней для {nickname}",
        "on_hold_expire_duration": 14 * 24 * 60 * 60,  # 14 дней
        "on_hold_timeout": 3 * 24 * 60 * 60
    }
    return await api_request("POST", "/user", payload)

async def create_paid_user(nickname: str, payment_id: int, months: int):
    """
    Создание платного пользователя с отложенной активацией (on_hold).
    ВАЖНО:
    - не указывать 'expire' вместе с status='on_hold'
    - 'on_hold_expire_duration' = срок будущей подписки (в секундах)
    - 'on_hold_timeout' (сек) — сколько можно находиться в холде до автоудаления/очистки
    """
    now = int(time.time())
    username = f"paid_{nickname}_{payment_id}"

    # длительность будущей подписки после активации (в секундах)
    duration_sec = now + months * 30 * 24 * 60 * 60  # «месяц» = 30 дней, как у тебя

    payload = {
        "username": username,
        "status": "active",
        "expire": duration_sec,
        "data_limit": 0,
        "data_limit_reset_strategy": "no_reset",
        "proxies": {
            "vless": {}
        },
        "inbounds": {
            "vless": ["Steal", "XTLS"]
        },
        "note": f"Paid подписка {months} мес. для {nickname}",
        # это НЕ «длительность холда», а длительность будущей подписки после активации
        #"on_hold_expire_duration": int(duration_sec),
        # а это — сколько можно висеть в холде до очистки (например, 3 дня)
        #"on_hold_timeout": 3 * 24 * 60 * 60
    }

    return await api_request("POST", "/user", payload)

async def extend_user(username: str, months: int):
    """
    Продлить срок действия подписки для пользователя.
    Добавляем N месяцев к текущему expire.
    """
    # Получаем данные пользователя
    user_data = await api_request("GET", f"/user/{username}")
    if not user_data:
        return None

    current_expire = user_data.get("expire", 0)
    now_ts = int(time.time())

    # если подписка бессрочная или уже истекла — начинаем от текущего времени
    base_time = current_expire if current_expire > now_ts else now_ts

    # добавляем N месяцев (30 дней * N)
    new_expire = base_time + months * 30 * 24 * 60 * 60

    payload = {
        "expire": new_expire
    }

    return await api_request("PUT", f"/user/{username}", payload)

async def get_user_subscription_link(username: str):
    """
    Получить подписку (subscription link) пользователя
    """
    data = await api_request("GET", f"/user/{username}")
    if data and "subscription_url" in data:
        return data["subscription_url"]
    return None

async def get_user_subscriptions(user_id: int):
    """Возвращает список подписок юзера (trial + paid)."""
    # тут у тебя может быть схема генерации username = f"trial_{user_id}" / f"paid_{user_id}_N"
    data = []
    async with aiohttp.ClientSession() as session:
        async with session.get(
                f"{MARZBAN_URL}/api/users", headers=await get_headers()
        ) as resp:
            if resp.status == 200:
                all_users = await resp.json()
                for user in all_users:
                    if str(user_id) in user["username"]:
                        data.append(user)
    return data
