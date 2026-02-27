#!/usr/bin/env python3
"""Fetch tank KPIs and save to data/snapshot.json.

Run periodically via cron or systemd timer.
Designed to be lightweight enough for a Raspberry Pi.
"""

import json
import os
import sys
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
    aquarium_uid = os.environ["AQUARIUM_UID"]
    ato_hwid = os.environ["ATO_HWID"]
    pump_hwid = os.environ["PUMP_HWID"]
    light_hwids = os.environ.get("LIGHT_HWIDS", "").split(",")

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


if __name__ == "__main__":
    main()
