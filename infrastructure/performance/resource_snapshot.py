from __future__ import annotations

import logging
import sys
from typing import Any

logger = logging.getLogger("moscraper.performance.resource")


def get_process_memory_mb() -> float | None:
    try:
        import psutil  # type: ignore[import-not-found]

        return float(psutil.Process().memory_info().rss) / (1024.0 * 1024.0)
    except Exception:
        pass
    if sys.platform == "win32":
        logger.debug(
            "performance resource snapshot: limited mode (optional psutil not installed)",
            exc_info=False,
        )
        return None
    try:
        import resource

        ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform == "darwin":
            return float(ru) / (1024.0 * 1024.0)
        return float(ru) / 1024.0
    except Exception:
        logger.debug(
            "performance resource snapshot: limited mode (no psutil / resource RSS)",
            exc_info=False,
        )
    return None


def build_resource_snapshot() -> dict[str, Any]:
    mb = get_process_memory_mb()
    return {
        "process_memory_mb": mb,
        "limited_mode": mb is None,
        "python": sys.version.split()[0],
        "platform": sys.platform,
    }
