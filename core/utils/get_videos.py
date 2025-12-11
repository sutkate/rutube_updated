from pathlib import Path

from core.utils.config import config

def get_videos() -> list[str]:
    if config.PRO:
        videos_file = Path(config.VIDEO_PATH)  # Укажите путь к файлу, если он не в текущей директории

        with open(videos_file, 'r', encoding='utf-8') as f:
            videos_lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]

        return videos_lines
    else:
        return [
        ]
