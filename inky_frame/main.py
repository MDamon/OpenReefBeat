"""OpenReefBeat — Inky Frame 7.3" Dashboard

Connects to WiFi, fetches live data from the ReefBeat cloud API,
and renders a tank dashboard on the Pimoroni Inky Frame 7.3" e-ink display.

Copy this file and config.py to your Inky Frame via Thonny or USB.
"""

import gc
import math
import time
import json
import network
import urequests
from picographics import PicoGraphics, DISPLAY_INKY_FRAME_7 as DISPLAY
from config import *

# ── Display setup ───────────────────────────────────────────
WIDTH = 800
HEIGHT = 480
graphics = PicoGraphics(DISPLAY)

# Colors (Spectra 6 palette)
WHITE = graphics.create_pen(255, 255, 255)
BLACK = graphics.create_pen(0, 0, 0)
BLUE = graphics.create_pen(0, 0, 255)
GREEN = graphics.create_pen(0, 255, 0)
RED = graphics.create_pen(255, 0, 0)
YELLOW = graphics.create_pen(255, 255, 0)

# Layout constants
HEADER_H = 44
LEFT_W = 252
PAD = 16

# Gauge columns (centers)
COL1 = 345   # Lights
COL2 = 525   # Pumps
COL3 = 705   # Waves
GAUGE_R = 44
GAUGE_THICK = 8
TOP_GAUGE_Y = 152
BOT_GAUGE_Y = 320


# ── WiFi ────────────────────────────────────────────────────
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        return True
    wlan.connect(SSID, PASSWORD)
    for _ in range(30):
        if wlan.isconnected():
            return True
        time.sleep(1)
    return False


# ── ReefBeat API ────────────────────────────────────────────
BASE_URL = "https://cloud.thereefbeat.com"
_token = None


def api_login():
    global _token
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": "Basic " + CLIENT_CREDENTIALS,
    }
    body = "grant_type=password&username={}&password={}".format(USERNAME, REEFBEAT_PASSWORD)
    r = urequests.post(BASE_URL + "/oauth/token", data=body, headers=headers)
    data = r.json()
    r.close()
    gc.collect()
    _token = data["access_token"]


def api_get(path):
    headers = {"Authorization": "Bearer " + _token}
    r = urequests.get(BASE_URL + path, headers=headers)
    data = r.json()
    r.close()
    gc.collect()
    return data


def fetch_tank_data():
    """Fetch all data needed for the dashboard. Returns a dict."""
    api_login()

    dashboard = api_get("/aquarium/{}/dashboard".format(AQUARIUM_UID))
    gc.collect()
    ato = api_get("/reef-ato/{}/dashboard".format(ATO_HWID))
    gc.collect()
    pumps = api_get("/reef-run/{}/dashboard".format(PUMP_HWID))
    gc.collect()

    # Extract fields we need
    ato_sensor = ato.get("ato_sensor", {})
    temp_c = ato_sensor.get("current_read")
    temp_f = round(temp_c * 9 / 5 + 32, 1) if temp_c else None

    # Lights (use first light)
    lights = dashboard.get("reef_lights", [])
    light = lights[0].get("specific", {}) if lights else {}
    manual = light.get("manual", {})

    # Waves
    waves = dashboard.get("reef_wave", [])

    # Roller / ReefMat
    mats = dashboard.get("reef_mat", [])
    mat = mats[0].get("specific", {}) if mats else {}

    p1 = pumps.get("pump_1", {})
    p2 = pumps.get("pump_2", {})

    return {
        "temp_f": temp_f,
        "level": ato_sensor.get("current_level", "?"),
        "leak": ato.get("leak_sensor", {}).get("status", "?"),
        "ato_vol_ml": ato.get("today_volume_usage", 0),
        "ato_fills": ato.get("today_fills", 0),
        "auto_fill": ato.get("auto_fill", False),
        "light_pct": manual.get("intensity", 0),
        "light_kelvin": manual.get("kelvin", 0),
        "moon_pct": manual.get("moon", 0),
        "return_pct": p1.get("intensity", 0),
        "return_state": p1.get("state", "?"),
        "skimmer_pct": p2.get("intensity", 0),
        "skimmer_state": p2.get("state", "?"),
        "skimmer_sensor": p2.get("sensor_controlled", False),
        "wave_l_pct": waves[1].get("specific", {}).get("active_wave", {}).get("fti", 0) if len(waves) > 1 else 0,
        "wave_r_pct": waves[0].get("specific", {}).get("active_wave", {}).get("fti", 0) if waves else 0,
        "wave_program": waves[0].get("specific", {}).get("active_wave", {}).get("name", "") if waves else "",
        "roller_pct": mat.get("mat_used_pct", 0),
        "roller_days": mat.get("days_remaining", None),
    }


