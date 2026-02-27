# OpenReefBeat

A reverse-engineered API client for the [Red Sea ReefBeat](https://www.redseafish.com/reefbeat/) aquarium monitoring system. Built to run on a Raspberry Pi with an e-ink display, giving you a glanceable tank dashboard without needing your phone.

## What It Does

OpenReefBeat talks directly to the ReefBeat cloud API, pulling live data from all your connected devices:

- **Water temperature** (from ATO sensor)
- **Water level** and ATO fill stats
- **Leak detection** status
- **Light status** — intensity, color temp, white/blue/moon channels, LED temps, fan speed, program name, moon phase
- **Pump status** — return and skimmer state, intensity
- **Wave pump status** — program, forward/reverse intensity
- **Notifications** — unread alerts, recent events (temp warnings, skimmer full, mat ending, connectivity issues)

Data is saved as a simple JSON snapshot (`data/snapshot.json`) and appended to a history log (`data/history.jsonl`) for trend tracking.

## How It Works

```
ReefBeat Cloud API ──→ reefbeat.py (API client) ──→ refresh.py (cron job)
                                                        │
                                                        ├─→ data/snapshot.json  (latest readings)
                                                        └─→ data/history.jsonl  (append-only log)
```

Authentication is handled automatically — the client logs in with your credentials, caches the OAuth2 token, and refreshes it before expiry. No manual intervention needed.

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/MDamon/OpenReefBeat.git
cd OpenReefBeat
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env` with your ReefBeat credentials and device IDs. To discover your device hardware IDs, see [docs/REVERSE_ENGINEERING.md](docs/REVERSE_ENGINEERING.md).

### 3. Run

```bash
python3 refresh.py
```

```
[2026-02-27T15:52:50] Temp: 79.8°F | Level: desired | Leak: dry | ATO fills today: 8 | Return: operational @ 30% | Skimmer: operational @ 80%
```

### 4. Schedule (optional)

Poll every 5 minutes via cron:

```bash
crontab -e
```

```
*/5 * * * * cd /path/to/OpenReefBeat && python3 refresh.py >> /var/log/openreefbeat.log 2>&1
```

## Project Structure

```
OpenReefBeat/
├── .env.example              # Config template (credentials + device IDs)
├── requirements.txt          # Python dependencies (requests, python-dotenv)
├── reefbeat.py               # API client library
├── refresh.py                # Data fetcher — run via cron or systemd
├── docs/
│   ├── API.md                # Full API reference
│   └── REVERSE_ENGINEERING.md # How the API was discovered using mitmproxy
└── data/                     # Created at runtime, gitignored
    ├── token.json            # Cached OAuth tokens
    ├── snapshot.json         # Latest tank readings
    └── history.jsonl         # Historical log
```

## API Documentation

The full API reference is in [docs/API.md](docs/API.md), covering all known endpoints for:

- Authentication (OAuth2 password grant + refresh tokens)
- Aquarium dashboard
- ATO, lights, pumps, wave pumps, ReefMat, dosing
- Notifications
- Firmware versions

The API was reverse-engineered by intercepting the official ReefBeat iOS app using mitmproxy. The full methodology is documented in [docs/REVERSE_ENGINEERING.md](docs/REVERSE_ENGINEERING.md).

## Supported Devices

Tested with the following Red Sea hardware:

| Device | Model |
|--------|-------|
| ReefLED | RSLED115 |
| ReefATO+ | RSATO+ |
| ReefRun | RSRUN (return pump + skimmer) |
| ReefWave | RSWAVE45 |
| ReefMat | RSMAT500 |

Other ReefBeat-connected devices likely work — the API patterns are consistent across device types.

## Roadmap

- [ ] **Raspberry Pi e-ink display** — render `snapshot.json` to a Waveshare e-ink display with a clean, minimal layout showing key tank KPIs
- [ ] **Historical charts** — plot temperature, ATO usage, and other trends from `history.jsonl`
- [ ] **Alerts** — local notifications (LED, buzzer, or push) when values go out of range
- [ ] **Multi-tank support** — handle multiple aquariums under one account
- [ ] **Systemd service** — proper daemon setup for the Pi with watchdog and auto-restart
- [ ] **Web dashboard** — lightweight local web UI as an alternative to e-ink
- [ ] **Home Assistant integration** — expose sensors as HA entities via MQTT or REST

## Disclaimer

This project is not affiliated with or endorsed by Red Sea. It interacts with the ReefBeat cloud API, which is undocumented and may change without notice. Use at your own risk.

## License

MIT
