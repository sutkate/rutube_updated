import asyncio
import concurrent.futures
import itertools
import os
import random
import time
import threading
import signal

from patchright.async_api import Page
from playwright.async_api import async_playwright, BrowserContext, Playwright
from playwright._impl._errors import TargetClosedError, Error as PlaywrightError
from playwright_stealth import Stealth

from core.modules.context_manager import ContextManager
from core.modules.proxy_main import ProxyManager
from core.modules.warmup_manager import WarmupManager
from core.utils.config import config
from core.utils.get_videos import get_videos, get_promo_videos
from core.utils.logger import get_logger
from core.utils.screenshot_logger import debug_screenshot

class Rutube:
    def __init__(
            self,
            num_contexts_per_thread: int = config.CONTEXTS_PER_THREAD,
            num_threads: int = config.THREADS
    ):
        self.proxy_manager = ProxyManager()
        self.proxies = []
        self.proxy_cycle = None

        self.profiles_dir = config.PROFILES_DIR
        self.logger = get_logger(__name__)
        self.count: int = 0
        self.num_contexts_per_thread = num_contexts_per_thread  # Контексты на поток
        self.num_threads = num_threads  # Количество потоков

        self.stop_event = threading.Event()  # Для graceful shutdown
        self.shutdown_initiated = False
        self.warmup_manager = WarmupManager(self.profiles_dir)

        self.video_list_main: list[str] = get_videos()
        self.video_list_promo: list[str] = get_promo_videos()
        self.logger.debug(self.video_list_main)

        self.context_manager = ContextManager()

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

    async def _watch_video(self, page, url: str, worker_id: str):
        """Просмотр видео с проверкой прогресса (адаптировано под прямой video-элемент Rutube)"""
        self.proxies = await self.proxy_manager.get_proxies()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            self.logger.debug(f"[W{worker_id}] 👤 Имитирую поведение пользователя: {url}")
            await asyncio.sleep(random.uniform(0.2, 4))
            await page.wait_for_selector("video", timeout=5000)

            await debug_screenshot(page=page, dir=__name__, name=f"video_loaded_{worker_id}")

            for _ in range(random.randint(2, 5)):
                try:
                    scroll_amount = random.randint(150, 900)
                    await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
                    await asyncio.sleep(random.uniform(0.1, 3))
                    await page.evaluate("window.scrollTo(0, 0)")
                    await asyncio.sleep(random.uniform(0.1, 3))
                    await page.get_by_role("button", name="Закрыть", exact=True).click()

                except (TargetClosedError, PlaywrightError) as err:
                    self.logger.debug(f"[W{worker_id}] {err}")

            await debug_screenshot(page=page, dir=__name__, name=f"debug_{worker_id}")
            watch_duration = random.uniform(
                config.WATCH_DURATION_MIN,
                config.WATCH_DURATION_MAX
            )
            self.logger.debug(f'WATCH_DURATION FOR VIDEO {url} == {watch_duration}')
            await asyncio.sleep(watch_duration)

            return True
        except (TargetClosedError, PlaywrightError) as e:
            self.logger.debug(f'[ERROR] Error while watching video: {e}')

    async def _context_task(self, playwright: Playwright, thread_id: int, context_id: int):
        max_restarts = 3
        restarts = 0
        context_expired = False
        try:
            while not self.stop_event.is_set():
                context: BrowserContext = await self.context_manager.get_context(
                    playwright, thread_id, context_id, self.proxy_manager
                )
                lifetime_limit = config.CONTEXT_LIFETIME * random.uniform(0.5, 1.2)
                started_at = time.monotonic()
                self.logger.info(
                    f"[T{thread_id}-C{context_id}] Context started at {started_at}"
                )
                page: Page = await context.new_page()
                index_main = 0
                index_promo = 0

                while not self.stop_event.is_set():
                    if time.monotonic() - started_at > lifetime_limit:
                        context_expired = True
                        self.logger.info(
                            f"[T{thread_id}-C{context_id}] Context lifetime expired"
                        )
                        break
                    if self.video_list_promo and random.random() > config.MAIN_LIST_PROBABILITY:
                        target_url = self.video_list_promo[index_promo]
                        index_promo = (index_promo + 1) % len(self.video_list_promo)
                    else:
                        target_url = self.video_list_main[index_main]
                        index_main = (index_main + 1) % len(self.video_list_main)
                    try:
                        ok = await self._watch_video(
                            page, target_url, f"T{thread_id}-C{context_id}"
                        )
                        if ok:
                            self.count += 1
                    except TargetClosedError:
                        self.logger.warning(
                            f"[T{thread_id}-C{context_id}] Target closed — killing context"
                        )
                        raise
                    except PlaywrightError as e:
                        self.logger.warning(
                            f"[T{thread_id}-C{context_id}] Page error: {e}"
                        )
                        await asyncio.sleep(1)
                    self.logger.debug('Context finished work')
                    await asyncio.sleep(random.uniform(1, 3))
                if context_expired:
                    await page.close()
                    await context.close()
                    continue
                await page.close()
                await context.close()
                self.logger.info('Context closed')

        except asyncio.CancelledError:
            return

        except TargetClosedError as err:
            restarts += 1
            self.logger.warning(
                f"[T{thread_id}-C{context_id}] Context died: {err}\n\n Restart {restarts}"
            )
            await asyncio.sleep(2)

        except Exception as e:
            restarts += 1
            self.logger.error(
                f"[T{thread_id}-C{context_id}] Fatal context error: {e}"
            )
            await asyncio.sleep(3)
        self.logger.info(
            f"[T{thread_id}-C{context_id}] Context task finished"
        )

    async def _thread_main(self, thread_id: int):
        """Асинхронный main для потока: запускает несколько контекстов параллельно"""
        if config.PRO or not config.PRO:
            async with Stealth().use_async(async_playwright()) as pw:
                context_tasks = []
                for context_id in range(self.num_contexts_per_thread):
                    task = asyncio.create_task(self._context_task(pw, thread_id, context_id))
                    context_tasks.append(task)
                    await asyncio.sleep(random.uniform(1, 8))  # Старт с задержкой для снижения всплесков
                await asyncio.gather(*context_tasks, return_exceptions=True)
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
        try:
            self.proxy_cycle = itertools.cycle(self.proxies)
            self._clean_profile()

            def signal_handler(sig, frame):
                self.logger.info(f"Signal {sig} received, shutting down...")
                self.stop_event.set()
                self.shutdown_initiated = True

            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)

            self.logger.info(
                f"Starting with {self.num_threads} threads, "
                f"{self.num_contexts_per_thread} contexts each"
            )
            # ... (начало функции без изменений) ...
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.num_threads) as executor:
                futures = []
                for thread_id in range(self.num_threads):
                    future = executor.submit(self._run_thread, thread_id)
                    futures.append(future)
                    time.sleep(random.uniform(1, 3))

                try:
                    concurrent.futures.wait(futures, return_when=concurrent.futures.ALL_COMPLETED)
                except KeyboardInterrupt:
                    self.logger.info("Keyboard interrupt, stopping threads...")
                    self.stop_event.set()
                    # Даем время на graceful shutdown
                    executor.shutdown(wait=True)

        except Exception as e:
            self.logger.error(f"Start failed: {e}")
        finally:
            self.logger.info(f"Bot stopped. Total views: {self.count}")