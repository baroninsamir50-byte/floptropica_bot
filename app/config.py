from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str
    database_url: str
    admin_ids: str = ""
    port: int = 10000
    timezone: str = "Europe/Amsterdam"
    house_attack_hour: int = 18
    house_attacks_enabled: bool = True
    cron_secret: str = ""
    webapp_url: str = ""
    miniapp_auth_max_age: int = 86400
    game_chat_id: int = 0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def admins(self) -> set[int]:
        result: set[int] = set()
        for value in self.admin_ids.split(","):
            value = value.strip()
            if value.isdigit():
                result.add(int(value))
        return result

    @property
    def normalized_database_url(self) -> str:
        url = self.database_url
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        if url.startswith("postgresql://") and "+asyncpg" not in url:
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
