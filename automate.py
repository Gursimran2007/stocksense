#!/usr/bin/env python3
"""Automated sync job — run by launchd/cron on a schedule.

For each enabled POS connector it: pulls new sales/stock, writes them into the
normalized DB, then regenerates the plain-language 'Buy today' report.
Idempotent: the inbox connector archives processed files; per-provider last-sync
is tracked in state.json.

Run manually:   python automate.py
With config:    python automate.py --config automation.json
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core import db
from core.adapters.pos import REGISTRY
from core.report import generate
from core.notify import send_report

CONFIG_PATH = ROOT / "automation.json"
STATE_PATH = ROOT / "state.json"
LOG_PATH = ROOT / "automation.log"

DEFAULT_CONFIG = {
    "providers": [
        {"name": "inbox", "enabled": True, "credentials": {"folder": "inbox"}},
        {"name": "tally", "enabled": False,
         "credentials": {"url": "http://localhost:9000"}},
        {"name": "vyapar", "enabled": False, "credentials": {}}
    ],
    "cash_cap": None,                # ₹ budget the daily report plans within; null = buy-all
    "report_dir": "reports",
    "notify": {
        "macos": {"enabled": True},  # desktop popup, works today
        "email": {"enabled": False, "host": "smtp.gmail.com", "port": 587,
                  "user": "", "password": "", "from": "", "to": ""},
        "whatsapp": {"enabled": False}   # stub — needs a paid provider
    }
}


def load_json(path, default):
    if Path(path).exists():
        return json.loads(Path(path).read_text())
    return default


def save_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2))


def log(msg):
    line = f"{datetime.now().isoformat(timespec='seconds')}  {msg}"
    print(line)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run(config):
    db.init_db()
    state = load_json(STATE_PATH, {})
    totals = {"products": 0, "sales": 0, "inventory": 0}

    for prov in config.get("providers", []):
        name = prov["name"]
        if not prov.get("enabled"):
            continue
        cls = REGISTRY.get(name)
        if not cls:
            log(f"[{name}] unknown provider, skipping"); continue
        conn = cls(prov.get("credentials", {}))
        # resolve inbox folder relative to project root
        if name == "inbox":
            folder = Path(prov.get("credentials", {}).get("folder", "inbox"))
            if not folder.is_absolute():
                conn.folder = ROOT / folder
        try:
            since = state.get(name)
            batch = conn.sync(since=since)
        except NotImplementedError as e:
            log(f"[{name}] not active: {e}"); continue
        except Exception as e:
            log(f"[{name}] ERROR: {e}"); continue

        if batch.products:
            db.upsert_products(batch.products)
        if batch.sales:
            db.insert_sales(batch.sales)
        if batch.inventory:
            db.upsert_inventory(batch.inventory)
        if batch.suppliers:
            db.upsert_suppliers(batch.suppliers)
        for w in batch.warnings:
            log(f"[{name}] {w}")

        totals["products"] += len(batch.products)
        totals["sales"] += len(batch.sales)
        totals["inventory"] += len(batch.inventory)
        state[name] = datetime.now().isoformat()
        log(f"[{name}] synced: {len(batch.products)} items, "
            f"{len(batch.sales)} sales, {len(batch.inventory)} stock")

    save_json(STATE_PATH, state)

    report_dir = ROOT / config.get("report_dir", "reports")
    res = generate(report_dir, cash_cap=config.get("cash_cap"))
    log(f"report written: {res['buy_count']} items to buy "
        f"(cash_cap={config.get('cash_cap')}) -> {report_dir}/buy_today.txt")
    for status in send_report(res, config):
        log(f"notify -> {status}")
    return totals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(CONFIG_PATH))
    ap.add_argument("--init", action="store_true",
                    help="write a default automation.json and exit")
    args = ap.parse_args()

    if args.init or not Path(args.config).exists():
        save_json(args.config, DEFAULT_CONFIG)
        log(f"wrote default config -> {args.config}")
        if args.init:
            return
    config = load_json(args.config, DEFAULT_CONFIG)
    log("=== sync run start ===")
    run(config)
    log("=== sync run done ===")


if __name__ == "__main__":
    main()
