#!/usr/bin/env python3
"""Fetch tank KPIs and save to data/snapshot.json.

Run periodically via cron or systemd timer.
Designed to be lightweight enough for a Raspberry Pi.
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from reefbeat import ReefBeatClient, DATA_DIR

SNAPSHOT_FILE = DATA_DIR / "snapshot.json"
HISTORY_FILE = DATA_DIR / "history.jsonl"


def main():
    load_dotenv(Path(__file__).parent / ".env")

    username = os.environ["REEFBEAT_USERNAME"]
    password = os.environ["REEFBEAT_PASSWORD"]
    client_creds = os.environ["REEFBEAT_CLIENT_CREDENTIALS"]

    # Device IDs are optional — auto-discovered if not set
    aquarium_uid = os.environ.get("AQUARIUM_UID") or None
    ato_hwid = os.environ.get("ATO_HWID") or None
    pump_hwid = os.environ.get("PUMP_HWID") or None
    light_hwids_str = os.environ.get("LIGHT_HWIDS", "").strip()
    light_hwids = light_hwids_str.split(",") if light_hwids_str else None

    client = ReefBeatClient(username, password, client_creds)

    try:
        snap = client.snapshot(aquarium_uid, ato_hwid, pump_hwid, light_hwids)
    except Exception as e:
        print(f"[{datetime.now().isoformat()}] ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # Write current snapshot (overwritten each time)
    SNAPSHOT_FILE.write_text(json.dumps(snap, indent=2))

    # Append to history log (one JSON object per line)
    with open(HISTORY_FILE, "a") as f:
        f.write(json.dumps(snap) + "\n")

    # Trim history to last 30 days
    max_age = int(os.environ.get("HISTORY_DAYS", 30))
    _trim_history(max_age)

    temp = snap["temperature_f"] or "?"
    level = snap["water_level"] or "?"
    leak = snap["leak_status"] or "?"
    print(
        f"[{datetime.now().isoformat()}] "
        f"Temp: {temp}°F | Level: {level} | Leak: {leak} | "
        f"ATO fills today: {snap['ato_fills_today']} | "
        f"Return: {snap['return_pump']['state']} @ {snap['return_pump']['intensity']}% | "
        f"Skimmer: {snap['skimmer']['state']} @ {snap['skimmer']['intensity']}%"
    )


def _trim_history(max_days=30):
    """Remove history entries older than max_days. Runs in-place."""
    if not HISTORY_FILE.exists():
        return
    cutoff = time.time() - max_days * 86400
    lines = HISTORY_FILE.read_text().strip().split("\n")
    kept = []
    for line in lines:
        try:
            if json.loads(line).get("timestamp", 0) >= cutoff:
                kept.append(line)
        except (json.JSONDecodeError, KeyError):
            continue
    if len(kept) < len(lines):
        HISTORY_FILE.write_text("\n".join(kept) + "\n" if kept else "")


if __name__ == "__main__":
    main()
