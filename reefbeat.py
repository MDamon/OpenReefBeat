"""ReefBeat Cloud API client."""

import json
import time
from pathlib import Path

import requests

BASE_URL = "https://cloud.thereefbeat.com"
DATA_DIR = Path(__file__).parent / "data"
TOKEN_FILE = DATA_DIR / "token.json"


class ReefBeatClient:
    def __init__(self, username: str, password: str, client_credentials: str):
        self.username = username
        self.password = password
        self.client_credentials = client_credentials
        self.access_token = None
        self.refresh_token = None
        self.token_expiry = 0
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})
        DATA_DIR.mkdir(exist_ok=True)
        self._load_token()

    def _load_token(self):
        if TOKEN_FILE.exists():
            data = json.loads(TOKEN_FILE.read_text())
            self.access_token = data.get("access_token")
            self.refresh_token = data.get("refresh_token")
            self.token_expiry = data.get("token_expiry", 0)

    def _save_token(self):
        TOKEN_FILE.write_text(json.dumps({
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "token_expiry": self.token_expiry,
        }, indent=2))

    def _authenticate(self, grant_type="password", **kwargs):
        data = {"grant_type": grant_type, **kwargs}
        if grant_type == "password":
            data["username"] = self.username
            data["password"] = self.password
        resp = self._session.post(
            f"{BASE_URL}/oauth/token",
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {self.client_credentials}",
            },
        )
        resp.raise_for_status()
        token = resp.json()
        self.access_token = token["access_token"]
        self.refresh_token = token["refresh_token"]
        self.token_expiry = time.time() + token["expires_in"] - 60  # 1 min buffer
        self._save_token()

    def _ensure_token(self):
        if self.access_token and time.time() < self.token_expiry:
            return
        if self.refresh_token:
            try:
                self._authenticate(
                    grant_type="refresh_token",
                    refresh_token=self.refresh_token,
                )
                return
            except requests.HTTPError:
                pass  # refresh token expired, fall through to password login
        self._authenticate(grant_type="password")

    def _get(self, path: str) -> dict:
        self._ensure_token()
        resp = self._session.get(
            f"{BASE_URL}{path}",
            headers={"Authorization": f"Bearer {self.access_token}"},
        )
        resp.raise_for_status()
        return resp.json()

    # ── High-level API ──────────────────────────────────────

    def get_aquariums(self) -> list:
        return self._get("/aquarium")

    def get_dashboard(self, aquarium_uid: str) -> dict:
        return self._get(f"/aquarium/{aquarium_uid}/dashboard")

    def get_devices(self) -> list:
        return self._get("/device")

    def get_ato_dashboard(self, hwid: str) -> dict:
        return self._get(f"/reef-ato/{hwid}/dashboard")

    def get_ato_temperature_log(self, hwid: str, duration: str = "P30D") -> dict:
        return self._get(f"/reef-ato/{hwid}/temperature-log?duration={duration}")

    def get_pump_dashboard(self, hwid: str) -> dict:
        return self._get(f"/reef-run/{hwid}/dashboard")

    def get_light_dashboard(self, hwid: str) -> dict:
        return self._get(f"/device/{hwid}/command/dashboard")

    def get_reefmat_rolling_log(self, hwid: str) -> dict:
        return self._get(f"/reef-mat/{hwid}/rolling-log")

    def get_wave_schedule(self, hwid: str) -> dict:
        return self._get(f"/reef-wave/schedule/{hwid}")

    def get_notifications(self, days: int = 90, size: int = 100) -> list:
        data = self._get(
            f"/notification/inapp?expirationDays={days}&page=0"
            f"&size={size}&sortDirection=DESC"
        )
        return data.get("content", [])

    def get_unread_notification_count(self, days: int = 60) -> int:
        return self._get(f"/notification/inapp/count-unread?days={days}")

    # ── Snapshot: all KPIs in one call ──────────────────────

    def snapshot(
        self,
        aquarium_uid: str,
        ato_hwid: str,
        pump_hwid: str,
        light_hwids=None,
    ) -> dict:
        """Fetch key tank KPIs for e-ink display."""
        ato = self.get_ato_dashboard(ato_hwid)
        pumps = self.get_pump_dashboard(pump_hwid)
        dashboard = self.get_dashboard(aquarium_uid)

        # Water temp from ATO sensor
        temp_c = ato.get("ato_sensor", {}).get("current_read")
        temp_f = round(temp_c * 9 / 5 + 32, 1) if temp_c else None

        # ATO water level (numeric sensor reading in addition to status)
        ato_sensor = ato.get("ato_sensor", {})

        # Lights from dashboard + detailed light endpoint
        lights = []
        for light in dashboard.get("reef_lights", []):
            common = light.get("common", {})
            specific = light.get("specific", {})
            manual = specific.get("manual", {})
            moon = specific.get("moon_phase", {})
            entry = {
                "name": common.get("name"),
                "connected": common.get("connected"),
                "mode": specific.get("mode"),
                "white_pct": manual.get("white"),
                "blue_pct": manual.get("blue"),
                "moon_pct": manual.get("moon"),
                "intensity_pct": manual.get("intensity"),
                "kelvin": manual.get("kelvin"),
                "led_temp_f": round(manual.get("temperature", 0), 1) or None,
                "fan_pct": manual.get("fan"),
                "program": specific.get("current_program", {}).get("name"),
                "moon_phase": moon.get("name"),
                "moon_intensity": moon.get("intensity"),
            }
            lights.append(entry)

        # Detailed light data if hwids provided (has fan, pwm, frequency)
        if light_hwids:
            for i, hwid in enumerate(light_hwids):
                try:
                    detail = self.get_light_dashboard(hwid)
                    manual_d = detail.get("manual", {})
                    if i < len(lights):
                        lights[i]["fan_pct"] = manual_d.get("fan")
                        lights[i]["led_temp_f"] = round(manual_d.get("temperature", 0), 1) or None
                except Exception:
                    pass

        # Wave pumps from dashboard
        waves = []
        for wp in dashboard.get("reef_wave", []):
            common = wp.get("common", {})
            specific = wp.get("specific", {})
            active = specific.get("active_wave", {})
            waves.append({
                "name": common.get("name"),
                "connected": common.get("connected"),
                "mode": specific.get("mode"),
                "program": active.get("name"),
                "type": active.get("type"),
                "forward_intensity": active.get("fti"),
                "reverse_intensity": active.get("rti"),
            })

        # Unread alerts
        try:
            unread = self.get_unread_notification_count()
        except Exception:
            unread = None

        return {
            "timestamp": time.time(),
            "temperature_c": round(temp_c, 1) if temp_c else None,
            "temperature_f": temp_f,
            "water_level": ato_sensor.get("current_level"),
            "water_level_reading": ato_sensor.get("current_read"),
            "ato_pump_on": ato.get("is_pump_on"),
            "ato_fills_today": ato.get("today_fills"),
            "ato_volume_today_ml": ato.get("today_volume_usage"),
            "ato_daily_avg_ml": ato.get("daily_volume_average"),
            "leak_status": ato.get("leak_sensor", {}).get("status"),
            "return_pump": {
                "state": pumps.get("pump_1", {}).get("state"),
                "intensity": pumps.get("pump_1", {}).get("intensity"),
            },
            "skimmer": {
                "state": pumps.get("pump_2", {}).get("state"),
                "intensity": pumps.get("pump_2", {}).get("intensity"),
            },
            "waves": waves,
            "lights": lights,
            "unread_alerts": unread,
            "online": True,
        }
