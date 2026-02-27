# ReefBeat Cloud API Reference

Reverse-engineered from the Red Sea ReefBeat iOS app (v8.0.0) via mitmproxy.

## Base URL

```
https://cloud.thereefbeat.com
```

## Authentication

OAuth2 password grant.

### Login / Get Token

```
POST /oauth/token
Content-Type: application/x-www-form-urlencoded
Authorization: Basic {REEFBEAT_CLIENT_CREDENTIALS}

grant_type=password&username={email}&password={password}
```

**Response:**
```json
{
    "access_token": "<JWT, 1 hour TTL>",
    "refresh_token": "<opaque token, long-lived>",
    "token_type": "Bearer",
    "expires_in": 3599
}
```

The `Authorization: Basic` header is a base64-encoded `client_id:client_secret`. This is the same for all ReefBeat users — it identifies the iOS app, not the user. See `.env.example` for the value.

### Refresh Token

```
POST /oauth/token
Content-Type: application/x-www-form-urlencoded
Authorization: Basic {REEFBEAT_CLIENT_CREDENTIALS}

grant_type=refresh_token&refresh_token={refresh_token}
```

### Authenticated Requests

All subsequent requests use:
```
Authorization: Bearer {access_token}
Content-Type: application/json
```

### JWT Claims

The access token JWT contains:
- `sub`: client ID
- `user_name`: user email
- `uid`: user UUID
- `exp`: expiration timestamp (iat + 3600)
- `iss`: `https://cloud.reef-beat.com`

---

## Endpoints

### User & Aquarium

| Method | Path | Description |
|--------|------|-------------|
| GET | `/user` | User profile |
| GET | `/user/picture` | User avatar |
| GET | `/aquarium` | List all aquariums |
| GET | `/aquarium/{uid}/dashboard` | **Main dashboard** — all devices in one response |
| GET | `/aquarium/{uid}/shortcut` | Shortcut states (feeding, maintenance, emergency) |
| GET | `/aquarium-system-model` | Available tank models |
| GET | `/device` | List all devices with full config |

### Reef Lights (RSLED)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/device/{hwid}/command/dashboard` | Light status: intensities (white/blue/moon), color temp, fan speed, temperature, acclimation, moon phase |
| GET | `/device/{hwid}/command/preset_name/{n}` | Preset name for slot N (1-7) |
| GET | `/device/{hwid}/mode` | Current mode (auto/manual) |
| GET | `/v2/reef-lights/library` | Saved light programs |
| GET | `/v2/reef-lights/color/library` | Saved color presets |

### ATO (Auto Top Off — RSATO+)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/reef-ato/{hwid}/dashboard` | ATO status: water level, **temperature**, fill stats, leak sensor |
| GET | `/reef-ato/{hwid}/configuration` | ATO settings (hose, pump, ranges) |
| GET | `/reef-ato/{hwid}/temperature-log?duration=P30D` | Temperature history (ISO 8601 duration) |

**ATO Dashboard Response:**
```json
{
    "mode": "auto",
    "is_pump_on": false,
    "auto_fill": true,
    "today_fills": 8,
    "today_volume_usage": 2687.0,
    "total_volume_usage": 97927.0,
    "daily_fills_average": 13.1,
    "daily_volume_average": 8272.0,
    "volume_left": 0.0,
    "days_till_empty": 0,
    "total_fills": 306,
    "ato_sensor": {
        "current_read": 26.291666,
        "current_level": "desired",
        "temperature_probe_status": "connected",
        "is_temp_enabled": true
    },
    "leak_sensor": {
        "status": "dry",
        "connected": true,
        "buzzer_on": false
    }
}
```

### Pumps (ReefRun — RSRUN)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/reef-run/{hwid}/dashboard` | Pump status: intensity, temperature, state |
| GET | `/reef-run/{hwid}/pump/settings` | Pump configuration |
| GET | `/reef-run/{hwid}/calibration` | Calibration data |

**Pump Dashboard Response:**
```json
{
    "mode": "auto",
    "pump_1": {
        "name": "Return",
        "type": "return",
        "model": "return-6000",
        "state": "operational",
        "intensity": 30,
        "temperature": 48.780487
    },
    "pump_2": {
        "name": "Skimmer",
        "type": "skimmer",
        "model": "rsk-600",
        "state": "operational",
        "intensity": 80,
        "temperature": 40.12195
    }
}
```

