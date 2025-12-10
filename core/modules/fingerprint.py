import random
import string
from datetime import datetime, timezone
try:
    from zoneinfo import ZoneInfo
except Exception:
    # fallback for very old pythons (unlikely); prefer Python 3.9+
    from backports.zoneinfo import ZoneInfo  # type: ignore

# ----- вспомогательные данные -----

# User-Agent'ы сгруппированы по платформам — это гарантирует согласованность:
USER_AGENTS_BY_PLATFORM = {
    "Win64": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
        "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ],
    "Win32": [
        # Rare for modern desktops, but keep for variety
        "Mozilla/5.0 (Windows NT 10.0; Win32; x86) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
    ],
    "MacIntel": [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7; rv:131.0) Gecko/20100101 Firefox/131.0"
    ],
    "Linux": [
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0"
    ],
}

# Разрешения экранов по типам устройств (часто встречающиеся)
SCREEN_RESOLUTIONS_BY_PLATFORM = {
    "Win64": [(1920, 1080), (1366, 768), (1536, 864), (2560, 1440), (3840, 2160), (1440, 900)],
    "MacIntel": [(2560, 1600), (2880, 1800), (1920, 1200), (1680, 1050)],
    "Linux": [(1920, 1080), (1366, 768), (1600, 900)],
    "Win32": [(1280, 720), (1366, 768)]
}

# Типичные viewports (не превышают screen)
VIEWPORT_VARIANTS = [
    (1920, 1040), (1366, 658), (1536, 744), (1440, 780),
    (1280, 600), (1600, 900), (1280, 720), (2560, 1380)
]

# WebGL vendors/renderers по платформам — без искусственного шума внутри renderer
WEBGL_BY_PLATFORM = {
    "Win64": [
        ("Google Inc.", "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0)"),
        ("Intel Inc.", "Intel(R) UHD Graphics 630"),
        ("NVIDIA Corporation", "NVIDIA GeForce GTX 1660 Ti")
    ],
    "MacIntel": [
        ("Apple Inc.", "Apple M1"),
        ("Apple Inc.", "Intel Iris OpenGL Engine")
    ],
    "Linux": [
        ("Google Inc.", "ANGLE (Intel, Intel(R) UHD Graphics 600)"),
        ("Intel Inc.", "Mesa DRI Intel(R) UHD Graphics")
    ],
    "Win32": [
        ("Intel Inc.", "Intel HD Graphics")
    ]
}

# Локали и часовые пояса с логикой связи (чтобы locale → timezone был правдоподобным)
REGION_LOCALES_TIMEZONES = [
    # (locales, timezones)
    (["ru-RU", "ru"], ["Europe/Moscow", "Europe/Samara", "Asia/Yekaterinburg"]),
    (["uk-UA", "uk"], ["Europe/Kiev", "Europe/Zaporozhye"]),  # note: aliases OK
    (["en-US", "en"], ["America/New_York", "America/Los_Angeles", "America/Chicago", "America/Denver"]),
    (["en-GB"], ["Europe/London"]),
    (["be-BY"], ["Europe/Minsk"]),
    (["kk-KZ"], ["Asia/Almaty", "Asia/Oral"]),
    (["tr-TR", "tr"], ["Europe/Istanbul"]),
    (["de-DE"], ["Europe/Berlin"]),
]

# Возможные hardware profiles (weights)
HARDWARE_PROFILES = [
    {"hw": 4, "mem": 4, "weight": 30},   # бюджетные ноуты / старые десктопы
    {"hw": 6, "mem": 8, "weight": 30},   # обычные ноуты
    {"hw": 8, "mem": 16, "weight": 25},  # средний ПК
    {"hw": 12, "mem": 32, "weight": 10}, # мощные рабочие станции
    {"hw": 16, "mem": 32, "weight": 5},  # топовые десктопы
]

# ----- вспомогательные функции -----

def _choose_platform():
    # даём приоритет Windows, затем mac, затем linux
    platforms = ["Win64", "MacIntel", "Linux", "Win32"]
    weights = [55, 20, 20, 5]
    return random.choices(platforms, weights=weights, k=1)[0]

def _pick_user_agent(platform):
    ualist = USER_AGENTS_BY_PLATFORM.get(platform, USER_AGENTS_BY_PLATFORM["Win64"])
    return random.choice(ualist)

def _pick_screen_and_viewport(platform):
    screens = SCREEN_RESOLUTIONS_BY_PLATFORM.get(platform, SCREEN_RESOLUTIONS_BY_PLATFORM["Win64"])
    screen_w, screen_h = random.choice(screens)
    # viewport не больше экрана; небольшой рандом в пределах
    possible_viewports = [v for v in VIEWPORT_VARIANTS if v[0] <= screen_w and v[1] <= screen_h]
    if not possible_viewports:
        vp_w = max(800, screen_w - random.randint(0, 200))
        vp_h = max(600, screen_h - random.randint(0, 200))
        return (screen_w, screen_h, vp_w, vp_h)
    vp_w, vp_h = random.choice(possible_viewports)
    # иногда уменьшить viewport height как будто есть taskbar/devtools
    if random.random() < 0.35:
        vp_h = max( vp_h - random.randint(24, 120), 400 )
    return (screen_w, screen_h, vp_w, vp_h)

