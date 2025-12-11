import asyncio
import random
import os
from patchright.async_api import BrowserContext

from core.utils.config import config
from core.utils.logger import get_logger
from core.utils.screenshot_logger import debug_screenshot


class WarmupManager:
    def __init__(self, profile_dir: str, warmup_sites: list[str] = None, num_actions_per_site: int = 4,
                 min_pause: float = config.PAUSES_ON_WARMUP * 0.5, max_pause: float = config.PAUSES_ON_WARMUP * 1.5):
        self.profile_dir = profile_dir
        self.logger = get_logger(__name__)
        self.warmup_sites = warmup_sites or [
            "https://www.google.com", "https://yandex.ru", "https://www.wikipedia.org",
            "https://github.com", "https://stackoverflow.com", "https://habr.com",
            "https://rutube.ru", "https://mail.ru", "https://ria.ru",
            "https://www.rbc.ru", "https://lenta.ru", "https://vk.com"
        ]
        self.num_actions_per_site = num_actions_per_site
        self.min_pause = min_pause
        self.max_pause = max_pause

    async def _human_like_pause(self):
        """Simulates a human-like pause with random duration."""
        await asyncio.sleep(random.uniform(self.min_pause, self.max_pause))

    async def _simulate_human_actions(self, page, worker_id: str):
        self.logger.info(f"[W{worker_id}] Simulating human-like actions...")
        actions = [
            self._random_scroll,
            self._random_click,
            self._random_hover,
            self._random_scroll  # Bias towards scrolling as it's common
        ]
        for _ in range(self.num_actions_per_site):
            action = random.choice(actions)
            try:
                await action(page)
                await self._human_like_pause()
                await debug_screenshot(page=page, dir=__name__, name=page.url)
            except Exception as e:
                await debug_screenshot(page=page,dir=__name__,name=f'EXCEPTION_{page.url}')
                self.logger.debug(f"[W{worker_id}] Action on page {page.url} failed: {e}")

    async def _random_scroll(self, page):
        scroll_amount = random.randint(200, 800)
        direction = random.choice([-1, 1])  # Up or down
        await page.evaluate(f"window.scrollBy(0, {direction * scroll_amount})")

    async def _random_click(self, page):
        elements = await page.query_selector_all('a, button, .card, .item')
        if elements:
            visible_elements = [el for el in elements if await el.is_visible() and await el.is_enabled()]
            if visible_elements:
                element = random.choice(visible_elements)
                await element.scroll_into_view_if_needed()
                await element.click()

    async def _random_hover(self, page):
        elements = await page.query_selector_all('a, button, img, div')
        if elements:
            element = random.choice(elements[:20])  # Limit to avoid overload
            await element.hover()

    async def _rutube_banner(self, page, worker_id):
        self.logger.info(f"Starting rutube warmup for profile {worker_id}")
        try:
            await debug_screenshot(page=page, dir=__name__, name=page.url)
            await page.get_by_role("button", name="Закрыть", exact=True).click()
            await self._human_like_pause()
            await page.get_by_role("link", name="Фильмы", exact=True).click()
            await self._human_like_pause()
            await page.locator("iframe[title=\"Multipass\"]").content_frame.get_by_role("button", name="Закрыть форму").click()
            await self._human_like_pause()
            await page.get_by_role("link", name="Сериалы").click()
            await page.locator("iframe[title=\"Multipass\"]").content_frame.get_by_role("button", name="Закрыть форму").click()
            await self._human_like_pause()
            await page.get_by_role("link", name="Новый год …").click()
            await page.get_by_role("link", name="Каталог …").click()
            await self._human_like_pause()
            await page.get_by_role("link", name="В топе …").click()
            await page.get_by_role("link", name="Shorts …").click()
            await self._human_like_pause()
            await page.get_by_test_id("back-button").first.click()
            await self._human_like_pause()
            await page.get_by_role("link", name="Моё …").click()
            await page.get_by_text("Здесь будет всё ваше — история просмотра, подписки, комментарии и многое другое").click()
            await self._human_like_pause()
            await self._human_like_pause()
            await page.get_by_role("button", name="закрыть").click()
            await page.get_by_role("button", name="Ок").click()
            await self._human_like_pause()
        except Exception as err:
            await debug_screenshot(page=page, dir=__name__, name=f'EXCEPTION_{page.url}')
            self.logger.warning(f'[{worker_id}] Error occurred while rutube warmup: {err}')

    async def warmup_profile(self, context: BrowserContext, profile_id: str) -> BrowserContext:
        self.logger.info(f"Starting extended warmup for profile {profile_id}")
        profile_path = os.path.join(self.profile_dir, profile_id)
        os.makedirs(profile_path, exist_ok=True)
        page = await context.new_page()
        try:
            # Visit multiple sites for extended warmup
            num_sites = random.randint(config.WARMUP_MIN_SITES, config.WARMUP_MAX_SITES)  # More sites for longer warmup
            selected_sites = random.sample(self.warmup_sites, num_sites)

            for site in selected_sites:
                self.logger.info(f"[Profile {profile_id}] Visiting {site}")
                await page.goto(site, wait_until="domcontentloaded", timeout=20000)
                await debug_screenshot(page=page, dir=__name__, name=site)
                await self._simulate_human_actions(page, profile_id)

                await asyncio.sleep(random.uniform(1, 3))
            await page.goto('rutube.ru')
            await self._rutube_banner(page, profile_id)
            self.logger.info(f"Warmup completed for profile {profile_id}. Cookies saved.")

        except Exception as e:
            self.logger.error(f"Warmup failed for {profile_id}: {e}")
        finally:
            await page.close()
        return context