from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    BOT_TOKEN: str
    DB_HOST: str = "db"
    DB_USER: str = "bot"
    DB_PASSWORD: str = "bot"
    DB_NAME: str = "calbot"
    TIMEZONE: str = "Europe/Moscow"
    WEBAPP_URL: str = "https://elmagique.duckdns.org:7443/cal/"
    BOT_USERNAME: str = "Elcalendar_bot"
    ALLOWED_CHAT_IDS: list[int] = []

    @field_validator("ALLOWED_CHAT_IDS", mode="before")
    @classmethod
    def parse_chat_ids(cls, v):
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return v

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}/{self.DB_NAME}"

    class Config:
        env_file = ".env"


settings = Settings()
