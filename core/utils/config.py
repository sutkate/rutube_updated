from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file='.settings', env_file_encoding='utf-8')



    DEBUG: bool = True
    DEBUG_SCREENSHOTS: bool = False
    THREADS: int = 2
    CONTEXTS_PER_THREAD: int = 2

    PROXY_PATH: str = 'proxies.txt'
    VIDEO_PATH: str = 'videos.txt'

    CHROME: str = "C:/Program Files/Google/Chrome/Application/chrome.exe"
    PROFILES_DIR: str = 'profiles'

    HEADLESS: str = 'True'

    PRO: bool = True

    WARMUP_MAX_SITES: int = 4
    WARMUP_MIN_SITES: int = 2
    PAUSES_ON_WARMUP: float = 4.0

    WATCH_DURATION_MIN: float = 0.05
    WATCH_DURATION_MAX: float = 0.1

config = Config()