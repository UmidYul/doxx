from __future__ import annotations

import re


def compile_patterns(raw: dict[str, list[str]]) -> dict[str, list[re.Pattern[str]]]:
    compiled: dict[str, list[re.Pattern[str]]] = {}
    for field, patterns in raw.items():
        compiled[field] = [re.compile(p, re.IGNORECASE) for p in patterns]
    return compiled


# ═══════════════════════════════════════════════════════════════════════════
# Phone patterns
# ═══════════════════════════════════════════════════════════════════════════

_PHONE_PATTERNS_RAW: dict[str, list[str]] = {
    "ram_gb": [
        r"(?P<value>\d+)\s*(?:GB|ГБ|Гб|гб)\s*(?:RAM|ОЗУ|озу|оперативн)",
        r"(?:RAM|ОЗУ|озу|оперативн\w*)\s*[:=]?\s*(?P<value>\d+)\s*(?:GB|ГБ|Гб|гб)?",
        r"(?P<value>\d+)\s*(?:GB|ГБ|Гб|гб)\s*(?:operativ|xotira)",
        r"(?:operativ\w*\s*xotira|оперативка)\s*[:=\-]?\s*(?P<value>\d+)",
    ],
    "storage_gb": [
        r"(?P<value>\d+)\s*(?:GB|ГБ|Гб|гб)\s*(?:встроен|внутрен|ichki|ROM|ПЗУ)",
        r"(?:встроен\w*\s*памят\w*|ichki\s*xotira|ROM|ПЗУ)\s*[:=]?\s*(?P<value>\d+)\s*(?:GB|ГБ|Гб|гб|TB|ТБ)?",
        r"(?P<value>\d+)\s*(?:TB|ТБ|тб|tb)",
        r"(?:xotira\s*hajmi|объ[её]м\s*памят\w*|storage)\s*[:=]?\s*(?P<value>\d+)\s*(?:GB|ГБ|Гб|гб|TB|ТБ)?",
    ],
    "battery_mah": [
        r"(?P<value>\d{3,5})\s*(?:мАч|mAh|мач|mah)",
        r"(?:аккумулятор|батарея|batareya|battery)\s*[:=]?\s*(?P<value>\d{3,5})\s*(?:мАч|mAh)?",
        r"(?:ёмкость|емкость|sig['\u2019]?imi)\s*[:=]?\s*(?P<value>\d{3,5})",
        r"(?:battery\s*capacity|batareya\s*sig['\u2019]?imi)\s*[:=]?\s*(?P<value>\d{3,5})",
    ],
    "display_size_inch": [
        r"""(?P<value>\d+[.,]\d+)\s*(?:дюйм\w*|inch\w*|"|″)""",
        r"(?:экран|ekran|display|диагональ\w*)\s*[:=]?\s*(?P<value>\d+[.,]\d+)",
        r"(?P<value>\d+[.,]\d+\s*(?:см|cm))",
        r"""(?:screen\s*size|ekran\s*o['\u2019]?lchami)\s*[:=]?\s*(?P<value>\d+[.,]\d+)""",
    ],
    "processor": [
        r"(?:процессор|protsessor|chipset|CPU)\s*[:=]?\s*(?P<value>[A-Za-zА-Яа-яёЁ0-9][\w\s\+\-\.]*\d\w*)",
        r"(?P<value>Snapdragon\s*\d+[\w\s\+]*)",
        r"(?P<value>Dimensity\s*\d+[\w\s]*)",
        r"(?P<value>(?:Apple\s*)?A\d{2}\s*(?:Bionic|Pro)?)",
        r"(?P<value>(?:Samsung\s*)?Exynos\s*\d+)",
        r"(?P<value>Helio\s*[A-Z]\d+)",
    ],
    "main_camera_mp": [
        r"(?:основн\w*\s*камер\w*|asosiy\s*kamera|rear\s*camera|задн\w*\s*камер\w*)\s*[:=]?\s*(?P<value>\d+)\s*(?:Мп|MP)?",
        r"(?P<value>\d+)\s*(?:Мп|MP|Mp|мп)\s*(?:основн\w*|asosiy|rear|задн\w*|главн\w*)",
        r"(?P<value>\d+)\s*(?:Мп|MP|Mp|мп)\s*(?:\+\s*\d+\s*(?:Мп|MP))+",
        r"(?:camera|kamera)\s*[:=]?\s*(?P<value>\d+)\s*(?:Мп|MP|Mp|мп)",
    ],
    "front_camera_mp": [
        r"(?:фронтальн\w*|передн\w*|front|old|selfi)\s*[:=]?\s*(?:камер\w*|kamera|camera)?\s*[:=]?\s*(?P<value>\d+)\s*(?:Мп|MP)?",
        r"(?P<value>\d+)\s*(?:Мп|MP|Mp)\s*(?:фронтальн|передн|front|old|selfi)",
        r"(?:old\s*kamera|front\s*camera)\s*[:=]?\s*(?P<value>\d+)",
        r"(?:selfi|selfie)\s*[:=]?\s*(?P<value>\d+)\s*(?:Мп|MP)?",
    ],
    "display_type": [
        r"(?P<value>(?:Dynamic\s*)?AMOLED\s*2X?)",
        r"(?P<value>(?:Super\s*)?AMOLED)",
        r"(?P<value>(?:Super\s*)?IPS(?:\s*LCD)?)",
        r"(?P<value>OLED)",
        r"(?P<value>TFT(?:\s*LCD)?)",
        r"(?P<value>Retina(?:\s*XDR)?)",
    ],
    "os": [
        r"(?P<value>Android\s*\d+\.?\d*)",
        r"(?P<value>iOS\s*\d+\.?\d*)",
        r"(?P<value>HarmonyOS\s*\d*\.?\d*)",
        r"(?:ОС|операционн\w*\s*систем\w*|OS|operatsion\s*tizim)\s*[:=]?\s*(?P<value>[A-Za-z]+\s*\d*\.?\d*)",
    ],
    "nfc": [
        r"(?P<value>NFC)\s*(?:есть|бор|mavjud|да|yes|✓|поддерж\w*)",
        r"(?:NFC)\s*[:=]?\s*(?P<value>есть|бор|mavjud|да|yes|Да|Ха)",
        r"(?P<value>NFC)\s*[:=\s]",
        r"(?P<value>NFC)",
    ],
    "sim_count": [
        r"(?P<value>[1234])\s*(?:SIM|сим|sim)",
        r"(?P<value>Dual|dual|Икки|ikki|два|2)\s*SIM",
        r"(?:nano-?SIM|Nano-?SIM)\s*x\s*(?P<value>[12])",
        r"(?:SIM\s*(?:kartalar|карт)\w*\s*(?:soni|количеств\w*))\s*[:=]?\s*(?P<value>[1234])",
    ],
    "weight_g": [
        r"(?P<value>\d{2,3})\s*(?:г(?!б|Б)|g(?!b|B))\b",
        r"(?:вес|og['\u2019]?irlig\w*|weight)\s*[:=]?\s*(?P<value>\d{2,3})\s*(?:г(?!б)|g(?!b))?",
        r"(?:масса|massa)\s*[:=]?\s*(?P<value>\d{2,3})\s*(?:г|g)",
        r"(?P<value>\d+[.,]\d+)\s*(?:кг|kg)",
    ],
}