### ReefMat (RSMAT)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/reef-mat/{hwid}/configuration` | Mat settings |
| GET | `/reef-mat/{hwid}/rolling-log` | Roll usage by hour/day |

### Wave Pumps (ReefWave)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/reef-wave/schedule/{hwid}` | Wave schedule |
| GET | `/reef-wave/library` | Wave program library |

Wave pump status is included in the main aquarium dashboard under `reef_wave[]`:

```json
{
    "common": {
        "hwid": "<device-hwid>",
        "name": "Wave Right",
        "model": "RSWAVE45",
        "connected": true,
        "ip_address": "<local-ip>"
    },
    "specific": {
        "mode": "auto",
        "active_wave": {
            "wave_uid": "2c3c7c9d-1e1b-4c16-b3da-c1276f72da16",
            "type": "ra",
            "name": "RS Random",
            "frt": 10,
            "rrt": 2,
            "fti": 40,
            "rti": 60,
            "direction": "fw"
        },
        "controlling_mode": "reef-beat",
        "feeding_duration": 20
    }
}
```

**Wave field reference:**
- `type`: wave pattern — `ra` (random), `re` (regular), `st` (step), `nw` (no wave)
- `fti`: forward intensity (%)
- `rti`: reverse intensity (%)
- `frt`: flow reversal time (seconds)
- `rrt`: ramp/rest time (seconds)
- `direction`: `fw` (forward) or `rv` (reverse)

### Dosing (ReefDose)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/reef-dosing/supplement` | All available supplements |
| GET | `/reef-dosing/bundled-supplements/reef_care` | Reef Care 4-part bundle (ratios) |

### Firmware

| Method | Path | Description |
|--------|------|-------------|
| GET | `/firmware/api/{device-type}/latest?board={board}&framework={fw}` | Latest firmware version |

Device types: `reef-lights`, `reef-run`, `reef-dosing`, `wave-controller`, `reef-wave`, `reef-ato`

### Notifications

| Method | Path | Description |
|--------|------|-------------|
| GET | `/notification/inapp?expirationDays=90&page=0&size=100000&sortDirection=DESC` | All notifications (paginated) |
| GET | `/notification/inapp/count-unread?days=60` | Unread notification count |
| POST | `/notification/push/device/{token}` | Register push token |

**Notification Response:**
```json
{
    "content": [
        {
            "id": 50197239,
            "subject": "ReefBeat Notification",
            "text": "Office: Your Mat is due to end in 5 days.",
            "aquarium_uid": "<aquarium-uid>",
            "hwid": "<device-hwid>",
            "device_type": "reef-mat",
            "type": "roll_end_1",
            "time_sent": "2026-02-27T06:23:10.669846Z",
            "channel": "inapp",
            "read": false
        }
    ]
}
```

**Known notification types:**
- `roll_end_1` — ReefMat roll ending soon
- `full_cup_warning` — Skimmer cup full
- `connectivity_1` — Device connectivity issue
- `temp_danger` — Temperature outside acceptable range
- `pump_timeout` — ATO pump ran too long, shut down

---

## Device Hardware IDs

Discover these by intercepting traffic with mitmproxy (see `docs/REVERSE_ENGINEERING.md`).
Store them in your `.env` file. Example device types:

| Type | Model Examples | Endpoint prefix |
|------|---------------|-----------------|
| reef-ato | RSATO+ | `/reef-ato/{hwid}/` |
| reef-run | RSRUN | `/reef-run/{hwid}/` |
| reef-lights | RSLED115 | `/device/{hwid}/command/` |
| reef-mat | RSMAT500 | `/reef-mat/{hwid}/` |
| reef-wave | RSWAVE45 | via `/aquarium/{uid}/dashboard` |

## Aquarium

Each user can have multiple aquariums. The aquarium UID is returned by `GET /aquarium`
and used as a path parameter for dashboard and shortcut endpoints.

## Polling Behavior

The iOS app polls the aquarium dashboard endpoint approximately every 10 seconds. Device mode endpoints are polled in parallel.

## Temperature

The ATO sensor provides the tank water temperature. The value in `ato_sensor.current_read` is in **Celsius**. Temperature ranges from device config:
- Desired: 25.8°C – 26.7°C
- Acceptable: 25.0°C – 26.9°C

Light and pump temperatures are internal device temps (not water temp).
