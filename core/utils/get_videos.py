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
            'https://rutube.ru/video/3135f282f0fed7ea5fd730da4bd9e791/',
            'https://rutube.ru/video/57e6349edf06db6996db5022d1f7655c/',
            'https://rutube.ru/video/185eda3a7e3864c33c329cbf0d52ae0e/',
            'https://rutube.ru/video/66a65b99a7e098741e0ca991434433fe/',
            'https://rutube.ru/video/eff1a1b2012d6ea90b2c509a1a895676/',
            'https://rutube.ru/video/50238d62713b46e044854983167813c7/',
            'https://rutube.ru/video/b53f860f7e0dadac61b2f028e91efe45/',
            'https://rutube.ru/video/0f668fa6b0ff52eb1c812a7f5f776a0a/',
            'https://rutube.ru/video/b7922bce768a749c47b814ab4391faa5/',
            'https://rutube.ru/video/cb72b695a5411b1b7aee5168c80743ef/'
        ]

def get_promo_videos() -> list[str] | None:
    # if not config.PRO:
    #     return [
    #         'https://rutube.ru/video/3135f282f0fed7ea5fd730da4bd9e791/',
    #         'https://rutube.ru/video/57e6349edf06db6996db5022d1f7655c/',
    #         'https://rutube.ru/video/185eda3a7e3864c33c329cbf0d52ae0e/',
    #         'https://rutube.ru/video/66a65b99a7e098741e0ca991434433fe/',
    #         'https://rutube.ru/video/eff1a1b2012d6ea90b2c509a1a895676/',
    #         'https://rutube.ru/video/50238d62713b46e044854983167813c7/',
    #         'https://rutube.ru/video/b53f860f7e0dadac61b2f028e91efe45/',
    #         'https://rutube.ru/video/0f668fa6b0ff52eb1c812a7f5f776a0a/',
    #         'https://rutube.ru/video/b7922bce768a749c47b814ab4391faa5/'
    #     ]
    # else:
    #     return []
    return []