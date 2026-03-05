"""OpenReefBeat — Inky Frame 7.3" Dashboard"""

import gc
import math
import time
import urequests
import ntptime
import machine
import inky_helper as ih
from picographics import PicoGraphics, DISPLAY_INKY_FRAME_7 as DISPLAY
from config import *

gc.collect()

# ── Display setup ───────────────────────────────────────────
WIDTH = 800
HEIGHT = 480
graphics = PicoGraphics(DISPLAY)

# Inky Frame native palette (mapped from device test)
BLACK = 0
WHITE = 1
YELLOW = 2
RED = 3
BLUE = 5
GREEN = 6

HEADER_H = 44
LEFT_W = 280
PAD = 16

# Button toggle states (True = active/on)
btn_states = {
    "A": False,  # Water change sequence
    "B": False,  # ATO auto-fill
    "C": False,  # Return pump on/off
    "D": False,  # Resume/Stop Skimmer
    "E": False,  # Emergency Stop/Resume
}

# Kasa cloud config (imported from config.py: KASA_TOKEN, KASA_CLOUD_URL,
# KASA_WASTE_DEVICE, KASA_WASTE_CHILD, KASA_SALT_DEVICE, KASA_SALT_CHILD)
btn_a_label = "10m W/C"
GAUGE_R = 50
GAUGE_THICK = 15
GAUGE_STEPS = 72  # points per full circle — balances smoothness vs memory
UTC_OFFSET = -5  # EST (Eastern Standard Time)

gc.collect()


# ── WiFi helper ────────────────────────────────────────────
def ensure_wifi():
    """Check WiFi and reconnect if needed. Retries indefinitely with backoff."""
    import network
    wlan = network.WLAN(network.STA_IF)
    if wlan.isconnected():
        return True
    print("WiFi dropped — reconnecting...")
    attempt = 0
    while True:
        attempt += 1
        backoff = min(attempt * 5, 60)  # 5s, 10s, 15s, ... cap at 60s
        wlan.active(False)
        time.sleep(2)
        wlan.active(True)
        time.sleep(1)
        wlan.config(pm=0xa11140)
        for ssid, pwd in WIFI_NETWORKS:
            print("  Trying '{}'...".format(ssid))
            wlan.disconnect()
            time.sleep(1)
            wlan.connect(ssid, pwd)
            for _ in range(30):
                if wlan.isconnected():
                    print("  Reconnected to '{}' (attempt {})".format(ssid, attempt))
                    return True
                time.sleep(1)
        print("  Reconnect round {} failed, waiting {}s...".format(attempt, backoff))
        gc.collect()
        time.sleep(backoff)


# ── ReefBeat API ────────────────────────────────────────────
BASE_URL = "https://cloud.thereefbeat.com"
_token = None
_aquarium_uid = None
_pump_hwid = None
_ato_hwid = None


def api_login():
    global _token
    ensure_wifi()
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": "Basic " + CLIENT_CREDENTIALS,
    }
    body = "grant_type=password&username={}&password={}".format(USERNAME, REEFBEAT_PASSWORD)
    for attempt in range(3):
        try:
            r = urequests.post(BASE_URL + "/oauth/token", data=body, headers=headers)
            data = r.json()
            r.close()
            gc.collect()
            _token = data["access_token"]
            return
        except OSError as e:
            print("Login retry {}: {}".format(attempt + 1, e))
            ensure_wifi()
            gc.collect()
            time.sleep(2)
    raise OSError("Login failed after 3 retries")


def api_get(path):
    headers = {"Authorization": "Bearer " + _token}
    for attempt in range(3):
        try:
            r = urequests.get(BASE_URL + path, headers=headers)
            data = r.json()
            r.close()
            gc.collect()
            return data
        except OSError as e:
            print("API retry {}: {}".format(attempt + 1, e))
            ensure_wifi()
            gc.collect()
            time.sleep(2)
    raise OSError("API failed after 3 retries")


def api_post(path):
    """POST with empty body to ReefBeat API."""
    ensure_wifi()
    headers = {"Authorization": "Bearer " + _token, "Content-Type": "application/json"}
    r = urequests.post(BASE_URL + path, headers=headers)
    data = r.json()
    r.close()
    gc.collect()
    print("POST {} -> {}".format(path, data))
    return data


