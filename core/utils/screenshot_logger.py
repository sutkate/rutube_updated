import configparser
import time
from pathlib import Path
import re
from urllib.parse import urlparse

from patchright._impl._errors import TargetClosedError, Error as PlaywrightError

from core.utils.config import config
from core.utils.logger import get_logger

logger = get_logger(logger_name='screenshot_debug')


async def debug_screenshot(page, dir, name) -> None:
    if config.DEBUG:
        if name.startswith(('http://', 'https://')):
            parsed = urlparse(name)
            safe_name = parsed.netloc.replace('.', '_')
        else:
            safe_name = name
        safe_name = re.sub(r'[<>:"/\\|?*]', '_', safe_name)
        ss_path = Path(f"logs/screenshots")
        ss_path.mkdir(exist_ok=True)
        ss_path = ss_path / dir
        ss_path.mkdir(exist_ok=True)

        ss_path = ss_path / f"debug_{safe_name}_{int(time.time())}.png"
        try:
            await page.screenshot(path=ss_path, full_page=True, timeout=10000)
            logger.info(f"Скриншот сохранен: {ss_path}")
        except (TargetClosedError, PlaywrightError) as e:
            logger.warning(f"Скриншот пропущен из-за закрытия: {e}")
        except Exception as e:
            logger.error(f"Ошибка при создании скриншота: {e}")