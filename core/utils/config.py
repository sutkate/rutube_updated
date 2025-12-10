from pydantic_settings import BaseSettings


class Config(BaseSettings):
    DEBUG: bool = True
    THREADS: int = 8
    CONTEXTS_PER_THREAD: int = 4

    PROXY_PATH: str = 'proxies.txt'
    VIDEO_PATH: str = 'videos.txt'
    CHROME_DIR: str = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
    PROFILES_DIR: str = 'profiles'
    HEADLESS: str = 'True'
config = Config()