def kasa_toggle(device_id, child_id, turn_on):
    """Toggle a Kasa outlet via TP-Link cloud API using raw sockets."""
    import ujson, usocket, ssl
    state = 1 if turn_on else 0
    inner = ujson.dumps({"context": {"child_ids": [child_id]}, "system": {"set_relay_state": {"state": state}}})
    body = ujson.dumps({"method": "passthrough", "params": {"deviceId": device_id, "requestData": inner}})
    path = "/?token=" + KASA_TOKEN
    host = "use1-wap.tplinkcloud.com"

    for attempt in range(3):
        gc.collect()
        ensure_wifi()
        try:
            ai = usocket.getaddrinfo(host, 443)
            addr = ai[0][-1]
            print("Kasa attempt {} -> {}".format(attempt + 1, addr))
            s = usocket.socket()
            s.connect(addr)
            ss = ssl.wrap_socket(s, server_hostname=host)

            request = "POST {} HTTP/1.1\r\nHost: {}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}".format(
                path, host, len(body), body)
            ss.write(request.encode())

            resp = b""
            while True:
                chunk = ss.read(512)
                if not chunk:
                    break
                resp += chunk
            ss.close()
            gc.collect()

            resp_str = resp.decode()
            body_start = resp_str.find("\r\n\r\n")
            resp_body = resp_str[body_start + 4:] if body_start >= 0 else ""
            data = ujson.loads(resp_body) if resp_body.strip() else {}
            print("Kasa {} child {} -> state={} err={}".format(device_id[-4:], child_id[-2:], state, data.get("error_code")))
            return data
        except Exception as e:
            print("Kasa attempt {} failed: {}".format(attempt + 1, e))
            time.sleep(3)
    raise OSError("Kasa failed after 3 attempts")


def fetch_tank_data():
    global _aquarium_uid, _pump_hwid, _ato_hwid
    api_login()
    gc.collect()

    aquariums = api_get("/aquarium")
    if not aquariums:
        raise RuntimeError("No aquariums found")
    uid = aquariums[0]["uid"]
    _aquarium_uid = uid
    tank_name = aquariums[0].get("name", "My Tank")
    del aquariums
    gc.collect()

    dashboard = api_get("/aquarium/{}/dashboard".format(uid))
    gc.collect()

    # Extract HWIDs
    ato_hwid = None
    pump_hwid = None
    atos = dashboard.get("reef_ato", [])
    if atos:
        ato_hwid = atos[0]["common"]["hwid"]
        _ato_hwid = ato_hwid
    runs = dashboard.get("reef_run", [])
    if runs:
        pump_hwid = runs[0]["common"]["hwid"]
        _pump_hwid = pump_hwid

    # Extract dashboard fields
    lights = dashboard.get("reef_lights", [])
    light = lights[0].get("specific", {}) if lights else {}
    manual = light.get("manual", {})
    waves = dashboard.get("reef_wave", [])
    mats = dashboard.get("reef_mat", [])
    mat = mats[0].get("specific", {}) if mats else {}

    # Calculate roller used percentage
    roller_pct = 0
    remaining_cm = mat.get("remaining_length", 0)
    mat_material = mat.get("material", {})
    mat_name = mat_material.get("name", "")
    print("Roller raw: remaining={}cm name='{}'".format(remaining_cm, mat_name))
    parts = mat_name.split()
    if parts and remaining_cm:
        try:
            total_m = float(parts[0])
            total_cm = total_m * 100
            if total_cm > 0:
                roller_pct = round((1 - remaining_cm / total_cm) * 100, 1)
                print("Roller calc: total={}cm pct={}".format(total_cm, roller_pct))
        except ValueError:
            print("Roller: could not parse total from '{}'".format(mat_name))

    result = {
        "tank_name": tank_name,
        "light_pct": manual.get("intensity", 0),
        "light_kelvin": manual.get("kelvin", 0),
        "moon_pct": manual.get("moon", 0),
        "wave_l_pct": waves[1].get("specific", {}).get("active_wave", {}).get("fti", 0) if len(waves) > 1 else 0,
        "wave_r_pct": waves[0].get("specific", {}).get("active_wave", {}).get("fti", 0) if waves else 0,
        "wave_program": waves[0].get("specific", {}).get("active_wave", {}).get("name", "") if waves else "",
        "roller_pct": roller_pct,
        "roller_days": mat.get("days_till_end_of_roll"),
        "roller_level": mat.get("roll_level", ""),
        "roller_mode": mat.get("mode", ""),
        "roller_today_cm": round(mat.get("today_usage", 0), 1),
        "roller_avg_cm": round(mat.get("daily_average_usage", 0), 1),
        "roller_used_cm": round(mat.get("total_usage", 0), 1),
        "roller_remaining_cm": round(remaining_cm, 1),
    }
    del dashboard, lights, light, manual, waves, mats, mat, mat_material
    gc.collect()

    if ato_hwid:
        ato = api_get("/reef-ato/{}/dashboard".format(ato_hwid))
        s = ato.get("ato_sensor", {})
        tc = s.get("current_read")
        result["temp_f"] = round(tc * 9 / 5 + 32, 1) if tc else None
        result["level"] = s.get("current_level", "?")
        result["leak"] = ato.get("leak_sensor", {}).get("status", "?")
        result["ato_vol_ml"] = ato.get("today_volume_usage", 0)
        result["ato_fills"] = ato.get("today_fills", 0)
        result["auto_fill"] = ato.get("auto_fill", False)
        del ato, s
    gc.collect()

    if pump_hwid:
        pumps = api_get("/reef-run/{}/dashboard".format(pump_hwid))
        p1 = pumps.get("pump_1", {})
        p2 = pumps.get("pump_2", {})
        result["return_pct"] = p1.get("intensity", 0)
        result["return_schedule"] = p1.get("schedule_enabled", True)
        result["skimmer_pct"] = p2.get("intensity", 0)
        result["skimmer_sensor"] = p2.get("sensor_controlled", False)
        result["skimmer_state"] = p2.get("state", "operational")
        result["skimmer_schedule"] = p2.get("schedule_enabled", True)
        del pumps, p1, p2
    gc.collect()

    # Shortcut states (maintenance, emergency)
    try:
        shortcuts = api_get("/aquarium/{}/shortcut".format(uid))
        result["maint_active"] = shortcuts.get("maintenance_1", {}).get("active", False)
        result["emergency_active"] = shortcuts.get("emergency_1", {}).get("active", False)
    except Exception:
        result["maint_active"] = False
        result["emergency_active"] = False
    gc.collect()

    return result


