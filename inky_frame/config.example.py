# ── OpenReefBeat · Inky Frame Configuration ─────────────────
# Copy this file to config.py and fill in your values.
# config.py is gitignored — your credentials stay local.

# WiFi — tries each network in order until one connects
WIFI_NETWORKS = [
    ("YourWiFiNetwork", "YourWiFiPassword"),
]

# ReefBeat account (same login as your phone app)
USERNAME = "your_email@example.com"
REEFBEAT_PASSWORD = "your_password"

# App credentials (see docs/REVERSE_ENGINEERING.md to capture this)
CLIENT_CREDENTIALS = "see-docs/REVERSE_ENGINEERING.md-to-capture-this"

# Kasa cloud (TP-Link HS300 power strip)
KASA_TOKEN = "your-kasa-cloud-token"
KASA_CLOUD_URL = "https://use1-wap.tplinkcloud.com"
KASA_WASTE_DEVICE = "your-device-id"
KASA_WASTE_CHILD = "your-waste-child-id"
KASA_SALT_DEVICE = "your-device-id"
KASA_SALT_CHILD = "your-salt-child-id"

# Display settings
REFRESH_MINUTES = 5
