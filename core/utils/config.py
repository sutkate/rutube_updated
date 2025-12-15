from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file='.settings', env_file_encoding='utf-8')



    DEBUG: bool = False
    DEBUG_SCREENSHOTS: bool = False
    THREADS: int = 5
    CONTEXTS_PER_THREAD: int = 5

    PROXY_PATH: str = 'proxies.txt'
    VIDEO_PATH: str = 'videos.txt'

    CHROME: str = "C:/Program Files/Google/Chrome/Application/chrome.exe"
    PROFILES_DIR: str = 'profiles'

    HEADLESS: str = 'True'

    PRO: bool = False

    CONTEXT_LIFETIME: float = 10 * 60
    WARMUP_MAX_SITES: int = 3
    WARMUP_MIN_SITES: int = 1
    PAUSES_ON_WARMUP: float = 4.0

    WATCH_DURATION_MIN: float = 4
    WATCH_DURATION_MAX: float = 15

config = Config()