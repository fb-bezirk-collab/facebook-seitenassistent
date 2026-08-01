from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional


VALID_POST_STATUSES = {
    "draft",
    "scheduled",
    "published",
    "failed",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_text_variants(value) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    variants: list[dict[str, str]] = []

    for index, item in enumerate(value[:6], start=1):
        if not isinstance(item, dict):
            continue

        text = str(item.get("text", "")).strip()
        if not text:
            continue

        title = str(item.get("title", "")).strip() or f"Variante {index}"
        variants.append({
            "title": title[:100],
            "text": text,
        })

    return variants


@dataclass
class ManagedPost:
    id: str
    title: str = ""
    text: str = ""
    text_variants: list[dict[str, str]] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    videos: list[str] = field(default_factory=list)
    video_url: str = ""
    page_id: str = ""
    source_url: str = ""
    status: str = "draft"
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    publish_at: Optional[str] = None
    published_at: Optional[str] = None
    error_message: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ManagedPost":
        status = str(data.get("status", "draft"))
        if status not in VALID_POST_STATUSES:
            status = "draft"

        images = data.get("images", [])
        if not isinstance(images, list):
            images = []

        videos = data.get("videos", [])
        if not isinstance(videos, list):
            videos = []

        video_url = str(data.get("video_url", "")).strip()
        if (
            not video_url
            and videos
            and str(videos[0]).startswith(("http://", "https://"))
        ):
            video_url = str(videos[0])
            videos = videos[1:]

        return cls(
            id=str(data.get("id", "")),
            title=str(data.get("title", "")),
            text=str(data.get("text", "")),
            text_variants=_load_text_variants(data.get("text_variants", [])),
            images=[str(item) for item in images if item],
            videos=[str(item) for item in videos if item],
            video_url=video_url,
            page_id=str(data.get("page_id", "")),
            source_url=str(data.get("source_url", "")),
            status=status,
            created_at=str(data.get("created_at", utc_now_iso())),
            updated_at=str(data.get("updated_at", utc_now_iso())),
            publish_at=data.get("publish_at"),
            published_at=data.get("published_at"),
            error_message=str(data.get("error_message", "")),
        )
