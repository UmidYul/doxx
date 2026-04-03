#!/usr/bin/env python3
"""
Короткий прогон паука с реальной отправкой в CRM (HTTP batch sync).

Перед запуском:
  1) Скопируйте .env.example → .env и заполните CRM_BASE_URL, CRM_PARSER_KEY (как в CRM).
  2) CRM на localhost: добавьте в .env ENABLE_LOCALHOST_BLOCK=false **или** передайте
     флаг --allow-localhost-crm (только для локальной отладки).
  3) Скрипт принудительно ставит DEV_MODE=false для процесса Scrapy, чтобы не сработал
     DryRunTransport (см. infrastructure/transports/factory.py).
  4) В STORE_NAMES должны быть все магазины, которые крутите (см. .env.example).

Примеры:
  python scripts/crm_short_crawl.py --store mediapark --items 15
  python scripts/crm_short_crawl.py --store uzum --items 10 --allow-localhost-crm

Что дальше для «много товаров, цены, характеристики, фото»:
  - Объём: поднять лимиты краула (SCRAPY_MAX_PAGES_PER_CATEGORY), больше стартовых
    категорий в пауке, cron/K8s CronJob с длительным таймаутом.
  - Качество полей: уже уходят в CRM нормализованный payload (цена, raw_specs,
    image_urls); досмотреть anti-bot (прокси, лимиты browser в store_resource_budgets).
  - Проверка БД: после успешного apply смотрите ответы CRM / логи crm_applied_total и
    таблицы на стороне CRM (парсер шлёт batch на CRM_SYNC_BATCH_ENDPOINT).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Short Scrapy crawl with CRM publish enabled.")
    parser.add_argument(
        "--store",
        choices=("mediapark", "uzum", "texnomart"),
        default="mediapark",
        help="Spider name",
    )
    parser.add_argument("--items", type=int, default=15, help="CLOSESPIDER_ITEMCOUNT")
    parser.add_argument("--timeout", type=int, default=240, help="CLOSESPIDER_TIMEOUT seconds")
    parser.add_argument(
        "--allow-localhost-crm",
        action="store_true",
        help="Set ENABLE_LOCALHOST_BLOCK=false for this run (local CRM on 127.0.0.1 only).",
    )
    args = parser.parse_args()

    env = os.environ.copy()
    env["MOSCRAPER_DISABLE_PUBLISH"] = "0"
    env["DEV_MODE"] = "false"
    env.setdefault("TRANSPORT_TYPE", "crm_http")
    if args.allow_localhost_crm:
        env["ENABLE_LOCALHOST_BLOCK"] = "false"
        # Loopback IPs are otherwise rejected as private (127.0.0.1).
        env.setdefault("ENABLE_PRIVATE_IP_BLOCK", "false")

    root = _repo_root()
    cmd = [
        sys.executable,
        "-m",
        "scrapy",
        "crawl",
        args.store,
        "-s",
        f"CLOSESPIDER_ITEMCOUNT={args.items}",
        "-s",
        f"CLOSESPIDER_TIMEOUT={args.timeout}",
        "-s",
        "LOG_LEVEL=INFO",
    ]
    print("Running:", " ".join(cmd), file=sys.stderr)
    print(
        "MOSCRAPER_DISABLE_PUBLISH=0 DEV_MODE=false (real CRM HTTP if CRM_BASE_URL + key are valid)",
        file=sys.stderr,
    )
    if args.allow_localhost_crm:
        print("ENABLE_LOCALHOST_BLOCK=false for this process only.", file=sys.stderr)

    p = subprocess.run(cmd, cwd=root, env=env)
    return int(p.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
