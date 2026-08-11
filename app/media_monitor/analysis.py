from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any

import requests

from app.media_monitor.storage import load_items, save_items

API_URL = "https://api.openai.com/v1/responses"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
)


class MediaAnalysisError(RuntimeError):
    pass


from app.media_monitor.prompt_loader import build_analysis_system_prompt, load_analysis_schema

ANALYSIS_SCHEMA = load_analysis_schema()
SYSTEM_PROMPT = build_analysis_system_prompt()


class _ArticleTextParser(HTMLParser):
    SKIP_TAGS = {"script", "style", "nav", "header", "footer", "aside", "form", "button", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.article_depth = 0
        self.capture_p = False
        self.current: list[str] = []
        self.article_paragraphs: list[str] = []
        self.all_paragraphs: list[str] = []
        self.json_ld: list[str] = []
        self.in_json_ld = False
        self.json_buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {k.lower(): (v or "") for k, v in attrs}
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
        if tag == "article":
            self.article_depth += 1
        if tag == "script" and attrs_dict.get("type", "").lower() == "application/ld+json":
            self.in_json_ld = True
            self.json_buffer = []
        if tag == "p" and self.skip_depth == 0:
            self.capture_p = True
            self.current = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "p" and self.capture_p:
            text = _clean_text(" ".join(self.current))
            if len(text) >= 35:
                self.all_paragraphs.append(text)
                if self.article_depth > 0:
                    self.article_paragraphs.append(text)
            self.capture_p = False
            self.current = []
        if tag == "article" and self.article_depth > 0:
            self.article_depth -= 1
        if tag == "script" and self.in_json_ld:
            self.json_ld.append("".join(self.json_buffer))
            self.in_json_ld = False
            self.json_buffer = []
        if tag in self.SKIP_TAGS and self.skip_depth > 0:
            self.skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.in_json_ld:
            self.json_buffer.append(data)
        if self.capture_p and self.skip_depth == 0:
            self.current.append(data)


def _clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _json_article_bodies(raw_blocks: list[str]) -> list[str]:
    bodies: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            body = value.get("articleBody")
            if isinstance(body, str) and len(_clean_text(body)) >= 100:
                bodies.append(_clean_text(body))
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    for raw in raw_blocks:
        try:
            walk(json.loads(raw))
        except (json.JSONDecodeError, TypeError):
            continue
    return bodies


def _meta_description(page: str) -> str:
    patterns = [
        r'<meta[^>]+(?:name|property)=["\'](?:description|og:description)["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\'](?:description|og:description)["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, page, flags=re.I | re.S)
        if match:
            return _clean_text(match.group(1))
    return ""


def fetch_article_text(url: str, teaser: str = "") -> tuple[str, str]:
    """Liest öffentlich zugänglichen Artikeltext. Rückgabe: (Text, Modus)."""
    if not url:
        fallback = _clean_text(teaser)
        return fallback, "teaser"

    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "de-AT,de;q=0.9,en;q=0.5"},
            timeout=30,
            allow_redirects=True,
        )
        response.raise_for_status()
    except requests.RequestException:
        fallback = _clean_text(teaser)
        return fallback, "teaser"

    page = response.text or ""
    parser = _ArticleTextParser()
    try:
        parser.feed(page)
    except Exception:
        pass

    json_bodies = _json_article_bodies(parser.json_ld)
    candidates: list[tuple[str, str]] = []
    if json_bodies:
        candidates.append((max(json_bodies, key=len), "article"))
    if parser.article_paragraphs:
        candidates.append(("\n\n".join(parser.article_paragraphs), "article"))
    if parser.all_paragraphs:
        candidates.append(("\n\n".join(parser.all_paragraphs), "page"))

    if candidates:
        text, mode = max(candidates, key=lambda pair: len(pair[0]))
        # Navigation/Boilerplate kann bei generischen Seiten sehr lang sein. Für die KI reicht ein sauber begrenzter Ausschnitt.
        text = _clean_text(text.replace("\n\n", "\n"))[:18000]
        if len(text) >= 300:
            return text, mode

    fallback_parts = [_clean_text(teaser), _meta_description(page)]
    fallback = "\n".join(part for part in fallback_parts if part)
    return fallback[:4000], "teaser"


def _extract_output_text(data: dict[str, Any]) -> str:
    direct = data.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    parts: list[str] = []
    for output in data.get("output", []):
        if not isinstance(output, dict):
            continue
        for content in output.get("content", []):
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
            elif isinstance(text, dict):
                value = text.get("value")
                if isinstance(value, str) and value.strip():
                    parts.append(value.strip())
    return "\n".join(parts).strip()


