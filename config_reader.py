from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

    bot_token: SecretStr
    yookassa_shop_id: SecretStr
    yookassa_secret_key: SecretStr
    admin_ids: str
    channel_id: int
    channel_username: str

# Создаем экземпляр настроек, который будет использоваться в других файлах
config = Settings()