# How We Reverse-Engineered the ReefBeat API

This documents the full process used to intercept, capture, and parse the Red Sea
ReefBeat iOS app's API traffic using mitmproxy on macOS.

## Prerequisites

- Mac on the same Wi-Fi as the iPhone
- Homebrew installed

## Step 1: Install mitmproxy

```bash
brew install mitmproxy
```

## Step 2: Start the proxy

For interactive browsing (web UI):
```bash
mitmweb --web-port 8081 --listen-port 8080
```

For headless capture to a file (what we used for parsing):
```bash
mitmdump --listen-port 8080 -w ~/reefbeat.flow
```

## Step 3: Configure iPhone proxy

1. Find Mac's local IP: `ipconfig getifaddr en0`
2. iPhone → Settings → Wi-Fi → tap network → Configure Proxy → Manual
   - Server: Mac's IP
   - Port: 8080
3. On iPhone Safari, visit `http://mitm.it` → download Apple profile
4. Settings → General → VPN & Device Management → install mitmproxy cert
5. Settings → General → About → Certificate Trust Settings → enable full trust for mitmproxy

## Step 4: Capture traffic

Open the ReefBeat app. Traffic flows through mitmdump and is saved to the `.flow` file.

**Important:** The app only loads detailed device data when you tap into each device screen.
We had to manually navigate to these sections to capture their endpoints:
- Main dashboard (loads automatically)
- Wave pumps (tap into wave pump detail)
- Notifications (tap into notification list)
- Login/auth (log out and log back in)

## Step 5: Parse the capture file

### List all endpoints (headers only)
```bash
mitmdump -r ~/reefbeat.flow -n --set flow_detail=2 2>&1 | head -300
```

### Show full request/response bodies
```bash
mitmdump -r ~/reefbeat.flow -n --set flow_detail=3 2>&1 | head -500
```

### Filter to specific domain
```bash
mitmdump -r ~/reefbeat.flow -n --set flow_detail=2 2>&1 | grep "thereefbeat"
```

### Extract unique API paths
```bash
mitmdump -r ~/reefbeat.flow -n --set flow_detail=2 2>&1 \
  | grep -E "GET.*thereefbeat" \
  | sed 's/.*GET /GET /' | sed 's/ HTTP.*//' \
  | sort -u
```

### Python parsing (requires matching mitmproxy version)

The `.flow` file format is version-specific. The `mitmproxy` Python package must match
the version of `mitmdump` that wrote the file. In our case, Homebrew installed v12.x
but `pip install mitmproxy` gave v9.x, causing a version mismatch. We worked around
this by using `mitmdump -r` to read flows instead of the Python API directly.

If versions match, you can parse programmatically:
```python
from mitmproxy.io import FlowReader
import json

with open("reefbeat.flow", "rb") as f:
    for flow in FlowReader(f).stream():
        req = flow.request
        print(f"{req.method} {req.url}")
        if flow.response and "json" in flow.response.headers.get("content-type", ""):
            print(json.dumps(json.loads(flow.response.content), indent=2))
```

## Step 6: Key discoveries

### Authentication
The login flow was only visible after logging out and back in while proxying.
The app uses OAuth2 password grant to `POST /oauth/token` with:
- Basic auth header containing the app's client credentials (same for all users)
- Form body with `grant_type=password`, `username`, and `password`
- Response includes both `access_token` (1hr JWT) and `refresh_token` (long-lived)

### Dashboard endpoint
`GET /aquarium/{uid}/dashboard` returns ALL device data in a single response:
- `reef_lights[]` — light status, intensities, programs, moon phase
- `reef_wave[]` — wave pump status, active program, intensities
- `reef_run[]` — pump controller status (wasn't populated for us, separate endpoint used)
- `reef_ato[]` — ATO status (wasn't populated for us, separate endpoint used)
- `reef_mat[]` — ReefMat status

The ATO and pump dashboards required separate endpoint calls for full data.

### Temperature
Water temperature comes from the ATO sensor (`ato_sensor.current_read` in Celsius).
Light and pump "temperature" fields are internal device temperatures, not water temp.

### Polling
The iOS app polls the dashboard endpoint every ~10 seconds. For a Pi with e-ink display,
polling every 5 minutes is more than sufficient.

## Captured flow file

The original capture is saved at `~/reefbeat.flow` (not committed to repo as it
contains auth tokens and passwords). To re-capture, repeat steps 2-4.

## Cleanup

After capturing, disable the proxy on your iPhone:
1. Settings → Wi-Fi → tap network → Configure Proxy → Off
2. Optionally remove the mitmproxy certificate from Certificate Trust Settings

Stop mitmdump on the Mac:
```bash
pkill -f mitmdump
```
