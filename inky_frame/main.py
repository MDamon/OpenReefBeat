"""OpenReefBeat — Inky Frame 7.3" Dashboard"""

import gc
import time
import urequests
import ntptime
import inky_helper as ih
from picographics import PicoGraphics, DISPLAY_INKY_FRAME_7 as DISPLAY
from config import *

gc.collect()

# ── Display setup ───────────────────────────────────────────
WIDTH = 800
HEIGHT = 480
graphics = PicoGraphics(DISPLAY)

WHITE = graphics.create_pen(255, 255, 255)
BLACK = graphics.create_pen(0, 0, 0)
BLUE = graphics.create_pen(0, 0, 255)
GREEN = graphics.create_pen(0, 64, 0)
RED = graphics.create_pen(255, 0, 0)
YELLOW = graphics.create_pen(255, 255, 0)

HEADER_H = 44
LEFT_W = 280
PAD = 16

gc.collect()


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
            gc.collect()
            time.sleep(2)
    raise OSError("API failed after 3 retries")


def fetch_tank_data():
    api_login()
    gc.collect()

    aquariums = api_get("/aquarium")
    if not aquariums:
        raise RuntimeError("No aquariums found")
    uid = aquariums[0]["uid"]
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
    runs = dashboard.get("reef_run", [])
    if runs:
        pump_hwid = runs[0]["common"]["hwid"]

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
        result["skimmer_pct"] = p2.get("intensity", 0)
        result["skimmer_sensor"] = p2.get("sensor_controlled", False)
        del pumps, p1, p2
    gc.collect()

    return result


# ── Drawing helpers ─────────────────────────────────────────
def draw_bar(x, y, w, h, pct, color):
    graphics.set_pen(BLACK)
    graphics.rectangle(x, y, w, h)
    graphics.set_pen(WHITE)
    graphics.rectangle(x + 1, y + 1, w - 2, h - 2)
    fill_w = int((w - 2) * min(pct, 100) / 100)
    if fill_w > 0:
        graphics.set_pen(color)
        graphics.rectangle(x + 1, y + 1, fill_w, h - 2)


