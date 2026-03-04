#!/usr/bin/env python3
"""Preview renderer — generates a dashboard PNG on Mac/Linux using PIL.

Mirrors the Inky Frame layout so you can preview without hardware.

Usage:
    python3 display.py              # Renders from data/snapshot.json
    python3 display.py --error      # Renders error screen
    open data/dashboard.png         # View the result
"""

import json
import math
import os
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ── Display constants ───────────────────────────────────────
WIDTH = 800
HEIGHT = 480

# E-ink palette (Spectra 6)
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
BLUE = (0, 0, 255)
GREEN = (0, 255, 0)
RED = (255, 0, 0)
YELLOW = (255, 255, 0)
LIGHT_GRAY = (200, 200, 200)

# Layout
HEADER_H = 44
LEFT_W = 280
PAD = 16
GAUGE_R = 50
GAUGE_THICK = 15
BTN_H = 44
# Right panel columns — 3 equal sections for Lights, Pumps, Waves
RIGHT_W = WIDTH - LEFT_W
COL1_CX = LEFT_W + RIGHT_W // 6       # Lights
COL2_CX = LEFT_W + RIGHT_W // 2       # Pumps
COL3_CX = LEFT_W + 5 * RIGHT_W // 6   # Waves
TOP_Y = HEADER_H + 14
TOP_GAUGE_Y = TOP_Y + 50 + GAUGE_R + 10
BOT_GAUGE_Y = TOP_GAUGE_Y + GAUGE_R * 2 + 70

DATA_DIR = Path(__file__).parent / "data"
HISTORY_FILE = DATA_DIR / "history.jsonl"


# ── Fonts ───────────────────────────────────────────────────
def _font(size, bold=False):
    style = "Bold" if bold else ""
    paths = [
        f"/usr/share/fonts/truetype/dejavu/DejaVuSans-{style}.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


FONT_TEMP = _font(52, bold=True)
FONT_UNIT = _font(22)
FONT_HEADING = _font(16, bold=True)
FONT_HEADER = _font(16, bold=True)
FONT_HEADER_SM = _font(13)
FONT_GAUGE_VAL = _font(26, bold=True)
FONT_GAUGE_PCT = _font(13)
FONT_LABEL = _font(13)
FONT_SMALL = _font(11)
FONT_STATUS = _font(13)
FONT_ERR_TITLE = _font(32, bold=True)
FONT_ERR_DETAIL = _font(16)
FONT_ERR_HINT = _font(13)


def _tw(draw, text, font):
    try:
        return draw.textlength(text, font=font)
    except AttributeError:
        return font.getsize(text)[0]


# ── Drawing helpers ─────────────────────────────────────────
def draw_gauge(draw, cx, cy, pct, fill_color, label, sub_label=""):
    """Draw a smooth circular gauge using PIL ellipse arcs."""
    r = GAUGE_R
    t = GAUGE_THICK

    # Background track — light gray filled ring
    outer = [cx - r, cy - r, cx + r, cy + r]
    inner_r = r - t
    inner = [cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r]

    # Draw full track ring (light gray)
    draw.ellipse(outer, outline=LIGHT_GRAY, width=t)

    # Draw filled arc — PIL arc uses angles where 0=3 o'clock, going clockwise
    # We want to start from top (270 degrees in PIL coords)
    if pct > 0:
        arc_end = 270 + int(360 * min(pct, 100) / 100)
        # Draw thick arc by drawing multiple concentric arcs
        for i in range(t):
            ri = r - i
            box = [cx - ri, cy - ri, cx + ri, cy + ri]
            draw.arc(box, start=270, end=arc_end, fill=fill_color, width=1)

    # Outer circle border
    draw.ellipse(outer, outline=BLACK, width=2)
    # Inner circle border
    draw.ellipse(inner, outline=BLACK, width=2)

    # Center value text
    val = str(int(pct))
    vw = _tw(draw, val, FONT_GAUGE_VAL)
    pw = _tw(draw, "%", FONT_GAUGE_PCT)
    total = vw + pw + 2
    draw.text((cx - total / 2, cy - 15), val, fill=BLACK, font=FONT_GAUGE_VAL)
    draw.text((cx - total / 2 + vw + 2, cy - 7), "%", fill=BLACK, font=FONT_GAUGE_PCT)

    # Label below
    lw = _tw(draw, label, FONT_LABEL)
    draw.text((cx - lw / 2, cy + r + 8), label, fill=BLACK, font=FONT_LABEL)

    # Sub-label
    if sub_label:
        sw = _tw(draw, sub_label, FONT_SMALL)
        draw.text((cx - sw / 2, cy + r + 24), sub_label, fill=BLACK, font=FONT_SMALL)


def draw_dot(draw, x, y, color, radius=5):
    draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=color)


