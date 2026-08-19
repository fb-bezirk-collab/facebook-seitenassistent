from __future__ import annotations
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse
from app.media_monitor.fetchers.generic import fetch_homepage_source

SOURCE_NAME="Die Presse"
DEFAULT_URL="https://www.diepresse.com/"
DEFAULT_INTERIOR_URL="https://www.diepresse.com/innenpolitik"
DEFAULT_FOREIGN_URL="https://www.diepresse.com/ausland"
DEFAULT_EU_URL="https://www.diepresse.com/ausland/eu"
DEFAULT_ECONOMY_URL="https://www.diepresse.com/wirtschaft"

def _is_article_url(url:str)->bool:
    parsed=urlparse(url); host=parsed.netloc.lower().removeprefix("www.")
    parts=[part for part in parsed.path.split("/") if part]
    return host=="diepresse.com" and bool(parts and parts[0].isdigit() and len(parts[0])>=5)

def _sort_value(item:dict[str,Any])->datetime:
    raw=str(item.get("published_at") or "").strip()
    if not raw: return datetime.min.replace(tzinfo=timezone.utc)
    try:
        value=datetime.fromisoformat(raw.replace("Z","+00:00"))
        if value.tzinfo is None: value=value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    except ValueError: return datetime.min.replace(tzinfo=timezone.utc)

def fetch_presse(limit:int=40)->list[dict[str,Any]]:
    wanted=max(1,min(limit,100)); per_channel=max(40,wanted)
    specs=[
      ("Innenpolitik",os.getenv("PRESSE_INTERIOR_URL",DEFAULT_INTERIOR_URL).strip() or DEFAULT_INTERIOR_URL),
      ("EU",os.getenv("PRESSE_EU_URL",DEFAULT_EU_URL).strip() or DEFAULT_EU_URL),
      ("Ausland",os.getenv("PRESSE_FOREIGN_URL",DEFAULT_FOREIGN_URL).strip() or DEFAULT_FOREIGN_URL),
      ("Wirtschaft",os.getenv("PRESSE_ECONOMY_URL",DEFAULT_ECONOMY_URL).strip() or DEFAULT_ECONOMY_URL),
      ("Startseite",os.getenv("PRESSE_MONITOR_URL",DEFAULT_URL).strip() or DEFAULT_URL),
    ]
    by_url={}; errors=[]
    for label,source_url in specs:
        try:
            items=fetch_homepage_source(source_name=SOURCE_NAME,source_url=source_url,base_url="https://www.diepresse.com/",article_url_predicate=_is_article_url,limit=per_channel,enrich_dates=True)
        except Exception as exc:
            errors.append(f"{label}: {exc}"); print(f"Die Presse – {label} fehlgeschlagen: {exc}",flush=True); continue
        for item in items:
            url=str(item.get("url") or "").split("#",1)[0].rstrip("/").strip()
            if not url: continue
            if url not in by_url:
                copy=dict(item); copy["url"]=url; by_url[url]=copy
            else:
                for key in ("title","teaser","image_url","published_at","source_category"):
                    if not by_url[url].get(key) and item.get(key): by_url[url][key]=item[key]
    if not by_url: raise RuntimeError("Die Presse konnte nicht gelesen werden: "+("; ".join(errors) or "keine Artikel gefunden"))
    merged=list(by_url.values()); merged.sort(key=_sort_value,reverse=True); return merged[:wanted]