# ── Drawing helpers ─────────────────────────────────────────
def _fill_ring(cx, cy, r_out, r_in, color, start_deg=0, end_deg=360):
    """Fill a ring sector pixel-by-pixel. Solid, no gaps."""
    graphics.set_pen(color)
    r_out_sq = r_out * r_out
    r_in_sq = r_in * r_in
    # Convert to radians (0=top, clockwise)
    if start_deg == 0 and end_deg == 360:
        # Full ring — skip angle check for speed
        for dy in range(-r_out, r_out + 1):
            for dx in range(-r_out, r_out + 1):
                d_sq = dx * dx + dy * dy
                if r_in_sq <= d_sq <= r_out_sq:
                    graphics.pixel(cx + dx, cy + dy)
    else:
        s_rad = (start_deg - 90) * math.pi / 180
        e_rad = (end_deg - 90) * math.pi / 180
        for dy in range(-r_out, r_out + 1):
            for dx in range(-r_out, r_out + 1):
                d_sq = dx * dx + dy * dy
                if r_in_sq <= d_sq <= r_out_sq:
                    a = math.atan2(dy, dx)
                    # Normalize to match our start reference
                    if a < s_rad:
                        a += 2 * math.pi
                    if s_rad <= a <= e_rad:
                        graphics.pixel(cx + dx, cy + dy)
    gc.collect()