def draw_row(x, y, label, pct, color, label_w=130):
    """Draw labeled bar filling available width."""
    graphics.set_pen(BLACK)
    graphics.set_font("bitmap8")
    graphics.text(label, x, y + 4, label_w, scale=2)
    bar_x = x + label_w
    bar_w = WIDTH - bar_x - PAD - 60
    draw_bar(bar_x, y, bar_w, 24, pct, color)
    graphics.set_pen(BLACK)
    graphics.text("{}%".format(int(pct)), bar_x + bar_w + 8, y + 4, 60, scale=2)
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
    elif level != "desired":
        status_text = "[!!] Level: {}".format(level)
        header_color = RED
    else:
        status_text = "All systems operational"
        header_color = BLUE

    # Header: tank name | status | date/time
    HSCALE = 3
    graphics.set_pen(header_color)
    graphics.rectangle(0, 0, WIDTH, HEADER_H)
    graphics.set_pen(WHITE)
    graphics.set_font("bitmap8")
    tank = data.get("tank_name", "")
    graphics.text(tank, PAD, 10, WIDTH, scale=HSCALE)
    t = time.localtime()
    ts = "{:02d}/{:02d} {:02d}:{:02d}".format(t[1], t[2], t[3], t[4])
    tw = graphics.measure_text(ts, scale=HSCALE)
    graphics.text(ts, WIDTH - PAD - tw, 10, WIDTH, scale=HSCALE)
    sw = graphics.measure_text(status_text, scale=HSCALE)
    graphics.text(status_text, WIDTH // 2 - sw // 2, 10, WIDTH, scale=HSCALE)
    gc.collect()

    # Divider
    graphics.set_pen(BLACK)
    graphics.line(LEFT_W, HEADER_H, LEFT_W, HEIGHT)

    # LEFT PANEL
    lx = PAD
    y = HEADER_H + 16

    # Temperature
    temp = data.get("temp_f")
    graphics.set_pen(BLACK)
    graphics.set_font("bitmap8")
    if temp is not None:
        graphics.text("{}F".format(temp), lx, y, LEFT_W - PAD * 2, scale=6)
    else:
        graphics.set_pen(RED)
        graphics.text("--.-F", lx, y, LEFT_W - PAD * 2, scale=6)
    gc.collect()

    # Water level
    y += 64
    level = data.get("level", "?")
    graphics.set_pen(BLACK)
    graphics.set_font("bitmap8")
    if level == "desired":
        graphics.text("Level: {}".format(level), lx, y + 2, LEFT_W - PAD * 2, scale=2)
    else:
        graphics.set_pen(RED)
        graphics.text("[!!] Level: {}".format(level), lx, y + 2, LEFT_W - PAD * 2, scale=2)

    y += 30
    graphics.set_pen(BLACK)
    graphics.line(lx, y, LEFT_W - PAD, y)

    # ATO
    y += 10
    graphics.set_pen(BLUE)
    graphics.set_font("bitmap8")
    graphics.text("ATO", lx, y, LEFT_W - PAD * 2, scale=3)

    y += 28
    graphics.set_pen(BLACK)
    vol_gal = round(data.get("ato_vol_ml", 0) / 3785.41, 2)
    graphics.text("{} gal today".format(vol_gal), lx, y, scale=2)

    y += 22
    fills = data.get("ato_fills", 0)
    auto = "ON" if data.get("auto_fill") else "OFF"
    graphics.text("{} fills / Auto {}".format(fills, auto), lx, y, scale=2)

    y += 22
    leak = data.get("leak", "?")
    if leak == "dry":
        graphics.set_pen(BLACK)
        graphics.text("Leak: {}".format(leak), lx, y, LEFT_W - PAD * 2, scale=2)
    else:
        graphics.set_pen(RED)
        graphics.text("[!!] Leak: {}".format(leak), lx, y, LEFT_W - PAD * 2, scale=2)
    gc.collect()

    y += 30
    graphics.set_pen(BLACK)
    graphics.line(lx, y, LEFT_W - PAD, y)

    # Roller
    y += 10
    graphics.set_pen(BLUE)
    graphics.set_font("bitmap8")
    graphics.text("Roller", lx, y, LEFT_W - PAD * 2, scale=3)

    y += 28
    graphics.set_pen(BLACK)
    graphics.set_font("bitmap8")
    roller_pct = data.get("roller_pct", 0)
    roller_days = data.get("roller_days")
    roller_level = data.get("roller_level", "")
    bar_color = RED if roller_level == "running_low" else BLUE
    print("RENDER roller: pct={} days={} level={}".format(roller_pct, roller_days, roller_level))
    if roller_pct > 0.1:
        bar_w = LEFT_W - PAD * 2
        # Draw bar explicitly
        graphics.set_pen(BLACK)
        graphics.rectangle(lx, y, bar_w, 20)
        graphics.set_pen(WHITE)
        graphics.rectangle(lx + 1, y + 1, bar_w - 2, 18)
        fill_w = int((bar_w - 2) * roller_pct / 100)
        print("RENDER bar: fill_w={} bar_w={} color={}".format(fill_w, bar_w, bar_color))
        if fill_w > 0:
            graphics.set_pen(bar_color)
            graphics.rectangle(lx + 1, y + 1, fill_w, 18)
        y += 26
        graphics.set_pen(BLACK)
        graphics.text("{}% used".format(int(roller_pct)), lx, y, LEFT_W, scale=2)
        if roller_days is not None:
            y += 18
            graphics.set_pen(RED if roller_days <= 5 else BLACK)
            graphics.text("{} days remaining".format(roller_days), lx, y, LEFT_W, scale=2)
    else:
        print("RENDER roller: showing No data")
        graphics.text("No data", lx, y, LEFT_W, scale=2)
    gc.collect()

    # RIGHT PANEL — fill the space
    rx = LEFT_W + PAD
    rw = WIDTH - LEFT_W - PAD * 2
    y = HEADER_H + 14

    # Lights
    graphics.set_pen(BLUE)
    graphics.set_font("bitmap8")
    graphics.text("Lights", rx, y, rw, scale=3)
    y += 32
    draw_row(rx, y, "Intensity", data.get("light_pct", 0), BLUE)
    y += 34
    draw_row(rx, y, "Moon", data.get("moon_pct", 0), BLUE)
    y += 46

    # Pumps
    graphics.set_pen(BLUE)
    graphics.text("Pumps", rx, y, rw, scale=3)
    y += 32
    draw_row(rx, y, "Return", data.get("return_pct", 0), BLUE)
    y += 34
    draw_row(rx, y, "Skimmer", data.get("skimmer_pct", 0), BLUE)
    y += 46

    # Waves
    graphics.set_pen(BLUE)
    graphics.set_font("bitmap8")
    graphics.text("Waves", rx, y, rw, scale=3)
    prog = data.get("wave_program", "")
    if prog:
        graphics.set_pen(BLACK)
        graphics.text(prog, rx + 140, y + 6, rw, scale=2)
    y += 32
    draw_row(rx, y, "Left", data.get("wave_l_pct", 0), BLUE)
    y += 34
    draw_row(rx, y, "Right", data.get("wave_r_pct", 0), BLUE)
    gc.collect()

    # Branding
    graphics.set_pen(BLACK)
    graphics.set_font("bitmap8")
    bw = graphics.measure_text("OpenReefBeat", scale=1)
    graphics.text("OpenReefBeat", WIDTH - PAD - bw, HEIGHT - 16, WIDTH, scale=1)



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


# ── Main ────────────────────────────────────────────────────
print("OpenReefBeat starting...")
gc.collect()

# WiFi — retry full connection cycle up to 3 times
import network
wlan = network.WLAN(network.STA_IF)

for wifi_attempt in range(3):
    print("WiFi attempt {}...".format(wifi_attempt + 1))
    wlan.active(False)
    time.sleep(1)
    wlan.active(True)
    wlan.config(pm=0xa11140)
    wlan.connect(SSID, PASSWORD)
    for _ in range(60):
        if wlan.isconnected():
            break
        time.sleep(1)
    if wlan.isconnected():
        break
    print("WiFi attempt {} failed, retrying...".format(wifi_attempt + 1))

if not wlan.isconnected():
    print("WiFi failed!")
    render_error("WiFi Failed", SSID)
    graphics.update()
    ih.sleep(REFRESH_MINUTES)
else:
    print("WiFi connected")

    # Sync clock via NTP
    try:
        ntptime.settime()
        print("NTP time synced")
    except Exception:
        print("NTP sync failed (clock may be wrong)")
    gc.collect()

    try:
        print("Fetching tank data...")
        data = fetch_tank_data()
        print("Data fetched: temp={}F roller={}% days={}".format(data.get("temp_f"), data.get("roller_pct"), data.get("roller_days")))
    except Exception as e:
        print("API error: {}".format(e))
        render_error("API Error", str(e))
        graphics.update()
        ih.sleep(REFRESH_MINUTES)
        data = None

    if data:
        print("Rendering...")
        gc.collect()
        render_dashboard(data)
        del data
        gc.collect()

        print("Updating display...")
        graphics.update()
        print("Done! Sleeping {} min.".format(REFRESH_MINUTES))
        ih.sleep(REFRESH_MINUTES)
