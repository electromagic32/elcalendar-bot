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

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}/{self.DB_NAME}"

    class Config:
        env_file = ".env"


settings = Settings()