def draw_gauge(cx, cy, pct, color, label):
    """Draw a circular gauge with percentage and label."""
    r_out = GAUGE_R
    r_in = GAUGE_R - GAUGE_THICK

    # Black outer border ring
    _fill_ring(cx, cy, r_out, r_in, BLACK)
    # White track (1px inset)
    _fill_ring(cx, cy, r_out - 1, r_in + 1, WHITE)

    # Filled arc
    if pct > 0:
        end_deg = int(360 * min(pct, 100) / 100)
        _fill_ring(cx, cy, r_out - 1, r_in + 1, color, 0, end_deg)

    # Center text: value%
    graphics.set_pen(BLACK)
    graphics.set_font("bitmap8")
    val = "{}%".format(int(pct))
    vw = graphics.measure_text(val, scale=3)
    vx = max(0, cx - vw // 2)
    graphics.text(val, vx, cy - 8, WIDTH, scale=3)

    # Label below
    if label:
        lw = graphics.measure_text(label, scale=2)
        lbx = max(0, cx - lw // 2)
        graphics.text(label, lbx, cy + GAUGE_R + 10, WIDTH, scale=2)
    gc.collect()


# ── Dashboard renderer ──────────────────────────────────────
def render_dashboard(data):
    graphics.set_pen(WHITE)
    graphics.clear()
    gc.collect()

    # Determine status
    leak = data.get("leak", "dry")
    level = data.get("level", "desired")
    if leak != "dry":
        status_text = "[!!] LEAK DETECTED"
        header_color = RED
    elif level not in ("desired", "acceptable"):
        status_text = "[!!] Level: {}".format(level)
        header_color = RED
    elif data.get("roller_mode") == "torn_mat":
        status_text = "[!!] MAT JAMMED"
        header_color = RED
    else:
        status_text = "All systems operational"
        header_color = BLUE

    # Header: tank name | status | branding + date/time
    graphics.set_pen(header_color)
    graphics.rectangle(0, 0, WIDTH, HEADER_H)
    graphics.set_pen(WHITE)
    graphics.set_font("bitmap8")
    HSCALE = 3
    tank = data.get("tank_name", "")
    graphics.text(tank, PAD, 10, WIDTH, scale=HSCALE)
    t = time.localtime(time.time() + UTC_OFFSET * 3600)
    ts = "{:02d}/{:02d} {:02d}:{:02d}".format(t[1], t[2], t[3], t[4])
    tw = graphics.measure_text(ts, scale=HSCALE)
    graphics.text(ts, WIDTH - PAD - tw, 10, WIDTH, scale=HSCALE)
    sw = graphics.measure_text(status_text, scale=HSCALE)
    graphics.text(status_text, WIDTH // 2 - sw // 2, 10, WIDTH, scale=HSCALE)
    gc.collect()

    # Divider (shortened — stop HEADER_H px from bottom for button bar)
    BTN_H = HEADER_H
    graphics.set_pen(BLACK)
    graphics.line(LEFT_W, HEADER_H, LEFT_W, HEIGHT - BTN_H)

    # LEFT PANEL
    lx = PAD
    y = HEADER_H + 16

    # Temperature
    temp = data.get("temp_f")
    graphics.set_pen(BLACK)
    graphics.set_font("bitmap8")
    if temp is not None:
        graphics.text("{}F".format(temp), lx, y, WIDTH, scale=6)
    else:
        graphics.set_pen(RED)
        graphics.text("--.-F", lx, y, WIDTH, scale=6)
    gc.collect()

    # Water level with status indicator
    y += 64
    level = data.get("level", "?")
    level_ok = level in ("desired", "acceptable")
    graphics.set_pen(GREEN if level_ok else RED)
    graphics.circle(lx + 6, y + 10, 6)
    graphics.set_pen(BLACK if level_ok else RED)
    graphics.set_font("bitmap8")
    graphics.text("Level: {}".format(level), lx + 18, y + 2, WIDTH, scale=2)

    y += 30
    graphics.set_pen(BLACK)
    graphics.line(lx, y, LEFT_W - PAD, y)

    # ATO
    y += 10
    graphics.set_pen(BLUE)
    graphics.set_font("bitmap8")
    graphics.text("ATO", lx, y, WIDTH, scale=3)

    y += 28
    graphics.set_pen(BLACK)
    vol_gal = round(data.get("ato_vol_ml", 0) / 3785.41, 2)
    graphics.text("{} gal today".format(vol_gal), lx, y, WIDTH, scale=2)

    y += 22
    fills = data.get("ato_fills", 0)
    auto = "ON" if data.get("auto_fill") else "OFF"
    graphics.text("{} fills / Auto {}".format(fills, auto), lx, y, WIDTH, scale=2)

    y += 22
    leak = data.get("leak", "?")
    leak_ok = leak == "dry"
    graphics.set_pen(GREEN if leak_ok else RED)
    graphics.circle(lx + 6, y + 8, 6)
    graphics.set_pen(BLACK if leak_ok else RED)
    graphics.text("Leak: {}".format(leak), lx + 18, y, WIDTH, scale=2)
    gc.collect()

    y += 30
    graphics.set_pen(BLACK)
    graphics.line(lx, y, LEFT_W - PAD, y)

    # Roller
    y += 10
    graphics.set_pen(BLUE)
    graphics.set_font("bitmap8")
    # Roller header with used/total in feet
    used_cm = data.get("roller_used_cm", 0)
    rem_cm = data.get("roller_remaining_cm", 0)
    total_cm = used_cm + rem_cm
    used_ft = round(used_cm / 30.48, 1)
    total_ft = round(total_cm / 30.48, 1)
    graphics.text("Roller", lx, y, WIDTH, scale=3)
    ft_text = "{}ft/{}ft".format(used_ft, total_ft)
    fw = graphics.measure_text(ft_text, scale=2)
    graphics.set_pen(BLACK)
    graphics.text(ft_text, LEFT_W - PAD - fw, y + 6, WIDTH, scale=2)

    y += 28
    graphics.set_pen(BLACK)
    graphics.set_font("bitmap8")
    roller_pct = data.get("roller_pct", 0)
    roller_days = data.get("roller_days")
    roller_level = data.get("roller_level", "")
    roller_mode = data.get("roller_mode", "")
    bar_color = RED if roller_level == "running_low" or roller_mode == "torn_mat" else BLUE
    if roller_pct > 0.1:
        bar_w = LEFT_W - PAD * 2
        graphics.set_pen(BLACK)
        graphics.rectangle(lx, y, bar_w, 20)
        graphics.set_pen(WHITE)
        graphics.rectangle(lx + 1, y + 1, bar_w - 2, 18)
        fill_w = int((bar_w - 2) * roller_pct / 100)
        if fill_w > 0:
            graphics.set_pen(bar_color)
            graphics.rectangle(lx + 1, y + 1, fill_w, 18)
        y += 26
        # Today and average usage in inches
        today_in = round(data.get("roller_today_cm", 0) / 2.54, 1)
        avg_in = round(data.get("roller_avg_cm", 0) / 2.54, 1)
        graphics.set_pen(BLACK)
        graphics.text("Today: {}in / Avg: {}in".format(today_in, avg_in), lx, y, WIDTH, scale=2)
        if roller_mode == "torn_mat":
            y += 18
            graphics.set_pen(RED)
            graphics.text("[!!] MAT JAMMED", lx, y, WIDTH, scale=2)
        elif roller_days is not None:
            y += 18
            graphics.set_pen(RED if roller_days <= 5 else BLACK)
            graphics.text("{} days remaining".format(roller_days), lx, y, WIDTH, scale=2)
    else:
        graphics.text("No data", lx, y, WIDTH, scale=2)

    # Branding below roller
    y += 24
    graphics.set_pen(BLACK)
    graphics.line(lx, y, LEFT_W - PAD, y)
    y += 6
    graphics.text("OpenReefBeat", lx, y, WIDTH, scale=1)
    gc.collect()

    # RIGHT PANEL — gauge layout (3 columns x 2 rows)
    col1_cx = LEFT_W + (WIDTH - LEFT_W) // 6          # Lights
    col2_cx = LEFT_W + (WIDTH - LEFT_W) // 2          # Pumps
    col3_cx = LEFT_W + 5 * (WIDTH - LEFT_W) // 6      # Waves
    top_y = HEADER_H + 14
    row1_cy = top_y + 50 + GAUGE_R + 10
    row2_cy = row1_cy + GAUGE_R * 2 + 70

    # Column headers
    graphics.set_pen(BLUE)
    graphics.set_font("bitmap8")
    for cx, label in [(col1_cx, "Lights"), (col2_cx, "Pumps"), (col3_cx, "Waves")]:
        hw = graphics.measure_text(label, scale=3)
        graphics.text(label, max(0, cx - hw // 2), top_y, WIDTH, scale=3)

    # Wave program under Waves header
    prog = data.get("wave_program", "")
    if prog:
        graphics.set_pen(BLACK)
        pw = graphics.measure_text(prog, scale=2)
        graphics.text(prog, max(0, col3_cx - pw // 2), top_y + 28, WIDTH, scale=2)
    gc.collect()

    # Top row: Intensity, Return, Left wave
    kelvin = data.get("light_kelvin", 0)
    k_label = "{}K".format(kelvin // 1000) if kelvin else ""
    draw_gauge(col1_cx, row1_cy, data.get("light_pct", 0), BLUE, k_label)
    draw_gauge(col2_cx, row1_cy, data.get("return_pct", 0), BLUE, "Return")
    draw_gauge(col3_cx, row1_cy, data.get("wave_l_pct", 0), BLUE, "Left")

    # Bottom row: Moon, Skimmer, Right wave
    draw_gauge(col1_cx, row2_cy, data.get("moon_pct", 0), BLUE, "Moon")
    skimmer_full = data.get("skimmer_state") == "full-cup"
    skimmer_color = RED if skimmer_full else BLUE
    draw_gauge(col2_cx, row2_cy, data.get("skimmer_pct", 0), skimmer_color, "Skimmer")
    if skimmer_full:
        # Warning triangle + text below skimmer gauge
        ty = row2_cy + GAUGE_R + 32
        graphics.set_pen(RED)
        # Triangle (pointing up) - narrow at top, wide at bottom
        tcx = col2_cx - 30
        for row in range(12):
            half = row // 2
            x0 = tcx + 6 - half
            x1 = tcx + 6 + half
            graphics.line(x0, ty + row, x1, ty + row)
        # Exclamation mark in triangle
        graphics.set_pen(WHITE)
        graphics.line(tcx + 6, ty + 3, tcx + 6, ty + 7)
        graphics.pixel(tcx + 6, ty + 9)
        # "FULL" text
        graphics.set_pen(RED)
        graphics.set_font("bitmap8")
        graphics.text("FULL", tcx + 16, ty, WIDTH, scale=2)
    draw_gauge(col3_cx, row2_cy, data.get("wave_r_pct", 0), BLUE, "Right")

    # ── Button bar at bottom ──
    btn_top = HEIGHT - BTN_H
    graphics.set_pen(BLACK)
    graphics.line(0, btn_top, WIDTH, btn_top)
    btn_w = WIDTH // 5
    graphics.set_font("bitmap8")
    # Button labels: (key, label) — dot color shows state (green=on, red=off)
    btn_labels = [
        ("A", btn_a_label),
        ("B", "ATO"),
        ("C", "Return"),
        ("D", "Skimmer"),
        ("E", "E-Stop"),
    ]
    for i, (key, label) in enumerate(btn_labels):
        bx = i * btn_w
        if i > 0:
            graphics.set_pen(BLACK)
            graphics.line(bx, btn_top, bx, HEIGHT)
        cx = bx + btn_w // 2
        on = btn_states[key]
        # Measure label to position dot + text as a unit
        lw = graphics.measure_text(label, scale=2)
        dot_r = 5
        gap = 6
        total_w = dot_r * 2 + gap + lw
        start_x = cx - total_w // 2
        # Status dot (green = active/on, red = off/inactive)
        dot_color = GREEN if on else RED
        graphics.set_pen(dot_color)
        dot_y = btn_top + BTN_H // 2
        graphics.circle(start_x + dot_r, dot_y, dot_r)
        # Label text
        graphics.set_pen(BLACK)
        text_x = start_x + dot_r * 2 + gap
        graphics.text(label, text_x, btn_top + (BTN_H - 16) // 2, WIDTH, scale=2)

    gc.collect()


def render_error(title, detail=""):
    graphics.set_pen(WHITE)
    graphics.clear()
    graphics.set_pen(RED)
    graphics.rectangle(0, 0, WIDTH, HEADER_H)
    graphics.set_pen(WHITE)
    graphics.set_font("bitmap8")
    graphics.text("OpenReefBeat - ERROR", PAD, 12, scale=3)
    graphics.set_pen(BLACK)
    cx = WIDTH // 2
    tw = graphics.measure_text(title, scale=3)
    graphics.text(title, cx - tw // 2, 180, scale=3)
    if detail:
        dw = graphics.measure_text(detail, scale=2)
        graphics.text(detail, cx - dw // 2, 230, scale=2)
    msg = "Check WiFi and config.py"
    mw = graphics.measure_text(msg, scale=2)
    graphics.text(msg, cx - mw // 2, 300, scale=2)


# ── Water change sequence ──────────────────────────────────
def run_water_change(data):
    """20-min water change: maintenance on, drain 10m, fill 10m, maintenance off."""
    global btn_a_label
    PHASE_MIN = 10

    btn_states["A"] = True
    try:
        # Start maintenance mode (disables return, ATO, skimmer)
        print("WC: Starting maintenance mode")
        api_post("/aquarium/{}/shortcut/maintenance_1/start".format(_aquarium_uid))
        time.sleep(3)
        gc.collect()

        # Drain phase — waste pump on for 10 min
        print("WC: Drain phase — waste pump ON")
        try:
            kasa_toggle(KASA_WASTE_DEVICE, KASA_WASTE_CHILD, True)
        except Exception as e:
            print("WC: Kasa waste ON failed: {}".format(e))
        for remaining in range(PHASE_MIN, 0, -1):
            btn_a_label = "Waste {}m".format(remaining)
            render_dashboard(data)
            gc.collect()
            graphics.update()
            time.sleep(60)

        print("WC: Drain done — waste pump OFF")
        try:
            kasa_toggle(KASA_WASTE_DEVICE, KASA_WASTE_CHILD, False)
        except Exception as e:
            print("WC: Kasa waste OFF failed: {}".format(e))

        # Fill phase — salt pump on for 10 min
        print("WC: Fill phase — salt pump ON")
        try:
            kasa_toggle(KASA_SALT_DEVICE, KASA_SALT_CHILD, True)
        except Exception as e:
            print("WC: Kasa salt ON failed: {}".format(e))
        for remaining in range(PHASE_MIN, 0, -1):
            btn_a_label = "Salt {}m".format(remaining)
            render_dashboard(data)
            gc.collect()
            graphics.update()
            time.sleep(60)

        print("WC: Fill done — salt pump OFF")
        try:
            kasa_toggle(KASA_SALT_DEVICE, KASA_SALT_CHILD, False)
        except Exception as e:
            print("WC: Kasa salt OFF failed: {}".format(e))

    finally:
        # Always stop maintenance mode, even if Kasa calls failed
        print("WC: Stopping maintenance mode")
        try:
            api_post("/aquarium/{}/shortcut/maintenance_1/stop".format(_aquarium_uid))
        except Exception as e:
            print("WC: Failed to stop maintenance: {}".format(e))
        btn_states["A"] = False
        btn_a_label = "10m W/C"
        render_dashboard(data)
        gc.collect()
        graphics.update()
        print("WC: Sequence complete")


# ── Main ────────────────────────────────────────────────────
print("OpenReefBeat starting...")
gc.collect()

# WiFi — retry indefinitely with backoff until connected
import network
wlan = network.WLAN(network.STA_IF)
attempt = 0
while not wlan.isconnected():
    attempt += 1
    backoff = min(attempt * 5, 60)  # 5s, 10s, 15s, ... cap at 60s
    wlan.active(False)
    time.sleep(2)
    wlan.active(True)
    time.sleep(1)
    wlan.config(pm=0xa11140)
    print("WiFi round {}...".format(attempt))
    for ssid, pwd in WIFI_NETWORKS:
        print("  Trying '{}'...".format(ssid))
        wlan.disconnect()
        time.sleep(1)
        wlan.connect(ssid, pwd)
        for _ in range(30):
            status = wlan.status()
            if status == 3:
                break
            time.sleep(1)
        if wlan.isconnected():
            print("  Connected to '{}'".format(ssid))
            break
        print("  '{}' failed (status={})".format(ssid, status))
    if not wlan.isconnected():
        print("Round {} failed, waiting {}s...".format(attempt, backoff))
        gc.collect()
        time.sleep(backoff)

print("WiFi connected")

# Sync clock via NTP (retry up to 3 times)
for _ntp in range(3):
    try:
        ntptime.settime()
        print("NTP time synced")
        break
    except Exception:
        print("NTP attempt {} failed".format(_ntp + 1))
        time.sleep(2)
else:
    print("NTP sync failed (clock may be wrong)")
gc.collect()

try:
    print("Fetching tank data...")
    data = fetch_tank_data()
    print("Data fetched: temp={}F roller={}% days={}".format(data.get("temp_f"), data.get("roller_pct"), data.get("roller_days")))
except Exception as e:
    print("API error: {} — rebooting in 30s...".format(e))
    render_error("API Error", str(e))
    graphics.update()
    time.sleep(30)
    machine.reset()

# Set initial button states from actual device/API data
btn_states["A"] = False  # Water change not running
btn_states["B"] = data.get("auto_fill", False)
btn_states["C"] = data.get("return_schedule", True)
btn_states["D"] = data.get("skimmer_schedule", True)  # True = on
btn_states["E"] = data.get("emergency_active", False)
print("Initial btn_states: {}".format(btn_states))

print("Rendering...")
gc.collect()
render_dashboard(data)
gc.collect()

print("Updating display...")
graphics.update()
print("Done! Polling buttons for {} min...".format(REFRESH_MINUTES))

# Poll buttons until refresh time
import inky_frame
buttons = [
    ("A", inky_frame.button_a),
    ("B", inky_frame.button_b),
    ("C", inky_frame.button_c),
    ("D", inky_frame.button_d),
    ("E", inky_frame.button_e),
]
deadline = time.time() + REFRESH_MINUTES * 60
while time.time() < deadline:
    pressed = False
    for key, btn in buttons:
        if btn.read():
            if key == "A":
                _a_count = getattr(run_water_change, '_count', 0) + 1
                _a_now = time.time()
                _a_last = getattr(run_water_change, '_last', 0)
                # Reset count if more than 5s since last press
                if _a_now - _a_last > 5:
                    _a_count = 1
                run_water_change._count = _a_count
                run_water_change._last = _a_now
                if _a_count < 3:
                    print("Button A press {}/3 — press {} more within 5s".format(_a_count, 3 - _a_count))
                    btn_a_label = "W/C {}/3".format(_a_count)
                    pressed = True
                    continue
                # 3 presses confirmed — reset and start
                run_water_change._count = 0
                btn_a_label = "10m W/C"
                print("Button A confirmed — starting water change")
                try:
                    run_water_change(data)
                except Exception as e:
                    print("Water change error: {}".format(e))
                pressed = True
                continue
            btn_states[key] = not btn_states[key]
            on = btn_states[key]
            print("Button {} pressed -> {}".format(key, on))
            try:
                if key == "B":
                    import ujson as _uj
                    _body = _uj.dumps({"auto_fill": on})
                    _hdrs = {"Authorization": "Bearer " + _token, "Content-Type": "application/json"}
                    _r = urequests.put(BASE_URL + "/reef-ato/{}/configuration".format(_ato_hwid), data=_body, headers=_hdrs)
                    print("ATO auto_fill={} -> {}".format(on, _r.json()))
                    _r.close()
                elif key == "C":
                    import ujson
                    headers = {"Authorization": "Bearer " + _token, "Content-Type": "application/json"}
                    if on:
                        body = ujson.dumps({"pump_1": {"schedule_enabled": True}})
                        r = urequests.put(BASE_URL + "/v2/reef-run/{}/pump/settings".format(_pump_hwid), data=body, headers=headers)
                        print("Return pump on -> {}".format(r.json()))
                        r.close()
                    else:
                        body = ujson.dumps({"pump_1": {"schedule_enabled": False}})
                        r = urequests.put(BASE_URL + "/v2/reef-run/{}/pump/settings".format(_pump_hwid), data=body, headers=headers)
                        print("Return pump off -> {}".format(r.json()))
                        r.close()
                elif key == "D":
                    import ujson
                    headers = {"Authorization": "Bearer " + _token, "Content-Type": "application/json"}
                    if on:
                        # Resume/enable skimmer
                        api_post("/reef-run/{}/pump/2/reset-state".format(_pump_hwid))
                        body = ujson.dumps({"pump_2": {"schedule_enabled": True}})
                        r = urequests.put(BASE_URL + "/v2/reef-run/{}/pump/settings".format(_pump_hwid), data=body, headers=headers)
                        print("Skimmer on -> {}".format(r.json()))
                        r.close()
                    else:
                        # Turn skimmer off
                        body = ujson.dumps({"pump_2": {"schedule_enabled": False}})
                        r = urequests.put(BASE_URL + "/v2/reef-run/{}/pump/settings".format(_pump_hwid), data=body, headers=headers)
                        print("Skimmer off -> {}".format(r.json()))
                        r.close()
                elif key == "E":
                    action = "start" if on else "stop"
                    api_post("/aquarium/{}/shortcut/emergency_1/{}".format(_aquarium_uid, action))
            except Exception as e:
                print("Button {} API error: {}".format(key, e))
            pressed = True
    # Reset W/C confirm label if it's been idle for 5s
    _a_count = getattr(run_water_change, '_count', 0)
    if _a_count > 0 and time.time() - getattr(run_water_change, '_last', 0) > 5:
        run_water_change._count = 0
        btn_a_label = "10m W/C"
        pressed = True  # trigger re-render
        print("W/C confirm timed out — reset")
    if pressed:
        gc.collect()
        render_dashboard(data)
        gc.collect()
        graphics.update()
        print("Display updated after button press")
        time.sleep(1)
    else:
        time.sleep(0.2)

del data
gc.collect()
# Reboot for fresh data cycle
machine.reset()