def draw_progress_bar(draw, x, y, w, h, pct, color):
    # Rounded-ish bar with fill
    draw.rounded_rectangle([x, y, x + w, y + h], radius=h // 2, outline=BLACK, width=1)
    fill_w = int((w - 2) * min(pct, 100) / 100)
    if fill_w > h:
        draw.rounded_rectangle([x + 1, y + 1, x + fill_w, y + h - 1],
                               radius=(h - 2) // 2, fill=color)


def draw_sparkline(draw, x, y, w, h, values, color=BLUE):
    """Draw a small line chart (sparkline) from a list of values."""
    if not values or len(values) < 2:
        return
    mn = min(values)
    mx = max(values)
    rng = mx - mn if mx != mn else 1

    # Draw light horizontal midline
    mid_y = y + h // 2
    draw.line([x, mid_y, x + w, mid_y], fill=LIGHT_GRAY, width=1)

    # Plot points and lines
    pts = []
    for i, v in enumerate(values):
        px = x + int(i * w / (len(values) - 1))
        py = y + h - int((v - mn) * h / rng)
        pts.append((px, py))

    # Draw line segments
    for i in range(len(pts) - 1):
        draw.line([pts[i], pts[i + 1]], fill=color, width=2)

    # Min/max labels
    mn_str = f"{mn:.1f}"
    mx_str = f"{mx:.1f}"
    draw.text((x + w + 4, y - 2), mx_str, fill=BLACK, font=_font(9))
    draw.text((x + w + 4, y + h - 10), mn_str, fill=BLACK, font=_font(9))


def load_temp_history(days=10, max_points=120):
    """Load recent temperature readings from history.jsonl, downsampled."""
    if not HISTORY_FILE.exists():
        return []
    import time
    cutoff = time.time() - days * 86400
    temps = []
    for line in HISTORY_FILE.read_text().strip().split("\n"):
        try:
            entry = json.loads(line)
            if entry.get("timestamp", 0) < cutoff:
                continue
            t = entry.get("temperature_f")
            if t is not None:
                temps.append(t)
        except (json.JSONDecodeError, KeyError):
            continue
    # Downsample if too many points
    if len(temps) > max_points:
        step = len(temps) / max_points
        temps = [temps[int(i * step)] for i in range(max_points)]
    return temps


# ── Dashboard ───────────────────────────────────────────────
def render_dashboard(data, temp_history=None, location=""):
    img = Image.new("RGB", (WIDTH, HEIGHT), WHITE)
    draw = ImageDraw.Draw(img)

    ts = data.get("timestamp", 0)
    now = datetime.now()
    date_str = now.strftime("%a %b %-d")
    time_str = now.strftime("%-I:%M %p")
    updated_ago = ""
    if ts:
        mins_ago = int((now.timestamp() - ts) / 60)
        if mins_ago < 1:
            updated_ago = "just now"
        elif mins_ago < 60:
            updated_ago = f"{mins_ago}m ago"
        else:
            updated_ago = f"{mins_ago // 60}h ago"

    # ── Header (matches Inky Frame: tank name | status | date/time) ──
    leak = data.get("leak_status", "dry")
    level = data.get("water_level", "desired")
    if leak != "dry":
        status_text, header_color = "LEAK DETECTED", RED
    elif level != "desired":
        status_text, header_color = f"Level: {level}", RED
    else:
        status_text, header_color = "All systems operational", BLUE

    draw.rectangle([0, 0, WIDTH, HEADER_H], fill=header_color)
    tank = data.get("tank_name", "")
    if not tank and location:
        tank = location
    draw.text((PAD, 12), tank, fill=WHITE, font=FONT_HEADER)

    # Status centered
    stw = _tw(draw, status_text, FONT_HEADER)
    draw.text((WIDTH // 2 - stw / 2, 12), status_text, fill=WHITE, font=FONT_HEADER)

    # Date/time right
    right_text = f"{date_str} {time_str}"
    rtw = _tw(draw, right_text, FONT_HEADER)
    draw.text((WIDTH - PAD - rtw, 12), right_text, fill=WHITE, font=FONT_HEADER)

    # ── Left/Right divider ────────────────────────────
    draw.line([LEFT_W, HEADER_H, LEFT_W, HEIGHT - BTN_H], fill=BLACK, width=1)

    # ── LEFT PANEL ────────────────────────────────────
    lx = PAD
    y = HEADER_H + 14

    # Temperature
    temp = data.get("temperature_f")
    if temp is not None:
        temp_str = str(temp)
        draw.text((lx, y), temp_str, fill=BLACK, font=FONT_TEMP)
        tw = _tw(draw, temp_str, FONT_TEMP)
        draw.text((lx + tw + 4, y + 6), "\u00b0F", fill=BLACK, font=FONT_UNIT)
    else:
        draw.text((lx, y), "--.-", fill=RED, font=FONT_TEMP)

    y += 62

    # Level
    level = data.get("water_level", "?")
    level_color = GREEN if level == "desired" else RED
    draw_dot(draw, lx + 6, y + 7, level_color, 5)
    draw.text((lx + 18, y), level.upper(), fill=BLACK, font=FONT_LABEL)

    # Separator
    y += 24
    draw.line([lx, y, LEFT_W - PAD, y], fill=LIGHT_GRAY, width=1)

    # ATO
    y += 10
    draw.text((lx, y), "ATO", fill=BLUE, font=FONT_HEADING)

    y += 22
    vol_ml = data.get("ato_volume_today_ml", 0)
    vol_gal = round(vol_ml / 3785.41, 2) if vol_ml else 0
    draw.text((lx, y), f"{vol_gal} gal today", fill=BLACK, font=FONT_LABEL)

    y += 18
    fills = data.get("ato_fills_today", 0)
    draw.text((lx, y), f"{fills} fills \u00b7 Auto-fill ON", fill=BLACK, font=FONT_LABEL)

    y += 18
    leak = data.get("leak_status", "?")
    leak_color = GREEN if leak == "dry" else RED
    draw.text((lx, y), f"Leak: {leak}", fill=BLACK, font=FONT_LABEL)
    lkw = _tw(draw, f"Leak: {leak}", FONT_LABEL)
    draw_dot(draw, lx + lkw + 12, y + 7, leak_color, 4)

    # Separator
    y += 26
    draw.line([lx, y, LEFT_W - PAD, y], fill=LIGHT_GRAY, width=1)

    # Roller
    y += 10
    draw.text((lx, y), "Roller", fill=BLUE, font=FONT_HEADING)

    y += 24
    roller = data.get("roller", {})
    used_pct = roller.get("used_pct", 0)
    days_left = roller.get("days_remaining", "?")
    remaining_m = roller.get("remaining_m", 0)
    total_m = roller.get("total_m", 0)
    used_ft = round(float(total_m - remaining_m) * 3.281, 1) if total_m else 0
    total_ft = round(float(total_m) * 3.281, 1) if total_m else 0
    roller_level = roller.get("level", "")
    bar_color = RED if roller_level == "running_low" else BLUE

    # Used/total in feet
    ft_text = f"{used_ft}ft / {total_ft}ft"
    ftw = _tw(draw, ft_text, FONT_LABEL)
    draw.text((LEFT_W - PAD - ftw, y - 20), ft_text, fill=BLACK, font=FONT_LABEL)

    draw_progress_bar(draw, lx, y, LEFT_W - PAD * 2, 14, used_pct, bar_color)
    y += 20
    # Today and average usage in inches
    today_in = round(roller.get("today_usage_cm", 0) / 2.54, 1)
    avg_in = round(roller.get("daily_avg_cm", 0) / 2.54, 1)
    draw.text((lx, y), f"Today: {today_in}in / Avg: {avg_in}in", fill=BLACK, font=FONT_LABEL)
    y += 16
    days_color = RED if isinstance(days_left, int) and days_left <= 5 else BLACK
    draw.text((lx, y), f"{days_left} days remaining", fill=days_color, font=FONT_LABEL)

    # Branding
    y += 20
    draw.line([lx, y, LEFT_W - PAD, y], fill=LIGHT_GRAY, width=1)
    y += 6
    draw.text((lx, y), "OpenReefBeat", fill=BLACK, font=FONT_SMALL)

    # ── RIGHT PANEL ───────────────────────────────────

    # Section headers
    hy = TOP_Y
    for cx, label in [(COL1_CX, "Lights"), (COL2_CX, "Pumps"), (COL3_CX, "Waves")]:
        tw = _tw(draw, label, FONT_HEADING)
        draw.text((cx - tw / 2, hy), label, fill=BLUE, font=FONT_HEADING)

    # Wave program under Waves header
    waves = data.get("waves", [])
    prog = waves[0].get("program", "") if waves else ""
    if prog:
        pw = _tw(draw, prog, FONT_SMALL)
        draw.text((COL3_CX - pw / 2, hy + 22), prog, fill=BLACK, font=FONT_SMALL)

    # ── Gauges — Top row ──────────────────────────────
    lights = data.get("lights", [{}])
    light = lights[0] if lights else {}
    kelvin = light.get("kelvin", 0)
    kelvin_str = f"{kelvin // 1000}K" if kelvin else "N/A"

    draw_gauge(draw, COL1_CX, TOP_GAUGE_Y, light.get("intensity_pct", 0), BLUE, kelvin_str)
    draw_gauge(draw, COL2_CX, TOP_GAUGE_Y, data.get("return_pump", {}).get("intensity", 0), BLUE, "Return")

    wave_l_pct = waves[1].get("forward_intensity", 0) if len(waves) > 1 else 0
    wave_r_pct = waves[0].get("forward_intensity", 0) if waves else 0
    draw_gauge(draw, COL3_CX, TOP_GAUGE_Y, wave_l_pct, BLUE, "Left")

    # ── Gauges — Bottom row ───────────────────────────
    draw_gauge(draw, COL1_CX, BOT_GAUGE_Y, light.get("moon_pct", 0), BLUE, "Moon")

    # Skimmer — red if cup full
    skimmer = data.get("skimmer", {})
    skimmer_full = skimmer.get("state") == "full-cup"
    skimmer_color = RED if skimmer_full else BLUE
    draw_gauge(draw, COL2_CX, BOT_GAUGE_Y, skimmer.get("intensity", 0), skimmer_color, "Skimmer")
    if skimmer_full:
        # Warning triangle + FULL text
        ty = BOT_GAUGE_Y + GAUGE_R + 32
        tcx = COL2_CX - 30
        tri = [(tcx + 6, ty), (tcx, ty + 12), (tcx + 12, ty + 12)]
        draw.polygon(tri, fill=RED)
        draw.text((tcx - 2, ty + 1), "!", fill=WHITE, font=_font(10, bold=True))
        draw.text((tcx + 16, ty), "FULL", fill=RED, font=FONT_LABEL)

    draw_gauge(draw, COL3_CX, BOT_GAUGE_Y, wave_r_pct, BLUE, "Right")

    # ── Button bar at bottom ──────────────────────────
    btn_top = HEIGHT - BTN_H
    draw.line([0, btn_top, WIDTH, btn_top], fill=BLACK, width=1)
    btn_w = WIDTH // 5
    btn_labels = [
        ("ATO\nOff", BLACK),
        ("Waste\nOff", BLACK),
        ("Salt Fill\nOff", BLACK),
        ("Resume\nSkimmer", RED),
        ("Stop\nAll", BLACK),
    ]
    for i, (lbl, color) in enumerate(btn_labels):
        bx = i * btn_w
        if i > 0:
            draw.line([bx, btn_top, bx, HEIGHT], fill=BLACK, width=1)
        cx = bx + btn_w // 2
        lines = lbl.split("\n")
        for j, line in enumerate(lines):
            lw = _tw(draw, line, FONT_LABEL)
            draw.text((cx - lw / 2, btn_top + 6 + j * 16), line, fill=color, font=FONT_LABEL)

    return img


def render_error(title, detail=""):
    img = Image.new("RGB", (WIDTH, HEIGHT), WHITE)
    draw = ImageDraw.Draw(img)

    # Red header
    draw.rectangle([0, 0, WIDTH, HEADER_H], fill=RED)
    draw.text((PAD, 12), "OpenReefBeat \u2014 ERROR", fill=WHITE, font=FONT_HEADER)

    cx = WIDTH // 2

    # Warning icon
    draw.text((cx - 20, 80), "!", fill=RED, font=_font(64, bold=True))

    # Title
    tw = _tw(draw, title, FONT_ERR_TITLE)
    draw.text((cx - tw / 2, 170), title, fill=BLACK, font=FONT_ERR_TITLE)

    # Detail
    if detail:
        dw = _tw(draw, detail, FONT_ERR_DETAIL)
        draw.text((cx - dw / 2, 215), detail, fill=BLACK, font=FONT_ERR_DETAIL)

    # Setup instructions
    y = 270
    draw.line([cx - 200, y, cx + 200, y], fill=LIGHT_GRAY, width=1)
    y += 16
    draw.text((cx - 200, y), "Quick Setup", fill=BLUE, font=FONT_HEADING)
    y += 28
    steps = [
        "1.  Edit config.py with your WiFi credentials",
        "    and ReefBeat login (same as the phone app)",
        "2.  Copy config.py + main.py to the Inky Frame",
        "3.  Power cycle the device to connect",
        "",
        "Devices are auto-discovered from your account.",
    ]
    for line in steps:
        draw.text((cx - 200, y), line, fill=BLACK, font=FONT_LABEL)
        y += 18

    # GitHub link
    y += 8
    url = "github.com/MDamon/OpenReefBeat"
    uw = _tw(draw, url, FONT_LABEL)
    draw.text((cx - uw / 2, y), url, fill=BLUE, font=FONT_LABEL)

    return img


# ── CLI ─────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent / ".env")
    except ImportError:
        pass
    DATA_DIR.mkdir(exist_ok=True)
    out = DATA_DIR / "dashboard.png"

    if "--error" in sys.argv:
        img = render_error("Connection Failed", "Could not reach ReefBeat API")
        img.save(out)
        print(f"Error screen saved to {out}")
    else:
        snap_file = DATA_DIR / "snapshot.json"
        if not snap_file.exists():
            print(f"No snapshot found at {snap_file}. Run refresh.py first.")
            sys.exit(1)
        data = json.loads(snap_file.read_text())
        temp_history = load_temp_history()
        location = os.environ.get("LOCATION", "")
        img = render_dashboard(data, temp_history, location=location)
        img.save(out)
        print(f"Dashboard saved to {out}")