# ── Drawing helpers ─────────────────────────────────────────
def draw_arc(cx, cy, radius, start_deg, arc_deg, thickness):
    """Draw an arc starting from start_deg, spanning arc_deg degrees clockwise."""
    for deg in range(arc_deg):
        angle = (start_deg + deg) % 360
        rad = math.radians(angle)
        c = math.cos(rad)
        s = math.sin(rad)
        for t in range(thickness):
            r = radius - t
            graphics.pixel(int(cx + r * c), int(cy + r * s))


def draw_gauge(cx, cy, pct, color, label, sub_label=""):
    """Draw a circular arc gauge with percentage and label."""
    r = GAUGE_R

    # Track circle (thin black outline)
    graphics.set_pen(BLACK)
    draw_arc(cx, cy, r, 0, 360, 2)
    draw_arc(cx, cy, r - GAUGE_THICK + 1, 0, 360, 1)

    # Colored fill arc (clockwise from top = 270 degrees in math coords)
    if pct > 0:
        graphics.set_pen(color)
        arc_len = int(360 * min(pct, 100) / 100)
        draw_arc(cx, cy, r - 2, 270, arc_len, GAUGE_THICK - 3)

    # Center text
    graphics.set_pen(BLACK)
    graphics.set_font("sans")
    graphics.set_thickness(2)
    val_text = str(int(pct))
    tw = graphics.measure_text(val_text, scale=0.7)
    graphics.text(val_text, cx - tw // 2 - 4, cy - 14, scale=0.7)
    graphics.set_thickness(1)
    graphics.text("%", cx + tw // 2 - 2, cy - 10, scale=0.35)

    # Label below gauge
    graphics.set_font("bitmap8")
    lw = graphics.measure_text(label, scale=2)
    graphics.text(label, cx - lw // 2, cy + r + 8, scale=2)

    # Sub-label
    if sub_label:
        sw = graphics.measure_text(sub_label, scale=1)
        graphics.text(sub_label, cx - sw // 2, cy + r + 28, scale=1)


def draw_dot(x, y, color, radius=5):
    graphics.set_pen(color)
    graphics.circle(x, y, radius)


def draw_progress_bar(x, y, w, h, pct, color):
    graphics.set_pen(BLACK)
    graphics.rectangle(x, y, w, h)
    graphics.set_pen(WHITE)
    graphics.rectangle(x + 1, y + 1, w - 2, h - 2)
    fill_w = int((w - 2) * min(pct, 100) / 100)
    if fill_w > 0:
        graphics.set_pen(color)
        graphics.rectangle(x + 1, y + 1, fill_w, h - 2)


# ── Dashboard renderer ──────────────────────────────────────
def render_dashboard(data):
    graphics.set_pen(WHITE)
    graphics.clear()

    # ── Header bar ──────────────────────────────────────
    graphics.set_pen(BLUE)
    graphics.rectangle(0, 0, WIDTH, HEADER_H)
    graphics.set_pen(WHITE)
    graphics.set_font("sans")
    graphics.set_thickness(2)
    graphics.text("OpenReefBeat", PAD, 10, scale=0.5)
    graphics.set_thickness(1)
    t = time.localtime()
    ts = "{:02d}/{:02d} {:02d}:{:02d}".format(t[1], t[2], t[3], t[4])
    tw = graphics.measure_text(ts, scale=0.4)
    graphics.text(ts, WIDTH - PAD - tw, 14, scale=0.4)

    # ── Vertical divider ────────────────────────────────
    graphics.set_pen(BLACK)
    graphics.line(LEFT_W, HEADER_H, LEFT_W, HEIGHT)

    # ── LEFT PANEL ──────────────────────────────────────
    lx = PAD
    y = HEADER_H + 20

    # Temperature (hero number)
    temp = data.get("temp_f")
    if temp is not None:
        graphics.set_pen(BLACK)
        graphics.set_font("sans")
        graphics.set_thickness(4)
        temp_str = str(temp)
        graphics.text(temp_str, lx, y, scale=1.3)
        tw = graphics.measure_text(temp_str, scale=1.3)
        graphics.set_thickness(1)
        graphics.text("F", lx + tw + 6, y + 8, scale=0.55)
        # Degree circle
        graphics.circle(lx + tw + 2, y + 10, 3)
    else:
        graphics.set_pen(RED)
        graphics.set_font("sans")
        graphics.set_thickness(3)
        graphics.text("--.-", lx, y, scale=1.3)

    # Water level status
    y += 70
    level = data.get("level", "?")
    level_color = GREEN if level == "desired" else RED
    draw_dot(lx + 6, y + 6, level_color, 5)
    graphics.set_pen(BLACK)
    graphics.set_font("bitmap14_outline")
    graphics.text(level.upper(), lx + 18, y - 2, scale=1)

    # Separator
    y += 28
    graphics.set_pen(BLACK)
    graphics.line(lx, y, LEFT_W - PAD, y)

    # ATO section
    y += 14
    graphics.set_pen(BLUE)
    graphics.set_font("sans")
    graphics.set_thickness(2)
    graphics.text("ATO", lx, y, scale=0.45)

    y += 28
    graphics.set_pen(BLACK)
    graphics.set_font("bitmap8")
    vol_gal = round(data.get("ato_vol_ml", 0) / 3785.41, 2)
    graphics.text("{} gal today".format(vol_gal), lx, y, scale=2)

    y += 22
    fills = data.get("ato_fills", 0)
    auto = "ON" if data.get("auto_fill") else "OFF"
    graphics.text("{} fills - Auto {}".format(fills, auto), lx, y, scale=2)

    y += 22
    leak = data.get("leak", "?")
    leak_color = GREEN if leak == "dry" else RED
    graphics.text("Leak: {}".format(leak), lx, y, scale=2)
    draw_dot(lx + graphics.measure_text("Leak: " + leak, scale=2) + 10, y + 6, leak_color, 4)

    # Separator
    y += 30
    graphics.set_pen(BLACK)
    graphics.line(lx, y, LEFT_W - PAD, y)

    # Roller section
    y += 14
    graphics.set_pen(BLUE)
    graphics.set_font("sans")
    graphics.set_thickness(2)
    graphics.text("Roller", lx, y, scale=0.45)

    y += 28
    graphics.set_pen(BLACK)
    graphics.set_font("bitmap8")
    roller_pct = data.get("roller_pct", 0)
    roller_days = data.get("roller_days")
    if roller_pct > 0:
        draw_progress_bar(lx, y, LEFT_W - PAD * 2, 16, roller_pct, YELLOW)
        y += 24
        if roller_days is not None:
            days_color = RED if roller_days <= 2 else BLACK
            graphics.set_pen(days_color)
            graphics.text("{} days remaining".format(roller_days), lx, y, scale=2)
        else:
            graphics.text("{}% used".format(int(roller_pct)), lx, y, scale=2)
    else:
        graphics.text("No data", lx, y, scale=2)

    # ── RIGHT PANEL — Column headers ────────────────────
    hy = HEADER_H + 12
    graphics.set_pen(BLUE)
    graphics.set_font("sans")
    graphics.set_thickness(2)
    for cx, label in [(COL1, "Lights"), (COL2, "Pumps"), (COL3, "Waves")]:
        tw = graphics.measure_text(label, scale=0.4)
        graphics.text(label, cx - tw // 2, hy, scale=0.4)

    # ── RIGHT PANEL — Top row gauges ────────────────────
    draw_gauge(COL1, TOP_GAUGE_Y, data.get("light_pct", 0), BLUE, "{}K".format(data.get("light_kelvin", 0) // 1000))
    draw_gauge(COL2, TOP_GAUGE_Y, data.get("return_pct", 0), BLUE, "Return")
    draw_gauge(COL3, TOP_GAUGE_Y, data.get("wave_l_pct", 0), BLUE, "Left")

    # ── RIGHT PANEL — Bottom row gauges ─────────────────
    draw_gauge(COL1, BOT_GAUGE_Y, data.get("moon_pct", 0), BLUE, "Moon")
    draw_gauge(COL2, BOT_GAUGE_Y, data.get("skimmer_pct", 0), BLUE, "Skimmer")
    draw_gauge(COL3, BOT_GAUGE_Y, data.get("wave_r_pct", 0), BLUE, "Right")

    # Skimmer sensor dot
    if data.get("skimmer_sensor"):
        graphics.set_pen(BLACK)
        graphics.set_font("bitmap8")
        tw = graphics.measure_text("Sensor", scale=1)
        sx = COL2 - tw // 2 - 8
        sy = BOT_GAUGE_Y + GAUGE_R + 48
        graphics.text("Sensor", sx + 12, sy, scale=1)
        draw_dot(sx + 4, sy + 4, GREEN, 3)

    # Wave program name
    prog = data.get("wave_program", "")
    if prog:
        graphics.set_pen(BLACK)
        graphics.set_font("bitmap8")
        tw = graphics.measure_text(prog, scale=1)
        graphics.text(prog, COL3 - tw // 2, BOT_GAUGE_Y + GAUGE_R + 48, scale=1)

    # ── Footer — alerts ─────────────────────────────────
    graphics.set_pen(BLACK)
    graphics.line(LEFT_W + PAD, HEIGHT - 36, WIDTH - PAD, HEIGHT - 36)
    graphics.set_font("bitmap8")
    status_text = "All systems operational"
    leak = data.get("leak", "dry")
    level = data.get("level", "desired")
    if leak != "dry":
        status_text = "LEAK DETECTED"
        graphics.set_pen(RED)
    elif level != "desired":
        status_text = "Water level: " + level
        graphics.set_pen(RED)
    else:
        graphics.set_pen(BLACK)
    graphics.text(status_text, LEFT_W + PAD + 4, HEIGHT - 28, scale=2)


def render_error(title, detail=""):
    """Render an error screen."""
    graphics.set_pen(WHITE)
    graphics.clear()

    # Red banner
    graphics.set_pen(RED)
    graphics.rectangle(0, 0, WIDTH, HEADER_H)
    graphics.set_pen(WHITE)
    graphics.set_font("sans")
    graphics.set_thickness(2)
    graphics.text("OpenReefBeat - ERROR", PAD, 10, scale=0.5)

    # Error icon (big X)
    cx, cy = WIDTH // 2, 180
    graphics.set_pen(RED)
    graphics.set_font("sans")
    graphics.set_thickness(5)
    graphics.text("!", cx - 15, cy - 60, scale=2.5)

    # Title
    graphics.set_pen(BLACK)
    graphics.set_thickness(3)
    tw = graphics.measure_text(title, scale=0.7)
    graphics.text(title, cx - tw // 2, cy + 40, scale=0.7)

    # Detail
    if detail:
        graphics.set_thickness(1)
        dw = graphics.measure_text(detail, scale=0.4)
        graphics.text(detail, cx - dw // 2, cy + 90, scale=0.4)

    # Instructions
    graphics.set_font("bitmap8")
    msg = "Check WiFi and config.py settings"
    mw = graphics.measure_text(msg, scale=2)
    graphics.text(msg, cx - mw // 2, cy + 140, scale=2)


# ── Main loop ───────────────────────────────────────────────
def main():
    print("OpenReefBeat starting...")

    # Connect WiFi
    print("Connecting to WiFi: {}".format(SSID))
    if not connect_wifi():
        print("WiFi failed!")
        render_error("WiFi Connection Failed", "Could not connect to " + SSID)
        graphics.update()
        time.sleep(60)
        return

    print("WiFi connected")

    # Fetch data
    try:
        print("Fetching tank data...")
        data = fetch_tank_data()
        print("Data fetched: temp={}F".format(data.get("temp_f")))
    except Exception as e:
        print("API error: {}".format(e))
        render_error("API Error", str(e))
        graphics.update()
        time.sleep(60)
        return

    # Render dashboard
    print("Rendering dashboard...")
    render_dashboard(data)

    # Update display
    print("Updating display (this takes ~30 seconds)...")
    graphics.update()
    print("Done! Sleeping for {} minutes.".format(REFRESH_MINUTES))

    # Deep sleep
    try:
        import inky_frame
        inky_frame.sleep_for(REFRESH_MINUTES)
    except ImportError:
        # Not on real hardware, just wait
        time.sleep(REFRESH_MINUTES * 60)


# Run
main()
