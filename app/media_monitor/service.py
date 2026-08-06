from __future__ import annotations

from app.media_monitor.fetchers.krone import fetch_krone
from app.media_monitor.storage import merge_fetched_items


def fetch_current_media() -> tuple[list[dict], int]:
    fetched = fetch_krone()
    return merge_fetched_items(fetched)
