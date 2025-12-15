import os
import random

from playwright.async_api import async_playwright, BrowserContext, Playwright
from playwright._impl._errors import TargetClosedError, Error as PlaywrightError
from patchright.async_api import Playwright, BrowserContext
from pydantic.v1.class_validators import all_kwargs

from core.modules.fingerprint import generate_fingerprint
from core.modules.proxy_main import ProxyManager
from core.modules.warmup_manager import WarmupManager
from core.utils.config import config
from core.utils.logger import get_logger

class ContextManager:
    def __init__(self):
        self.profiles_dir = config.PROFILES_DIR
        self.warmup_manager = WarmupManager()
        self.logger = get_logger(
            __name__
        )
    async def _apply_advanced_stealth(self, context: BrowserContext, fp: dict):
        """
        Мягкий stealth, без вмешательства в WebGL/Canvas/Audio/Screen/Connection/UserAgentData.
        Не ломает видеоплееры — только безопасные правки.
        """
        try:
            language = fp.get('language', 'ru-RU')
            languages = fp.get('languages') or [language, 'en-US']
            platform = fp.get('platform', 'Win32')

            hwc_base = int(fp.get('hardware_concurrency', 4))
            hwc = max(1, hwc_base + random.choice([-1, 0, 1]))
        except (TargetClosedError, PlaywrightError, Exception) as err:
            self.logger.warning(f"Stealth init script failed or context closed: {err}")

    async def _generate_context(
            self,
            proxy_manager: ProxyManager,
            playwright: Playwright,
            worker_id: int,
            context_id: int
    ) -> BrowserContext:
        """
        Генерация контекста:
        - headless=False (чтобы не ломать декодеры и рендеринг)
        - НЕ отключаем GPU
        - НЕ трогаем screen и webgl
        - применяем _apply_advanced_stealth (мягкий)
        """
        fp = generate_fingerprint()  # остаётся использовать вашу функцию генерации отпечатков

        os.makedirs(self.profiles_dir, exist_ok=True)

        args = [
            f"--window-size={fp['viewport_width']},{fp['viewport_height']}",
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            f"--lang={fp['language']}",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-session-crashed-bubble",
            "--disable-restore-session-state",
            "--disable-background-networking",
            "--disable-sync",
            "--no-first-run",
            "--no-default-browser-check",
        ]

        proxy = await proxy_manager.get_random_proxy()
        self.logger.info(f'starting context [T{worker_id}-C{context_id}] with proxy: {proxy}')
        try:
            browser = await playwright.chromium.launch(
                executable_path=str(config.CHROME),
                headless=True if config.HEADLESS == 'True' else False,
                args=args,
                proxy=proxy,
            )

            context: BrowserContext = await browser.new_context(
                viewport={"width": fp["viewport_width"], "height": fp["viewport_height"]},
                user_agent=fp["user_agent"],
                locale=fp["language"],
                timezone_id=fp.get("timezone", None),
                ignore_https_errors=True,
                java_script_enabled=True,
                bypass_csp=False,
            )

            if proxy:
                self.logger.info(f"[W{worker_id}] Используется прокси: {proxy['server']}")
            await self._apply_advanced_stealth(context, fp)

            page = await context.new_page()
            await self.warmup_manager.warmup_profile(page, f"{worker_id}-{context_id}")
            await page.close()

            return context
        except Exception as err:
            self.logger.error(f"Failed to create context: {err}")
            raise err

    async def get_context(
            self,
            pw: Playwright,
            worker_id: int,
            context_id: int,
            proxy_manager: ProxyManager
    ) -> BrowserContext:
        context: BrowserContext = await self._generate_context(
            proxy_manager=proxy_manager,
            playwright=pw,
            worker_id=worker_id,
            context_id=context_id
        )
        return context