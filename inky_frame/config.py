# ── OpenReefBeat · Inky Frame Configuration ─────────────────
# Edit these 4 values, then copy this file + main.py to your Inky Frame.

# WiFi — tries each network in order until one connects
WIFI_NETWORKS = [
    ("YourWiFiNetwork", "YourWiFiPassword"),
    ("BackupNetwork", "YourWiFiPassword"),
]

# ReefBeat account (same login as your phone app)
USERNAME = "your_email@example.com"
REEFBEAT_PASSWORD = "your_password"

# App credentials (shared across all ReefBeat users — do not change)
CLIENT_CREDENTIALS = "see-docs/REVERSE_ENGINEERING.md-to-capture-this"

# Display settings
REFRESH_MINUTES = 5