def _pick_webgl(platform):
    candidates = WEBGL_BY_PLATFORM.get(platform, WEBGL_BY_PLATFORM["Win64"])
    vendor, renderer = random.choice(candidates)
    return vendor, renderer

def _pick_locale_and_tz():
    # выберем пару (locales, timezone) правдоподобно
    group = random.choice(REGION_LOCALES_TIMEZONES)
    locales_group = group[0]
    tz_group = group[1]
    primary_locale = random.choice(locales_group)
    # build languages list with realistic fallback order
    languages = [primary_locale]
    if primary_locale != "en-US":
        languages.append("en-US")
    languages.append("en")
    timezone_choice = random.choice(tz_group)
    return primary_locale, languages, timezone_choice

def _timezone_offset_minutes(tz_name):
    try:
        tz = ZoneInfo(tz_name)
        now = datetime.now(tz)
        offset = now.utcoffset()
        if offset is None:
            return 0
        return int(offset.total_seconds() // 60)
    except Exception:
        # fallback: 0
        return 0

def _canvas_noise(min_len=60, max_len=180):
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()_+-=[]{};:,.<>/?"
    return ''.join(random.choices(chars, k=random.randint(min_len, max_len)))

def _audio_noise_hex(length=32):
    return ''.join(random.choices("0123456789abcdef", k=length))

def _pick_hardware_profile():
    weights = [p["weight"] for p in HARDWARE_PROFILES]
    prof = random.choices(HARDWARE_PROFILES, weights=weights, k=1)[0]
    return prof["hw"], prof["mem"]

def _pick_do_not_track():
    # realistic distribution: most users have DNT disabled, minority enabled
    return random.choices(["1", "0", None], weights=[8, 85, 7], k=1)[0]

# ----- публичная функция -----

def generate_fingerprint(seed: int | None = None) -> dict:
    """
    Возвращает реалистичный fingerprint (Variant B).
    Если передан seed — генерация станет детерминированной.
    """
    if seed is not None:
        random.seed(seed)

    platform = _choose_platform()
    user_agent = _pick_user_agent(platform)
    ua_platform_map = {
        "Win64": "Win64",
        "Win32": "Win32",
        "MacIntel": "MacIntel",
        "Linux": "Linux"
    }
    platform_field = ua_platform_map.get(platform, "Win64")

    screen_w, screen_h, vp_w, vp_h = _pick_screen_and_viewport(platform)
    webgl_vendor, webgl_renderer = _pick_webgl(platform)

    locale, languages, timezone_name = _pick_locale_and_tz()
    tz_offset = _timezone_offset_minutes(timezone_name)

    hw_concurrency, device_memory = _pick_hardware_profile()

    fingerprint = {
        # browser / platform
        "user_agent": user_agent,
        "platform": platform_field,
        "product": "Gecko" if "Firefox" in user_agent else "WebKit",
        "vendor": "Google Inc." if "Chrome" in user_agent else ("Apple Inc." if "Safari" in user_agent else ""),

        # screen & viewport
        "screen_width": screen_w,
        "screen_height": screen_h,
        "viewport_width": vp_w,
        "viewport_height": vp_h,
        "color_depth": random.choice([24, 30, 32]),
        "pixel_ratio": random.choice([1, 1.25, 1.5, 2]),

        # locale / timezone
        "language": locale,
        "languages": languages,
        "timezone": timezone_name,
        "timezone_offset": tz_offset,  # minutes

        # webgl / canvas / audio
        "webgl_vendor": webgl_vendor,
        "webgl_renderer": webgl_renderer,
        "canvas_noise": _canvas_noise(),
        "audio_context_noise": _audio_noise_hex(32),

        # hardware
        "hardware_concurrency": hw_concurrency,
        "device_memory": device_memory,
        "touch_support": random.choices([False, True], weights=[85, 15], k=1)[0],
        "do_not_track": _pick_do_not_track(),

        # extras for convenience
        "fingerprint_version": "B-1.0",
        "generated_at": datetime.utcnow().isoformat() + "Z"
    }

    return fingerprint

# ----- дополнительные утилиты -----

def generate_many(n: int, seed: int | None = None):
    """Генерирует список fingerprint'ов"""
    res = []
    base = seed if seed is not None else random.randrange(1 << 30)
    for i in range(n):
        res.append(generate_fingerprint(seed=(base + i)))
    return res
