import asyncio
import concurrent.futures
import itertools
import os
import random
import time
import threading
import signal

from patchright.async_api import async_playwright, BrowserContext, Playwright
from patchright._impl._errors import TargetClosedError, Error as PlaywrightError
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
            profile_dir: str,
            num_contexts_per_thread: int = config.CONTEXTS_PER_THREAD,
            num_threads: int = config.THREADS
    ):
        self.profile_dir = profile_dir
        self.logger = get_logger(__name__)
        self.num_contexts_per_thread = num_contexts_per_thread  # Контексты на поток
        self.num_threads = num_threads  # Количество потоков
        self.stop_event = threading.Event()  # Для graceful shutdown
        self.shutdown_initiated = False
        self.warmup_manager = WarmupManager(self.profile_dir)
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

    async def _check_protection(self, page):
        """Проверка наличия защитной страницы"""
        try:
            content = await page.content(timeout=10000)
            protection_indicators = [
                "cloudflare", "ddos", "challenge", "captcha",
                "security check", "доступ ограничен", "подтвердите",
                "recaptcha", "hcaptcha", "turnstile", "произошла ошибка"
            ]
            content_lower = content.lower()
            return any(indicator in content_lower for indicator in protection_indicators)
        except (TargetClosedError, PlaywrightError):
            return False

    async def _apply_advanced_stealth(self, context: BrowserContext, fp: dict):
        """
        Мягкий stealth, без вмешательства в WebGL/Canvas/Audio/Screen/Connection/UserAgentData.
        Не ломает видеоплееры — только безопасные правки.
        """
        try:
            # Подготовим значения, которые вставим в скрипт (экранируем JSON-представлением)
            language = fp.get('language', 'ru-RU')
            languages = fp.get('languages') or [language, 'en-US']
            platform = fp.get('platform', 'Win32')

            hwc_base = int(fp.get('hardware_concurrency', 4))
            hwc = max(1, hwc_base + random.choice([-1, 0, 1]))

        except (TargetClosedError, PlaywrightError, Exception) as err:
            self.logger.warning(f"Stealth init script failed or context closed: {err}")

    async def _generate_context(self, playwright: Playwright, worker_id: int, context_id: int) -> BrowserContext:
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

        # Собираем аргументы — избегаем опций, которые ломают плеер
        args = [
            f"--window-size={fp['viewport_width']},{fp['viewport_height']}",
            "--disable-blink-features=AutomationControlled",  # мягкий stealth
            "--disable-features=IsolateOrigins,site-per-process",
            f"--lang={fp['language']}",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-setuid-sandbox",
        ]
        proxy = next(self.proxy_cycle) if self.proxy_cycle else None
        self.logger.debug(proxy)
        try:
            # Запускаем persistent context в видимом режиме (headful) — это критично для корректной работы медиадекодеров
            context = await playwright.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                executable_path=config.CHROME_DIR,
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
            raise

    async def _watch_video(self, page, url: str, worker_id: str):
        """Просмотр видео с проверкой прогресса (адаптировано под прямой video-элемент Rutube)"""
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            self.logger.info(f"[W{worker_id}] 👤 Имитирую поведение пользователя...")

            await asyncio.sleep(1)

            # Ждем загрузки видео
            for _ in range(3):
                html = await page.content()
                if "video" in html.lower():
                    break
                await asyncio.sleep(1)
            else:
                self.logger.warning(f"[W{worker_id}] Видео не найдено на странице")
                return False

            await debug_screenshot(page=page, dir=__name__, name=f"video_loaded_{worker_id}")

            # Логирование ошибок страницы
            page.on("pageerror", lambda err: self.logger.error(f"PAGE ERROR: {err}"))

            # Получаем длительность видео
            duration_el = await page.query_selector(".time-block-module__duration___RQctT")
            duration: float = 120

            try:
                if duration_el:
                    duration_text = await duration_el.text_content()
                    if duration_text:
                        # Конвертируем время в секунды (формат "mm:ss" или "hh:mm:ss")
                        time_parts = duration_text.strip().split(":")
                        if len(time_parts) == 3:  # hh:mm:ss
                            hours, minutes, seconds = time_parts
                            duration = int(hours) * 3600 + int(minutes) * 60 + int(seconds)
                        elif len(time_parts) == 2:  # mm:ss
                            minutes, seconds = time_parts
                            duration = int(minutes) * 60 + int(seconds)
            except Exception as e:
                self.logger.debug(f"[W{worker_id}] Не удалось распарсить длительность: {e}")

            # Случайный скроллинг с человеческими паузами
            for _ in range(random.randint(25, 50)):
                await page.reload()
                for _ in range(random.randint(2, 5)):
                    try:
                        scroll_amount = random.randint(150, 900)
                        await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
                        await asyncio.sleep(random.uniform(0.8, 2.5))
                        await page.evaluate("window.scrollTo(0, 0)")
                        await asyncio.sleep(random.uniform(0.8, 2.5))

                        # Пробуем закрыть рекламу, если есть
                        try:
                            close_btn = page.get_by_role("button", name="Закрыть", exact=True)
                            if await close_btn.count() > 0:
                                await close_btn.first.click()
                        except:
                            pass

                    except (TargetClosedError, PlaywrightError) as err:
                        self.logger.debug(f"[W{worker_id}] Ошибка при скроллинге: {err}")
                        # Не прерываем выполнение, продолжаем просмотр

            await debug_screenshot(page=page, dir=__name__, name=f"before_play_{worker_id}")

            # Начальная пауза перед просмотром
            await asyncio.sleep(random.uniform(2, 4))

            # Время просмотра (50-100% от длительности видео)
            watch_duration = random.uniform(duration * 0.5, min(duration, 300))  # Ограничиваем максимум 5 минутами
            self.logger.info(f"[W{worker_id}] Буду смотреть {watch_duration:.1f} секунд из {duration:.1f}")

            await asyncio.sleep(watch_duration)

            # Проверяем прогресс просмотра
            try:
                summary_time_el = await page.query_selector(".time-block-module__currentTime___Fo3jS")
                if summary_time_el:
                    summary_time_text = await summary_time_el.text_content()
                    if summary_time_text:
                        # Конвертируем текущее время в секунды
                        time_parts = summary_time_text.strip().split(":")
                        if len(time_parts) == 3:
                            hours, minutes, seconds = time_parts
                            summary_time = int(hours) * 3600 + int(minutes) * 60 + int(seconds)
                        elif len(time_parts) == 2:
                            minutes, seconds = time_parts
                            summary_time = int(minutes) * 60 + int(seconds)
                        else:
                            summary_time = watch_duration

                        if summary_time >= duration - 20 or summary_time >= watch_duration * 0.8:
                            self.logger.info(f"[W{worker_id}] Video playback confirmed ({summary_time:.1f}s)")
                            return True
                        else:
                            self.logger.warning(
                                f"[W{worker_id}] Video failed to play properly (progress: {summary_time:.1f}s)")
                            return False
            except Exception as e:
                self.logger.debug(f"[W{worker_id}] Не удалось получить прогресс: {e}")
                # Если не смогли получить прогресс, считаем что просмотр успешен
                return True

            return True

        except (TargetClosedError, PlaywrightError) as e:
            self.logger.error(f"[W{worker_id}] Ошибка браузера: {e}")
            return False
        except Exception as e:
            self.logger.error(f"[W{worker_id}] Неожиданная ошибка: {e}")
            return False

    async def _context_task(self, playwright: Playwright, thread_id: int, context_id: str):
        """Задача для одного контекста: warmup + цикл просмотров с перебором видео"""
        context = None

        try:
            context = await self._generate_context(playwright, thread_id, context_id)
            video_index = 0
            consecutive_failures = 0

            while not self.stop_event.is_set():
                page = None
                try:
                    # Создаем новую страницу для каждого видео
                    page = await context.new_page()

                    # Настройка таймаутов
                    page.set_default_timeout(30000)

                    # Берем URL по кругу
                    video_url = self.video_list[video_index]
                    video_index = (video_index + 1) % len(self.video_list)

                    self.logger.info(f"[T{thread_id}-C{context_id}] Начинаю просмотр видео {video_index}: {video_url}")

                    # Основной просмотр
                    success = await self._watch_video(page, video_url, f"{thread_id}-{context_id}")

                    if success:
                        consecutive_failures = 0
                        self.logger.info(f"[T{thread_id}-C{context_id}] Видео просмотрено успешно")
                    else:
                        consecutive_failures += 1
                        self.logger.warning(
                            f"[T{thread_id}-C{context_id}] Ошибка просмотра видео (попытка {consecutive_failures})")

                    # Если много ошибок подряд - небольшая пауза
                    if consecutive_failures >= 3:
                        self.logger.warning(f"[T{thread_id}-C{context_id}] 3 ошибки подряд, делаю паузу")
                        await asyncio.sleep(random.uniform(30, 60))
                        consecutive_failures = 0

                    # Пауза перед следующим видео
                    pause_time = random.uniform(40, 160)
                    self.logger.info(f"[T{thread_id}-C{context_id}] Пауза {pause_time:.1f} сек до следующего видео")
                    await asyncio.sleep(pause_time)

                except Exception as e:
                    self.logger.error(f"[T{thread_id}-C{context_id}] Ошибка в цикле просмотра: {e}")
                    consecutive_failures += 1
                    await asyncio.sleep(random.uniform(10, 30))  # Короткая пауза при ошибке

                finally:
                    # Всегда закрываем страницу после просмотра
                    if page and not page.is_closed():
                        try:
                            await page.close()
                        except Exception as e:
                            self.logger.debug(f"[T{thread_id}-C{context_id}] Ошибка при закрытии страницы: {e}")

        except Exception as e:
            self.logger.error(f"[T{thread_id}-C{context_id}] Критическая ошибка контекста: {e}")

        finally:
            # Закрываем контекст только при завершении задачи
            if context:
                try:
                    await context.close()
                    self.logger.info(f"[T{thread_id}-C{context_id}] Контекст закрыт")
                except Exception as e:
                    self.logger.debug(f"[T{thread_id}-C{context_id}] Ошибка при закрытии контекста: {e}")

    async def _thread_main(self, thread_id: int):
        """Асинхронный main для потока: запускает несколько контекстов параллельно"""
        async with Stealth().use_async(async_playwright()) as pw:
            context_tasks = []
            for context_id in range(self.num_contexts_per_thread):
                task = asyncio.create_task(self._context_task(pw, thread_id, context_id))
                context_tasks.append(task)
                await asyncio.sleep(random.uniform(1, 3))  # Старт с задержкой для снижения всплесков

            await asyncio.gather(*context_tasks, return_exceptions=True)

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
            # Cancel all tasks
            for task in asyncio.all_tasks(loop):
                task.cancel()
            loop.run_until_complete(asyncio.gather(*asyncio.all_tasks(loop), return_exceptions=True))
        finally:
            self._clean_profile()
            loop.close()

    def start(self):
        """Запуск многопоточной системы"""
        self.proxies = asyncio.run(self.proxy_manager.get_proxies())
        self._clean_profile()

        def signal_handler(sig, frame):
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
                time.sleep(random.uniform(2, 5))  # Задержка между запуском потоков для снижения всплесков
            # Ждем завершения
            concurrent.futures.wait(futures, return_when=concurrent.futures.ALL_COMPLETED)