# ═══════════════════════════════════════════════════════════════════════════
# Laptop patterns
# ═══════════════════════════════════════════════════════════════════════════

_LAPTOP_PATTERNS_RAW: dict[str, list[str]] = {
    "ram_gb": [
        r"(?P<value>\d+)\s*(?:GB|ГБ|Гб|гб)\s*(?:RAM|ОЗУ|DDR\d?|оперативн|LPDDR)",
        r"(?:RAM|ОЗУ|оперативн\w*)\s*[:=]?\s*(?P<value>\d+)\s*(?:GB|ГБ)?",
        r"(?P<value>\d+)\s*(?:GB|ГБ)\s*(?:DDR[45]\w*|LPDDR[45]x?)",
        r"(?:operativ\w*\s*xotira)\s*[:=]?\s*(?P<value>\d+)",
    ],
    "storage_gb": [
        r"(?P<value>\d+)\s*(?:GB|ГБ|TB|ТБ)\s*(?:SSD|HDD|NVMe|накопител|storage)",
        r"(?:SSD|HDD|NVMe|накопител\w*|ichki\s*xotira)\s*[:=]?\s*(?P<value>\d+)\s*(?:GB|ГБ|TB|ТБ)?",
        r"(?P<value>\d+)\s*(?:GB|ГБ|TB|ТБ)\s*(?:встроен|внутрен|PCIe)",
        r"(?:storage|xotira\s*hajmi)\s*[:=]?\s*(?P<value>\d+)\s*(?:GB|ГБ|TB|ТБ)?",
    ],
    "processor": [
        r"(?:процессор|protsessor|CPU)\s*[:=]?\s*(?P<value>(?:Intel|AMD|Apple)\s*[\w\s\-\+]+\d\w*)",
        r"(?P<value>(?:Intel\s*)?Core\s*i[3579]\s*[-\s]?\d{4,5}\w*)",
        r"(?P<value>(?:AMD\s*)?Ryzen\s*[3579]\s*\d{4}\w*)",
        r"(?P<value>Apple\s*M[1234]\s*(?:Pro|Max|Ultra)?)",
    ],
    "display_size_inch": [
        r"""(?P<value>\d+(?:[.,]\d+)?)\s*(?:дюйм\w*|inch\w*|"|″)""",
        r"(?:экран|ekran|display|диагональ)\s*[:=]?\s*(?P<value>\d+(?:[.,]\d+)?)",
        r"""(?:screen\s*size)\s*[:=]?\s*(?P<value>\d+(?:[.,]\d+)?)""",
        r"(?P<value>\d+(?:[.,]\d+)?)\s*(?:см|cm)",
    ],
    "gpu": [
        r"(?:видеокарт\w*|GPU|график\w*|graphics)\s*[:=]?\s*(?P<value>(?:NVIDIA|AMD|Intel|GeForce|Radeon)\s*[\w\s\-]+\d\w*)",
        r"(?P<value>(?:GeForce\s*)?(?:RTX|GTX)\s*\d{4}\w*(?:\s*Ti)?)",
        r"(?P<value>Radeon\s*\w+\s*\d+\w*)",
        r"(?P<value>Intel\s*(?:Iris|UHD|Arc)\s*\w*\s*\d*)",
    ],
    "os": [
        r"(?P<value>Windows\s*1[0-4]\s*(?:Home|Pro)?)",
        r"(?P<value>macOS\s*\w*)",
        r"(?P<value>Ubuntu\s*\d*\.?\d*)",
        r"(?P<value>Chrome\s*OS|Linux|FreeDOS|Без\s*ОС|DOS)",
    ],
    "storage_type": [
        r"(?P<value>(?:PCIe\s*)?NVMe\s*SSD)",
        r"(?P<value>SSD\s*\+\s*HDD)",
        r"(?P<value>SSD)",
        r"(?P<value>HDD)",
        r"(?:тип\s*накопител\w*|storage\s*type|xotira\s*turi)\s*[:=]?\s*(?P<value>SSD|HDD|NVMe|eMMC)",
    ],
    "battery_wh": [
        r"(?P<value>\d+[.,]?\d*)\s*(?:Вт\s*[·*⋅]?\s*ч|Wh|wh|Втч)",
        r"(?:аккумулятор|батарея|battery|batareya)\s*[:=]?\s*(?P<value>\d+[.,]?\d*)\s*(?:Вт\s*[·*⋅]?\s*ч|Wh)?",
        r"(?:ёмкость|емкость|capacity)\s*[:=]?\s*(?P<value>\d+[.,]?\d*)\s*(?:Вт\s*[·*⋅]?\s*ч|Wh)",
        r"(?P<value>\d+[.,]?\d*)\s*(?:Вт\s*ч|Wh)\s*(?:батарея|battery|аккумулятор)?",
    ],
    "weight_kg": [
        r"(?P<value>\d+[.,]\d+)\s*(?:кг|kg)",
        r"(?:вес|og['\u2019]?irlig\w*|weight)\s*[:=]?\s*(?P<value>\d+[.,]\d+)\s*(?:кг|kg)?",
        r"(?:масса|massa)\s*[:=]?\s*(?P<value>\d+[.,]\d+)\s*(?:кг|kg)?",
        r"(?P<value>\d{3,4})\s*(?:г(?!б)|g(?!b))\b",
    ],
    "usb_c_count": [
        r"(?P<value>\d)\s*[xх×]\s*(?:USB[\s-]*(?:Type[\s-]*)?C|USB-C)",
        r"(?:USB[\s-]*(?:Type[\s-]*)?C|USB-C)\s*[xх×]\s*(?P<value>\d)",
        r"(?:USB[\s-]*(?:Type[\s-]*)?C|USB-C)\s*[:=]?\s*(?P<value>\d)\s*(?:шт|порт|port)?",
        r"(?P<value>\d)\s*(?:порт\w*|port\w*)\s*USB[\s-]*(?:Type[\s-]*)?C",
    ],
}


