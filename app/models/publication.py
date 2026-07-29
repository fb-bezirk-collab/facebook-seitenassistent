from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional


VALID_PLATFORMS = {"facebook", "instagram", "x", "tiktok"}
VALID_PUBLICATION_STATUSES = {"planned", "ready", "published", "failed", "cancelled"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Publication:
    id: str
    post_id: str
    platform: str
    account_id: str
    account_name: str
    publish_at: str
    status: str = "planned"
    external_post_id: str = ""
    error_message: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    published_at: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Publication":
        platform = str(data.get("platform", "facebook")).lower().strip()
        if platform not in VALID_PLATFORMS:
            platform = "facebook"
        status = str(data.get("status", "planned")).lower().strip()
        if status not in VALID_PUBLICATION_STATUSES:
            status = "planned"
        return cls(
            id=str(data.get("id", "")),
            post_id=str(data.get("post_id", "")),
            platform=platform,
            account_id=str(data.get("account_id", "")),
            account_name=str(data.get("account_name", "")),
            publish_at=str(data.get("publish_at", "")),
            status=status,
            external_post_id=str(data.get("external_post_id", "")),
            error_message=str(data.get("error_message", "")),
            created_at=str(data.get("created_at", utc_now_iso())),
            updated_at=str(data.get("updated_at", utc_now_iso())),
            published_at=data.get("published_at"),
        )
