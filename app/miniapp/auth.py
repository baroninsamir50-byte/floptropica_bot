from __future__ import annotations
import hashlib, hmac, json, time
from dataclasses import dataclass
from urllib.parse import parse_qsl
from fastapi import Header, HTTPException
from app.config import get_settings

@dataclass(frozen=True)
class TelegramMiniAppUser:
    id: int
    first_name: str
    username: str | None
    language_code: str | None

def validate_init_data(init_data: str) -> TelegramMiniAppUser:
    if not init_data:
        raise HTTPException(status_code=401, detail="Telegram initData is missing")
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise HTTPException(status_code=401, detail="initData hash is missing")
    try:
        auth_date = int(parsed.get("auth_date", "0"))
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid auth_date") from exc
    settings = get_settings()
    if abs(int(time.time()) - auth_date) > settings.miniapp_auth_max_age:
        raise HTTPException(status_code=401, detail="initData has expired")
    check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    calculated = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, received_hash):
        raise HTTPException(status_code=401, detail="Invalid Telegram signature")
    try:
        user = json.loads(parsed["user"])
        return TelegramMiniAppUser(
            id=int(user["id"]),
            first_name=str(user.get("first_name", "")),
            username=user.get("username"),
            language_code=user.get("language_code"),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid user data") from exc

async def current_miniapp_user(
    x_telegram_init_data: str = Header(default=""),
) -> TelegramMiniAppUser:
    return validate_init_data(x_telegram_init_data)