# ═══════════════════════════════════════════════════════════════════════════
# TV patterns
# ═══════════════════════════════════════════════════════════════════════════

_TV_PATTERNS_RAW: dict[str, list[str]] = {
    "display_size_inch": [
        r"""(?P<value>\d+)\s*(?:дюйм\w*|inch\w*|"|″)""",
        r"(?:экран|ekran|display|диагональ)\s*[:=]?\s*(?P<value>\d+)",
        r"""(?:screen\s*size|ekran\s*o['\u2019]?lchami)\s*[:=]?\s*(?P<value>\d+)""",
        r"(?P<value>\d+)\s*(?:см|cm)",
    ],
    "resolution": [
        r"(?P<value>3840\s*[xх×]\s*2160|4K\s*(?:UHD|Ultra\s*HD)?)",
        r"(?P<value>1920\s*[xх×]\s*1080|Full\s*HD|FHD)",
        r"(?P<value>7680\s*[xх×]\s*4320|8K(?:\s*UHD)?)",
        r"(?P<value>1366\s*[xх×]\s*768|HD\s*Ready|HD)",
        r"(?:разрешени\w*|resolution|ruxsat)\s*[:=]?\s*(?P<value>\d+\s*[xх×]\s*\d+|\w+\s*HD\w*|[48]K)",
    ],
    "display_tech": [
        r"(?P<value>Neo\s*QLED)",
        r"(?P<value>Mini\s*LED)",
        r"(?P<value>QLED)",
        r"(?P<value>OLED)",
        r"(?P<value>Nano\s*Cell)",
        r"(?P<value>(?:Direct\s*)?LED)",
        r"(?:технологи\w*|texnologiya|тип\s*матриц\w*)\s*[:=]?\s*(?P<value>QLED|OLED|LED|Mini\s*LED|IPS|VA)",
    ],
    "refresh_rate_hz": [
        r"(?P<value>\d+)\s*(?:Гц|Hz|гц|hz|герц)",
        r"(?:частота\s*обновлени\w*|refresh\s*rate|yangilanish\s*chastotasi)\s*[:=]?\s*(?P<value>\d+)\s*(?:Гц|Hz)?",
        r"(?:chastota|частота)\s*[:=]?\s*(?P<value>\d+)\s*(?:Гц|Hz)?",
        r"(?P<value>\d+)\s*(?:Гц|Hz)\s*(?:обновлени\w*|refresh)?",
    ],
    "smart_tv": [
        r"(?P<value>Smart\s*TV)",
        r"(?P<value>Android\s*TV)",
        r"(?P<value>Tizen(?:\s*\d+\.?\d*)?)",
        r"(?P<value>webOS(?:\s*\d+\.?\d*)?)",
        r"(?P<value>Vidaa)",
        r"(?P<value>Google\s*TV)",
    ],
    "has_wifi": [
        r"(?P<value>Wi-?Fi(?:\s*\d)?)",
        r"(?P<value>WiFi)",
        r"(?P<value>802\.11\w*)",
        r"(?:беспроводн\w*|wireless)\s*[:=]?\s*(?P<value>Wi-?Fi|WiFi|есть|да|yes)",
    ],
    "hdmi_count": [
        r"HDMI\s*[xх×]\s*(?P<value>\d)",
        r"(?P<value>\d)\s*[xх×]\s*HDMI",
        r"HDMI\s*[:=]?\s*(?P<value>\d)\s*(?:шт|порт|port)?",
        r"(?P<value>\d)\s*(?:порт\w*|port\w*)\s*HDMI",
    ],
}


# ═══════════════════════════════════════════════════════════════════════════
# Compiled pattern dicts (module-level singletons)
# ═══════════════════════════════════════════════════════════════════════════

PHONE_PATTERNS: dict[str, list[re.Pattern[str]]] = compile_patterns(_PHONE_PATTERNS_RAW)
LAPTOP_PATTERNS: dict[str, list[re.Pattern[str]]] = compile_patterns(_LAPTOP_PATTERNS_RAW)
TV_PATTERNS: dict[str, list[re.Pattern[str]]] = compile_patterns(_TV_PATTERNS_RAW)
