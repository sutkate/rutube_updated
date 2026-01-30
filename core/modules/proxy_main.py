import asyncio
import random

import aiohttp
import aiofiles
import time
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from core.utils.config import config


class ProxyManager:
    TEST_URL = "http://example.com"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    def __init__(self, proxy_path: str = config.PROXY_PATH, debug: bool = config.DEBUG):
        self.logger = logging.getLogger(__name__)
        self.proxy_path = Path(proxy_path)
        self.debug = debug

        self.working_proxies: List[Dict] = []
        self.failed_proxies: List[Dict] = []

    # ==========================================================
    # PUBLIC
    # ==========================================================

    async def get_proxies(self, max_concurrent: int = 100) -> List[Dict]:
        lines = await self._read_proxy_file()
        proxies = self._parse_proxy_lines(lines)

        if not proxies:
            return []

        start = time.monotonic()
        self.working_proxies, self.failed_proxies = await self._check_batch(
            proxies,
            max_concurrent
        )
        elapsed = time.monotonic() - start

        self._print_stats(elapsed)
        self._save_results()

        return self.working_proxies

    async def get_random_proxy(self) -> Optional[Dict]:
        if not self.working_proxies:
            await self.get_proxies()
        return random.choice(self.working_proxies) if self.working_proxies else None

    # ==========================================================
    # CORE
    # ==========================================================

    async def _check_batch(
        self,
        proxy_list: List[Tuple],
        max_concurrent: int
    ) -> Tuple[List[Dict], List[Dict]]:

        timeout = aiohttp.ClientTimeout(
            total=5,
            connect=3,
            sock_read=3
        )

        semaphore = asyncio.Semaphore(max_concurrent)
        working, failed = [], []

        async with aiohttp.ClientSession(
            timeout=timeout,
            headers=self.HEADERS
        ) as session:

            tasks = [
                self._check_single(proxy, session, semaphore)
                for proxy in proxy_list
            ]

            for coro in asyncio.as_completed(tasks):
                result = await coro
                (working if result["working"] else failed).append(result["proxy"])

        return working, failed

    async def _check_single(
        self,
        proxy: Tuple,
        session: aiohttp.ClientSession,
        semaphore: asyncio.Semaphore
    ) -> Dict:

        ip, port, user, password = proxy
        proxy_url = f"http://{ip}:{port}"
        auth = aiohttp.BasicAuth(user, password) if user else None

        async with semaphore:
            try:
                async with session.get(
                    self.TEST_URL,
                    proxy=proxy_url,
                    proxy_auth=auth
                ) as resp:
                    ok = resp.status == 200

            except Exception:
                ok = False

        return {
            "working": ok,
            "proxy": {
                "server": proxy_url,
                "username": user,
                "password": password
            }
        }

    # ==========================================================
    # IO
    # ==========================================================

    async def _read_proxy_file(self) -> List[str]:
        if not self.proxy_path.exists():
            return []

        async with aiofiles.open(self.proxy_path, "r", encoding="utf-8") as f:
            return [
                line.strip()
                for line in await f.readlines()
                if line.strip() and not line.startswith("#")
            ]

    def _parse_proxy_lines(self, lines: List[str]) -> List[Tuple]:
        result = []

        for line in lines:
            try:
                if "@" in line:
                    auth, addr = line.split("@", 1)
                    user, pwd = auth.split(":", 1)
                    ip, port = addr.split(":", 1)
                else:
                    parts = line.split(":")
                    if len(parts) == 2:
                        ip, port = parts
                        user = pwd = None
                    elif len(parts) == 4:
                        ip, port, user, pwd = parts
                    else:
                        continue

                result.append((ip, int(port), user, pwd))
            except Exception:
                continue

        return result

    # ==========================================================
    # OUTPUT
    # ==========================================================

    def _print_stats(self, elapsed: float):
        total = len(self.working_proxies) + len(self.failed_proxies)
        if total == 0:
            return

        self.logger.debug(
            f"\nПрокси проверены за {elapsed:.2f} сек | "
            f"Рабочие: {len(self.working_proxies)} | "
            f"Нерабочие: {len(self.failed_proxies)} | "
            f"{(len(self.working_proxies) / total * 100):.1f}%"
        )

    def _save_results(self):
        if self.working_proxies:
            with open("accepted_proxies.json", "w", encoding="utf-8") as f:
                json.dump(self.working_proxies, f, indent=2, ensure_ascii=False)

        if self.debug and self.failed_proxies:
            with open("failed_proxies.txt", "w", encoding="utf-8") as f:
                for p in self.failed_proxies:
                    f.write(f"{p['server']}\n")
