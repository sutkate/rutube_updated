from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file='.settings', env_file_encoding='utf-8')

    DEBUG: bool = True
    THREADS: int = 8
    CONTEXTS_PER_THREAD: int = 4

    PROXY_PATH: str = 'proxies.txt'
    VIDEO_PATH: str = 'videos.txt'

    CHROME: str = "C:/Program Files/Google/Chrome/Application/chrome.exe"
    PROFILES_DIR: str = 'profiles'

    HEADLESS: str = 'True'

    PRO: bool = True


config = Config()