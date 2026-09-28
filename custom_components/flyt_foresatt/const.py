"""Constants for the Flyt Foresatt integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "flyt_foresatt"

API_URL: Final = "https://api.foresatt.visma.no/"
FRONTEND_URL: Final = "https://foresatt.visma.no"

CONF_MUNICIPALITY: Final = "municipality"
CONF_COOKIES: Final = "cookies"

DEFAULT_SCAN_INTERVAL: Final = timedelta(minutes=15)

# How many weeks of timetable to fetch (current week + following weeks).
TIMETABLE_WEEKS: Final = 2