def _call_analysis_model(item: dict[str, Any], article_text: str, content_mode: str, related: list[dict[str, Any]]) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MEDIA_ANALYSIS_MODEL", os.getenv("OPENAI_MEDIA_MONITOR_MODEL", os.getenv("OPENAI_MODEL", "gpt-5-mini"))).strip()
    if not api_key:
        raise MediaAnalysisError("OPENAI_API_KEY ist nicht konfiguriert.")

    compact_related = [
        {
            "source": str(other.get("source", "")),
            "title": str(other.get("title", ""))[:500],
            "summary": str(other.get("ai_summary") or other.get("teaser") or "")[:1200],
            "published_at": str(other.get("published_at") or ""),
            "url": str(other.get("url") or ""),
        }
        for other in related[:10]
    ]

    user_payload = {
        "article": {
            "source": str(item.get("source", "")),
            "title": str(item.get("title", "")),
            "published_at": str(item.get("published_at") or ""),
            "url": str(item.get("url") or ""),
            "existing_summary": str(item.get("ai_summary") or item.get("teaser") or ""),
            "content_mode": content_mode,
            "article_text": article_text,
        },
        "same_event_other_sources": compact_related,
    }

    payload = {
        "model": model,
        "input": [
            {"role": "developer", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
        "reasoning": {"effort": "minimal"},
        "text": {
            "verbosity": "medium",
            "format": {
                "type": "json_schema",
                "name": "media_article_analysis",
                "strict": True,
                "schema": ANALYSIS_SCHEMA,
            },
        },
        "max_output_tokens": 7000,
    }

    try:
        response = requests.post(
            API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=150,
        )
    except requests.RequestException as exc:
        raise MediaAnalysisError(f"OpenAI ist nicht erreichbar: {exc}") from exc

    if response.status_code >= 400:
        try:
            message = response.json().get("error", {}).get("message")
        except ValueError:
            message = None
        raise MediaAnalysisError(f"OpenAI-Fehler: {message or response.status_code}")

    try:
        data = response.json()
        raw = _extract_output_text(data)
        parsed = json.loads(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        raise MediaAnalysisError(f"Die KI-Analyse konnte nicht gelesen werden: {exc}") from exc
    if not isinstance(parsed, dict):
        raise MediaAnalysisError("Die KI-Analyse hatte ein unerwartetes Format.")
    return parsed


def run_item_analysis(item_id: str) -> None:
    """Hintergrundjob für eine einzelne Meldung."""
    items = load_items()
    item = next((entry for entry in items if str(entry.get("id")) == str(item_id)), None)
    if not item:
        return

    item["analysis_status"] = "running"
    item["analysis_error"] = ""
    save_items(items)

    try:
        article_text, content_mode = fetch_article_text(str(item.get("url") or ""), str(item.get("teaser") or ""))
        if not article_text.strip():
            raise MediaAnalysisError("Auf der Artikelseite konnte kein auswertbarer Text gelesen werden.")

        cluster_id = str(item.get("trend_cluster_id") or "")
        related = [
            other for other in items
            if cluster_id and str(other.get("trend_cluster_id") or "") == cluster_id and str(other.get("id")) != str(item_id)
        ]
        result = _call_analysis_model(item, article_text, content_mode, related)

        # Noch einmal frisch laden, damit ein zwischenzeitlicher Medienabruf nicht überschrieben wird.
        fresh_items = load_items()
        fresh_item = next((entry for entry in fresh_items if str(entry.get("id")) == str(item_id)), None)
        if not fresh_item:
            return
        fresh_item["analysis_status"] = "done"
        fresh_item["analysis_error"] = ""
        fresh_item["analysis_updated_at"] = datetime.now(timezone.utc).isoformat()
        fresh_item["analysis_content_mode"] = content_mode
        fresh_item["analysis_article_chars"] = len(article_text)
        fresh_item["analysis"] = result
        save_items(fresh_items)
    except Exception as exc:
        fresh_items = load_items()
        fresh_item = next((entry for entry in fresh_items if str(entry.get("id")) == str(item_id)), None)
        if fresh_item:
            fresh_item["analysis_status"] = "error"
            fresh_item["analysis_error"] = str(exc).strip() or "Unbekannter Fehler bei der KI-Analyse."
            fresh_item["analysis_updated_at"] = datetime.now(timezone.utc).isoformat()
            save_items(fresh_items)
