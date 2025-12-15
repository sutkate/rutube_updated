import random
import string
from datetime import datetime

# =========================
# BASE DATA
# =========================

PLATFORMS = ["Win64", "MacIntel", "Linux", "Win32"]
PLATFORM_WEIGHTS = [55, 20, 20, 5]

CHROME_MAJOR_VERSIONS = [128, 129, 130, 131]
CHROME_BUILD_RANGES = {
    128: (6610, 6640),
    129: (6650, 6690),
    130: (6700, 6750),
    131: (6760, 6790),
}

WINDOWS_NT = ["10.0"]
MAC_OS_VERSIONS = ["10_15_7", "11_7_10", "12_7_1", "13_6_1"]

# =========================
# SCREENS / VIEWPORTS
# =========================

SCREENS = {
    "Win64": [(1920,1080),(1366,768),(1536,864),(1600,900),(1440,900),(2560,1440),(3840,2160)],
    "MacIntel": [(2560,1600),(2880,1800),(3072,1920),(1920,1200),(1680,1050)],
    "Linux": [(1920,1080),(1366,768),(1600,900),(1440,900),(1280,800)],
    "Win32": [(1366,768),(1280,720)],
}

VIEWPORT_OFFSETS = [(0, 40), (0, 60), (0, 80), (0, 100)]

PIXEL_RATIOS = {
    "Win64": [1, 1.25, 1.5],
    "MacIntel": [2],
    "Linux": [1, 1.25],
    "Win32": [1],
}

# =========================
# WEBGL
# =========================

WEBGL = {
    "Win64": [
        ("Google Inc.", "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0)"),
        ("Google Inc.", "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0)"),
    ],
    "MacIntel": [
        ("Apple Inc.", "Intel Iris OpenGL Engine"),
        ("Apple Inc.", "Apple M1"),
    ],
    "Linux": [
        ("Google Inc.", "ANGLE (Intel, Mesa Intel(R) UHD Graphics 620)"),
    ],
    "Win32": [
        ("Google Inc.", "ANGLE (Intel, Intel HD Graphics 4000 Direct3D11 vs_5_0 ps_5_0)"),
    ],
}

# =========================
# LOCALES / TIMEZONES
# =========================

REGIONS = [
    (["ru-RU","ru"], ["Europe/Moscow","Europe/Samara","Asia/Yekaterinburg"]),
    (["en-US","en"], ["America/New_York","America/Chicago","America/Los_Angeles"]),
    (["en-GB"], ["Europe/London"]),
    (["de-DE"], ["Europe/Berlin"]),
    (["fr-FR"], ["Europe/Paris"]),
    (["pl-PL"], ["Europe/Warsaw"]),
    (["tr-TR"], ["Europe/Istanbul"]),
    (["es-ES"], ["Europe/Madrid"]),
    (["it-IT"], ["Europe/Rome"]),
]

# =========================
# HARDWARE
# =========================

HARDWARE_PROFILES = [
    {"hw":2,"mem":4,"w":8},
    {"hw":4,"mem":4,"w":22},
    {"hw":4,"mem":8,"w":20},
    {"hw":6,"mem":8,"w":20},
    {"hw":8,"mem":16,"w":18},
    {"hw":12,"mem":32,"w":8},
    {"hw":16,"mem":32,"w":4},
]

CPU_ARCH = "x86_64"
ENDIANNESS = "little"

# =========================
# HELPERS
# =========================

def _weighted(items, weights):
    return random.choices(items, weights=weights, k=1)[0]

def _chrome_ua(platform: str) -> str:
    major = random.choice(CHROME_MAJOR_VERSIONS)
    build = random.randint(*CHROME_BUILD_RANGES[major])
    patch = random.randint(0, 150)

    if platform.startswith("Win"):
        arch = "Win64; x64" if platform == "Win64" else "Win32; x86"
        return (
            f"Mozilla/5.0 (Windows NT 10.0; {arch}) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{major}.0.{build}.{patch} Safari/537.36"
        )

    if platform == "MacIntel":
        osx = random.choice(MAC_OS_VERSIONS)
        return (
            f"Mozilla/5.0 (Macintosh; Intel Mac OS X {osx}) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{major}.0.{build}.{patch} Safari/537.36"
        )

    return (
        f"Mozilla/5.0 (X11; Linux x86_64) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{major}.0.{build}.{patch} Safari/537.36"
    )

def _screen(platform):
    sw, sh = random.choice(SCREENS[platform])
    _, off_h = random.choice(VIEWPORT_OFFSETS)
    vw = sw
    vh = max(400, sh - off_h)
    dpr = random.choice(PIXEL_RATIOS[platform])
    return sw, sh, vw, vh, dpr

def _locale_timezone():
    langs, tzs = random.choice(REGIONS)
    lang = langs[0]
    tz = random.choice(tzs)
    return lang, langs, tz

def _hardware():
    p = _weighted(HARDWARE_PROFILES, [x["w"] for x in HARDWARE_PROFILES])
    return p["hw"], p["mem"]

def _noise(n1=64, n2=180):
    chars = string.ascii_letters + string.digits
    return "".join(random.choices(chars, k=random.randint(n1, n2)))

# =========================
# PUBLIC
# =========================

def generate_fingerprint(seed: int | None = None) -> dict:
    if seed is not None:
        random.seed(seed)

    platform = _weighted(PLATFORMS, PLATFORM_WEIGHTS)
    ua = _chrome_ua(platform)
    sw, sh, vw, vh, dpr = _screen(platform)
    gl_vendor, gl_renderer = random.choice(WEBGL[platform])
    lang, langs, tz = _locale_timezone()
    hw, mem = _hardware()

    return {
        # core
        "user_agent": ua,
        "platform": platform,
        "vendor": "Google Inc.",
        "product": "WebKit",

        # screen
        "screen_width": sw,
        "screen_height": sh,
        "viewport_width": vw,
        "viewport_height": vh,
        "device_pixel_ratio": dpr,
        "color_depth": 24,

        # locale
        "language": lang,
        "languages": langs,
        "timezone": tz,  # ← использовать напрямую в Playwright

        # webgl
        "webgl_vendor": gl_vendor,
        "webgl_renderer": gl_renderer,

        # hardware
        "hardware_concurrency": hw,
        "device_memory": mem,
        "cpu_architecture": CPU_ARCH,
        "endianness": ENDIANNESS,

        # prefs
        "prefers_reduced_motion": random.choice([False, False, False, True]),
        "color_gamut": random.choice(["srgb", "p3"]),
        "forced_colors": False,
        "do_not_track": random.choices([None,"0","1"], [70,25,5])[0],

        # noise
        "canvas_noise": _noise(),
        "audio_noise": _noise(32,64),

        # meta
        "fingerprint_version": "C-2.1",
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
