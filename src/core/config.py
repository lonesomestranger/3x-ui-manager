from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    BOT_TOKEN: str
    PANEL_URL: str
    PANEL_LOGIN: str
    PANEL_PASSWORD: str
    PUBLIC_HOST: str
    VLESS_INBOUND_ID: int

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
