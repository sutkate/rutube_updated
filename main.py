import traceback
from pathlib import Path

from core.rutube_worker import Rutube
from core.utils.config import config

rutube = Rutube()
rutube.start()

if __name__ == "__main__":
    try:
        print(config.CHROME)

        rutube = Rutube()
        rutube.start()

    except Exception:
        import traceback
        traceback.print_exc()
        input("Ошибка! Нажмите Enter чтобы закрыть...")