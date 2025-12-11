import asyncio
import concurrent.futures
import itertools
import os
import random
import time
import threading
import signal

from playwright.async_api import async_playwright, BrowserContext, Playwright
from playwright._impl._errors import TargetClosedError, Error as PlaywrightError
from playwright_stealth import Stealth

from core.modules.fingerprint import generate_fingerprint
from core.modules.proxy_main import ProxyManager
from core.modules.warmup_manager import WarmupManager
from core.utils.config import config
from core.utils.get_videos import get_videos
from core.utils.logger import get_logger
from core.utils.screenshot_logger import debug_screenshot

class Rutube:
    def __init__(
            self,
            profile_dir: str = config.PROFILES_DIR,
            num_contexts_per_thread: int = config.CONTEXTS_PER_THREAD,
            num_threads: int = config.THREADS
    ):
        self.logger = get_logger(__name__)
        self.count: int = 0
        self.num_contexts_per_thread = num_contexts_per_thread  # Контексты на поток
        self.num_threads = num_threads  # Количество потоков

        self.stop_event = threading.Event()  # Для graceful shutdown
        self.shutdown_initiated = False
        self.warmup_manager = WarmupManager(profile_dir)

        self.proxy_manager = ProxyManager()
        self.proxies = []  # Загружаем прокси при инициализации

        self.proxy_cycle = itertools.cycle(self.proxies) if self.proxies else None  # Создаем цикличный итератор
        self.profiles_dir = config.PROFILES_DIR

        self.video_list: list[str] = get_videos()
        self.logger.debug(self.video_list)

    def _clean_profile(self):
        import shutil, os
        profiles_dir = self.profiles_dir  # если ты внутри AdvancedRutubeBot
        try:
            if os.path.exists(profiles_dir):
                shutil.rmtree(profiles_dir)
                os.makedirs(profiles_dir, exist_ok=True)
                self.logger.info("Profiles directory cleaned")
        except Exception as e:
            self.logger.error(f"Failed to clear profiles directory: {e}")

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

        profile_dir = os.path.join(self.profile_dir, f"thread_{worker_id}_context_{context_id}")
        os.makedirs(self.profile_dir, exist_ok=True)

        args = [
            f"--window-size={fp['viewport_width']},{fp['viewport_height']}",
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            f"--lang={fp['language']}",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-setuid-sandbox",
        ]
        proxy = next(self.proxy_cycle) if self.proxy_cycle else None
        self.logger.info(f'starting context [T{worker_id}-C{context_id}] with proxy: {proxy}')
        try:
            context = await playwright.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                executable_path=str(config.CHROME),
                headless=True if config.HEADLESS == 'True' else False,
                viewport={"width": fp["viewport_width"], "height": fp["viewport_height"]},
                user_agent=fp["user_agent"],
                locale=fp["language"],
                timezone_id=fp.get("timezone", None),
                args=args,
                ignore_https_errors=True,
                java_script_enabled=True,
                bypass_csp=False,
                proxy=proxy
            )
            if proxy:
                self.logger.info(f"[W{worker_id}] Используется прокси: {proxy['server']}")
            await self._apply_advanced_stealth(context, fp)
            try:
                await self.warmup_manager.warmup_profile(context, f"{worker_id}-{context_id}")
            except Exception as err:
                self.logger.warning(err)
            return context
        except Exception as err:
            self.logger.error(f"Failed to create context: {err}")
            raise err

    async def _watch_video(self, page, url: str, worker_id: str):
        """Просмотр видео с проверкой прогресса (адаптировано под прямой video-элемент Rutube)"""
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            self.logger.debug(f"[W{worker_id}] 👤 Имитирую поведение пользователя...")
            await asyncio.sleep(random.uniform(0.2, 1.5))
            print(f'starting watch {url}')
            for _ in range(3):
                html = await page.content()
                if "video" in html.lower():
                    break
                await asyncio.sleep(1)

            await debug_screenshot(page=page, dir=__name__, name=f"video_loaded_{worker_id}")

            # page.on("console", lambda msg: self.logger.debug(f"PAGE LOG: {msg.text}"))
            # page.on("pageerror", lambda err: self.logger.error(f"PAGE ERROR: {err}"))

            duration_el = await page.query_selector(".time-block-module__duration___RQctT")
            duration: float = 40

            for _ in range(random.randint(2, 5)):
                try:
                    scroll_amount = random.randint(150, 900)
                    await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
                    await asyncio.sleep(random.uniform(0.2, 2.5))
                    await page.evaluate("window.scrollTo(0, 0)")
                    await asyncio.sleep(random.uniform(0.2, 2.5))
                    await page.get_by_role("button", name="Закрыть", exact=True).click()

                except (TargetClosedError, PlaywrightError) as err:
                    self.logger.debug(f"[W{worker_id}] {err}")

            await debug_screenshot(page=page, dir=__name__, name=f"debug_{worker_id}")

            try:
                duration = float(await duration_el.text_content() if duration_el else None)
                await debug_screenshot(page=page, dir=__name__, name=f"debug_{worker_id}")
            except Exception as e:
                await debug_screenshot(page=page, dir=__name__, name=f"EXCEPTION_{worker_id}")

            watch_duration = random.uniform(
                duration * config.WATCH_DURATION_MIN,
                duration * config.WATCH_DURATION_MAX
            )
            await asyncio.sleep(watch_duration)

            summary_time = await page.query_selector(".time-block-module__currentTime___Fo3jS")
            if duration - summary_time > 20:
                self.logger.debug(f"[W{worker_id}] Video playback confirmed ({summary_time:.1f}s)")
                return True
            else:
                self.logger.debug(
                    f"[W{worker_id}] Video failed to play properly (progress: {summary_time:.1f}s)")
                return False
        except (TargetClosedError, PlaywrightError):
            return False

    async def _context_task(self, playwright: Playwright, thread_id: int, context_id: int):
        """Задача для одного контекста: warmup + цикл просмотров с перебором видео"""
        context = await self._generate_context(playwright, thread_id, context_id)
        self.logger.debug(f'Starting task [T{thread_id}-C{context_id}]')
        page = await context.new_page()
        try:
            video_index = 0
            while not self.stop_event.is_set():
                try:
                    video_url = self.video_list[video_index]
                    video_index = (video_index + 1) % len(self.video_list)
                    if await self._watch_video(page, video_url, f"T{thread_id}-C{context_id}"):
                        self.count += 1
                    # await page.goto('rutube.ru')
                    # await asyncio.sleep(random.uniform(1, 4))
                except Exception as e:
                    self.logger.error(f"[T{thread_id}-C{context_id}] Error: {e}")
        finally:
            try:
                await context.close()
            except:
                pass
            self.logger.info(f"[T{thread_id}-C{context_id}] Context closed")

    async def _thread_main(self, thread_id: int):
        """Асинхронный main для потока: запускает несколько контекстов параллельно"""
        if config.PRO or not config.PRO:
            try:
                async with Stealth().use_async(async_playwright()) as pw:
                    context_tasks = []
                    for context_id in range(self.num_contexts_per_thread):
                        task = asyncio.create_task(self._context_task(pw, thread_id, context_id))
                        context_tasks.append(task)
                        await asyncio.sleep(random.uniform(1, 8))  # Старт с задержкой для снижения всплесков
                    await asyncio.gather(*context_tasks, return_exceptions=True)
            except Exception as err:
                self.logger.error(err)
                raise
        # else:
        #     async with Stealth().use_async(async_playwright()) as pw:
        #         context_tasks = []
        #         for context_id in range(self.num_contexts_per_thread):

    def _run_thread(self, thread_id: int):
        """Запуск async loop в потоке"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._thread_main(thread_id))
        except KeyboardInterrupt:
            self.logger.info(f"Thread {thread_id} received shutdown")
            self.stop_event.set()
            self.shutdown_initiated = True
            for task in asyncio.all_tasks(loop):
                task.cancel()
            loop.run_until_complete(asyncio.gather(*asyncio.all_tasks(loop), return_exceptions=True))
        except Exception as err:
            self.logger.error(err)
        finally:
            loop.close()

    def start(self):
        """Запуск многопоточной системы"""
        #asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        self.proxies = asyncio.run(self.proxy_manager.get_proxies())
        try:
            self._clean_profile()
        except:
            pass
        def signal_handler(sig, frame):
            # print(f'Watched video count: {self.count}')
            self.logger.info("Signal received, initiating shutdown")
            self.stop_event.set()
            self.shutdown_initiated = True

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        self.logger.info(
            f"Starting Rutube bot with {self.num_threads} threads, {self.num_contexts_per_thread} contexts each")

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.num_threads) as executor:
            futures = []
            for thread_id in range(self.num_threads):
                future = executor.submit(self._run_thread, thread_id)
                futures.append(future)
                time.sleep(random.uniform(2, 5))
            concurrent.futures.wait(futures, return_when=concurrent.futures.ALL_COMPLETED)
