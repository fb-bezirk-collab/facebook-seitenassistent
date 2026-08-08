"""Quellenmodule des KI-Medienmonitors."""

from app.media_monitor.fetchers.heute import fetch_heute
from app.media_monitor.fetchers.krone import fetch_krone
from app.media_monitor.fetchers.kurier import fetch_kurier
from app.media_monitor.fetchers.oe24 import fetch_oe24

__all__ = ["fetch_krone", "fetch_kurier", "fetch_heute", "fetch_oe24"]
