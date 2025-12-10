import aiofiles
from typing import List, Dict, Optional, Tuple
import aiohttp
import asyncio
import re
from pathlib import Path
import time
import json

from core.utils.config import config
from core.utils.logger import get_logger


class ProxyManager:
    def __init__(self):
        self.logger = get_logger(__name__)
        self.config = config
        self.semaphore = None
        self.working_proxies = []
        self.failed_proxies = []

    async def check_proxy_async(
            self,
            ip: str,
            port: int,
            user: Optional[str] = None,
            password: Optional[str] = None,
            test_url: str = "http://httpbin.org/ip",
            timeout: int = 10,
            session: Optional[aiohttp.ClientSession] = None
    ) -> bool:
        """
        Асинхронно проверяет HTTP/HTTPS прокси
        """
        own_session = False
        if session is None:
            timeout_obj = aiohttp.ClientTimeout(total=timeout)
            session = aiohttp.ClientSession(timeout=timeout_obj)
            own_session = True

        try:
            proxy_str = f"http://{ip}:{port}"
            proxy_auth = aiohttp.BasicAuth(user, password) if user and password else None

            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

            async with session.get(
                    test_url,
                    proxy=proxy_str,
                    proxy_auth=proxy_auth,
                    headers=headers,
                    ssl=False
            ) as response:
                text = await response.text()
                self.logger.debug(f'{response.status} ==> {text}')
                return response.status == 200

        except Exception as e:
            self.logger.debug(f"Прокси {ip}:{port} не работает: {str(e)[:100]}")
            return False
        finally:
            if own_session and session and not session.closed:
                await session.close()

    async def get_proxies(self, max_concurrent: int = 20) -> List[Dict]:
        """
        Основной метод для получения рабочих прокси

        :param max_concurrent: максимальное количество одновременных проверок
        :return: список рабочих прокси в формате [{"server": "...", "username": "...", "password": "..."}, ...]
        """
        proxies_file = Path(self.config.PROXY_PATH)

        # 1. Асинхронное чтение файла
        proxy_lines = await self._read_proxy_file_async(proxies_file)
        if not proxy_lines:
            self.logger.warning("Файл с прокси пуст или не найден")
            return []

        # 2. Парсинг прокси
        proxy_list = self._parse_proxy_lines(proxy_lines)
        if not proxy_list:
            self.logger.warning("Нет валидных прокси в файле.")
            return []

        # 3. Параллельная проверка всех прокси
        self.logger.info(f"Начинаем проверку {len(proxy_list)} прокси...")
        start_time = time.time()

        working_proxies, failed_proxies = await self._check_proxies_batch_with_failed(
            proxy_list,
            max_concurrent=max_concurrent
        )

        elapsed_time = time.time() - start_time

        # 4. Выводим результаты
        self._print_results(working_proxies, failed_proxies, elapsed_time)

        # 5. Сохраняем рабочие прокси в файл
        self._save_working_proxies(working_proxies)

        # 6. Сохраняем нерабочие прокси в файл (опционально)
        self._save_failed_proxies(failed_proxies)

        return working_proxies

    async def _read_proxy_file_async(self, file_path: Path) -> List[str]:
        """Асинхронное чтение файла с прокси"""
        if not file_path.exists():
            self.logger.warning(f"Файл {file_path} не найден.")
            return []

        try:
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                lines = [
                    line.strip() for line in content.split('\n')
                    if line.strip() and not line.startswith('#')
                ]
                self.logger.debug(f"Прочитано {len(lines)} строк из файла")
                return lines
        except Exception as e:
            self.logger.error(f"Ошибка чтения {file_path}: {e}")
            return []

    def _parse_proxy_lines(self, lines: List[str]) -> List[tuple]:
        """Парсинг строк прокси в список кортежей (ip, port, user, password)"""
        proxies = []

        for line in lines:
            try:
                if '@' in line:
                    # Формат: user:password@ip:port
                    auth_part, address_part = line.split('@')
                    user, password = auth_part.split(':')
                    ip, port = address_part.split(':')
                    proxies.append((ip.strip(), int(port.strip()), user.strip(), password.strip()))
                else:
                    # Формат: ip:port:user:password
                    parts = line.split(':')
                    if len(parts) == 4:
                        ip, port, user, password = parts
                        proxies.append((ip.strip(), int(port.strip()), user.strip(), password.strip()))
                    elif len(parts) == 2:
                        # Формат без авторизации: ip:port
                        ip, port = parts
                        proxies.append((ip.strip(), int(port.strip()), None, None))
                    else:
                        self.logger.warning(f"Неверный формат прокси: {line}")
            except Exception as e:
                self.logger.warning(f"Ошибка парсинга прокси '{line}': {e}")

        self.logger.debug(f"Распарсено {len(proxies)} прокси")
        return proxies

    async def _check_proxies_batch_with_failed(
            self,
            proxy_list: List[tuple],
            max_concurrent: int = 20
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Параллельная проверка списка прокси с возвратом и рабочих, и нерабочих

        :return: (working_proxies, failed_proxies)
        """
        # Создаем семафор для ограничения одновременных запросов
        semaphore = asyncio.Semaphore(max_concurrent)

        # Создаем общую сессию для всех запросов
        timeout = aiohttp.ClientTimeout(total=10)

        working_proxies = []
        failed_proxies = []

        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Создаем задачи для всех прокси
            tasks = []
            for ip, port, user, password in proxy_list:
                task = self._check_proxy_with_semaphore_and_info(
                    ip, port, user, password, session, semaphore
                )
                tasks.append(task)

            # Запускаем все задачи параллельно и собираем результаты
            results = await asyncio.gather(*tasks, return_exceptions=True)

        # Обрабатываем результаты
        for result in results:
            if isinstance(result, Exception):
                self.logger.debug(f"Исключение при проверке: {result}")
                continue

            proxy_data = result['proxy']
            if result['working']:
                working_proxies.append(proxy_data)
            else:
                failed_proxies.append(proxy_data)

        return working_proxies, failed_proxies

    async def _check_proxy_with_semaphore_and_info(
            self,
            ip: str,
            port: int,
            user: Optional[str],
            password: Optional[str],
            session: aiohttp.ClientSession,
            semaphore: asyncio.Semaphore
    ) -> Dict:
        """Проверка одного прокси с возвратом информации о результате"""
        async with semaphore:
            try:
                is_working = await self.check_proxy_async(
                    ip=ip,
                    port=port,
                    user=user,
                    password=password,
                    session=session,
                    timeout=5
                )

                proxy_dict = {
                    "server": f"http://{ip}:{port}",
                    "username": user,
                    "password": password
                }

                return {
                    'working': is_working,
                    'proxy': proxy_dict,
                    'ip': ip,
                    'port': port
                }

            except Exception as e:
                self.logger.debug(f"Ошибка при проверке {ip}:{port}: {str(e)[:50]}")
                return {
                    'working': False,
                    'proxy': {
                        "server": f"http://{ip}:{port}",
                        "username": user,
                        "password": password
                    },
                    'ip': ip,
                    'port': port
                }

    def _print_results(self, working_proxies: List[Dict], failed_proxies: List[Dict], elapsed_time: float):
        """Вывод результатов проверки"""
        print(f"\nРабочие прокси ({len(working_proxies)}):")
        for proxy in working_proxies:
            auth_info = f" (с авторизацией)" if proxy['username'] else ""
            print(f"  - {proxy['server']}{auth_info}")
        if self.config.DEBUG == 'True':
            print(f"\n✗ Нерабочие прокси ({len(failed_proxies)}):")
            for proxy in failed_proxies:
                auth_info = f" (с авторизацией)" if proxy['username'] else ""
                print(f"  - {proxy['server']}{auth_info}")

            print(f"\n📊 Статистика:")
            print(f"  Всего проверено: {len(working_proxies) + len(failed_proxies)}")
            print(f"  Рабочих: {len(working_proxies)}")
            print(f"  Нерабочих: {len(failed_proxies)}")
            print(f"  Процент рабочих: {(len(working_proxies) / (len(working_proxies) + len(failed_proxies)) * 100):.1f}%")
            print(f"  Время проверки: {elapsed_time:.2f} секунд")
            print("=" * 50)

    def _save_working_proxies(self, working_proxies: List[Dict]):
        """Сохранение рабочих прокси в файл"""
        if not working_proxies:
            self.logger.warning("Нет рабочих прокси для сохранения")
            return

        # Сохраняем в формате JSON
        json_file = "accepted_proxies.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(working_proxies, f, indent=2, ensure_ascii=False)

        # Сохраняем в текстовом формате (для удобства)
        txt_file = "accepted_proxies.txt"
        with open(txt_file, 'w', encoding='utf-8') as f:
            f.write("# Рабочие прокси\n")
            f.write("# Формат: server:username:password\n")
            f.write("# Если username и password отсутствуют, оставьте пустыми\n")
            f.write("# Пример: http://192.168.1.1:8080:myuser:mypassword\n")
            f.write("# Пример без авторизации: http://192.168.1.1:8080::\n\n")

            for proxy in working_proxies:
                username = proxy['username'] or ''
                password = proxy['password'] or ''
                server = proxy['server']
                f.write(f"{server}:{username}:{password}\n")

        # Также сохраняем в формате для curl (если нужно)
        curl_file = "accepted_proxies_curl.txt"
        with open(curl_file, 'w', encoding='utf-8') as f:
            f.write("# Прокси для curl\n")
            f.write("# Использование: curl -x http://user:pass@ip:port http://example.com\n\n")
            for proxy in working_proxies:
                server = proxy['server'].replace('http://', '')
                if proxy['username'] and proxy['password']:
                    f.write(f"http://{proxy['username']}:{proxy['password']}@{server}\n")
                else:
                    f.write(f"http://{server}\n")

        self.logger.info(f"Рабочие прокси сохранены в файлы:")
        self.logger.info(f"  - {json_file} (JSON формат)")
        self.logger.info(f"  - {txt_file} (текстовый формат)")
        self.logger.info(f"  - {curl_file} (формат для curl)")

    def _save_failed_proxies(self, failed_proxies: List[Dict]):
        """Сохранение нерабочих прокси в файл (опционально)"""
        if not failed_proxies:
            return

        failed_file = "failed_proxies.txt"
        with open(failed_file, 'w', encoding='utf-8') as f:
            f.write("# Нерабочие прокси\n")
            f.write("# Эти прокси не прошли проверку\n\n")

            for proxy in failed_proxies:
                username = proxy['username'] or ''
                password = proxy['password'] or ''
                server = proxy['server']
                f.write(f"{server}:{username}:{password}\n")

        self.logger.info(f"Нерабочие прокси сохранены в {failed_file}")

    async def get_random_proxy(self) -> Optional[Dict]:
        """
        Возвращает случайный рабочий прокси из загруженных

        :return: случайный прокси или None если нет рабочих
        """
        if not hasattr(self, 'working_proxies') or not self.working_proxies:
            # Если прокси еще не загружены, загружаем их
            self.working_proxies = await self.get_proxies()

        if not self.working_proxies:
            return None

        import random
        return random.choice(self.working_proxies)

    def get_proxy_count(self) -> Dict[str, int]:
        """
        Возвращает статистику по прокси

        :return: словарь с количеством рабочих и нерабочих прокси
        """
        working_count = len(self.working_proxies) if hasattr(self, 'working_proxies') else 0
        failed_count = len(self.failed_proxies) if hasattr(self, 'failed_proxies') else 0

        return {
            'working': working_count,
            'failed': failed_count,
            'total': working_count + failed_count
        }
