from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone

from app.config import COMMENT_USERS_FILE
from app.models.facebook_comment import FacebookComment
from app.models.facebook_comment_user import FacebookCommentUserState


def _normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().casefold())


def _normalize_message(value: str) -> str:
    text = (value or "").casefold()
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[^\wäöüß]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def user_key_for_name(name: str) -> str:
    normalized = _normalize_name(name)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20] if normalized else ""


class CommentUserStateStorage:
    def __init__(self, path=COMMENT_USERS_FILE):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.save({})

    def load(self) -> dict[str, FacebookCommentUserState]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8") or "{}")
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(raw, dict):
            return {}
        result: dict[str, FacebookCommentUserState] = {}
        for key, value in raw.items():
            if not isinstance(value, dict):
                continue
            state = FacebookCommentUserState.from_dict({**value, "user_key": value.get("user_key") or key})
            if state.user_key:
                result[state.user_key] = state
        return result

    def save(self, states: dict[str, FacebookCommentUserState]) -> None:
        self.path.write_text(
            json.dumps({key: state.to_dict() for key, state in states.items()}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get(self, user_key: str) -> FacebookCommentUserState | None:
        return self.load().get(user_key)

    def update(self, state: FacebookCommentUserState) -> None:
        states = self.load()
        state.updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        states[state.user_key] = state
        self.save(states)


def build_user_profiles(comments: list[FacebookComment]) -> list[dict]:
    """Bündelt Kommentare nach Anzeigename.

    Meta verwendet pro User-Seiten-Paar eine eigene PSID. Ein gleicher Anzeigename auf
    mehreren Seiten ist daher nur ein möglicher Identitätstreffer und wird entsprechend
    gekennzeichnet. Für Sperraktionen werden ausschließlich konkret beobachtete PSIDs
    je Seite verwendet.
    """
    states = CommentUserStateStorage().load()
    groups: dict[str, list[FacebookComment]] = defaultdict(list)
    display_names: dict[str, str] = {}

    for comment in comments:
        name = (comment.author_name or "").strip()
        key = user_key_for_name(name)
        if not key:
            continue
        groups[key].append(comment)
        display_names.setdefault(key, name)

    profiles: list[dict] = []
    for key, items in groups.items():
        items.sort(key=lambda c: c.created_time or c.fetched_at, reverse=True)
        page_ids: dict[str, set[str]] = defaultdict(set)
        page_names: dict[str, str] = {}
        for c in items:
            if c.page_id:
                page_names[c.page_id] = c.page_name
                if c.author_id:
                    page_ids[c.page_id].add(c.author_id)

        exact_page_ids = {
            page_id: next(iter(ids))
            for page_id, ids in page_ids.items()
            if len(ids) == 1
        }
        ambiguous_pages = [page_id for page_id, ids in page_ids.items() if len(ids) > 1]

        categories = Counter(c.ai_category for c in items if c.ai_category)
        attachment_types = Counter((c.attachment_type or "").casefold() for c in items if c.attachment_type or c.attachment_url or c.attachment_image_url)
        image_count = sum(1 for c in items if c.attachment_image_url and "gif" not in (c.attachment_type or "").casefold() and "sticker" not in (c.attachment_type or "").casefold())
        gif_count = sum(1 for c in items if "gif" in (c.attachment_type or "").casefold())
        sticker_count = sum(1 for c in items if "sticker" in (c.attachment_type or "").casefold())
        media_count = sum(1 for c in items if c.attachment_type or c.attachment_url or c.attachment_image_url)
        moderation_count = sum(1 for c in items if c.ai_recommendation in {"Ausblenden prüfen", "Löschen prüfen"})
        high_count = sum(1 for c in items if c.ai_priority == "hoch")

        normalized_messages = [_normalize_message(c.message) for c in items]
        normalized_messages = [m for m in normalized_messages if len(m) >= 8]
        message_counts = Counter(normalized_messages)
        repeated_messages = {msg: count for msg, count in message_counts.items() if count >= 2}
        repeated_comment_count = sum(count for count in repeated_messages.values())
        max_repeat = max(repeated_messages.values(), default=0)

        # Der Score ist eine Arbeitshilfe, keine automatische Sperrentscheidung.
        score = 0
        score += min(45, categories.get("Beleidigung", 0) * 15)
        score += min(50, categories.get("Drohung/Gewalt", 0) * 25)
        score += min(30, categories.get("Spam", 0) * 10)
        score += min(20, categories.get("Off-Topic", 0) * 5)
        score += min(25, max(0, repeated_comment_count - len(repeated_messages)) * 5)
        score += min(15, moderation_count * 3)
        score = min(100, score)

        if score >= 70:
            risk_label = "häufig störend"
        elif score >= 40:
            risk_label = "auffällig"
        elif score >= 20:
            risk_label = "beobachten"
        else:
            risk_label = "unauffällig"

        state = states.get(key) or FacebookCommentUserState(user_key=key, display_name=display_names[key])
        profiles.append({
            "user_key": key,
            "display_name": display_names[key],
            "comments": items,
            "comment_count": len(items),
            "page_count": len({c.page_id for c in items if c.page_id}),
            "page_names": sorted({c.page_name for c in items if c.page_name}, key=str.lower),
            "page_ids": exact_page_ids,
            "page_id_details": [
                {
                    "page_id": page_id,
                    "page_name": page_names.get(page_id, page_id),
                    "psid": exact_page_ids.get(page_id, ""),
                    "ambiguous": page_id in ambiguous_pages,
                }
                for page_id in sorted(page_names, key=lambda pid: page_names.get(pid, "").lower())
            ],
            "known_blockable_pages": len(exact_page_ids),
            "ambiguous_page_count": len(ambiguous_pages),
            "identity_notice": len({c.page_id for c in items if c.page_id}) > 1,
            "category_counts": dict(categories),
            "media_count": media_count,
            "image_count": image_count,
            "gif_count": gif_count,
            "sticker_count": sticker_count,
            "moderation_count": moderation_count,
            "high_count": high_count,
            "repeated_comment_count": repeated_comment_count,
            "max_repeat": max_repeat,
            "risk_score": score,
            "risk_label": risk_label,
            "state": state,
        })

    profiles.sort(key=lambda p: (p["risk_score"], p["comment_count"]), reverse=True)
    return profiles


def get_user_profile(comments: list[FacebookComment], user_key: str) -> dict | None:
    return next((profile for profile in build_user_profiles(comments) if profile["user_key"] == user_key), None)
