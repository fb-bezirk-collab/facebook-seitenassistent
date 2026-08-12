from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class FacebookComment:
    comment_id: str
    page_id: str
    page_name: str
    post_id: str
    post_message: str = ""
    post_permalink: str = ""
    author_id: str = ""
    author_name: str = ""
    message: str = ""
    created_time: str = ""
    permalink_url: str = ""
    parent_id: str = ""
    is_hidden: bool = False
    can_hide: bool = False
    can_remove: bool = False
    status: str = "new"
    fetched_at: str = field(default_factory=utc_now_iso)
    last_seen_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "FacebookComment":
        return cls(
            comment_id=str(data.get("comment_id", "")).strip(),
            page_id=str(data.get("page_id", "")).strip(),
            page_name=str(data.get("page_name", "")).strip(),
            post_id=str(data.get("post_id", "")).strip(),
            post_message=str(data.get("post_message", "") or ""),
            post_permalink=str(data.get("post_permalink", "") or ""),
            author_id=str(data.get("author_id", "") or ""),
            author_name=str(data.get("author_name", "") or ""),
            message=str(data.get("message", "") or ""),
            created_time=str(data.get("created_time", "") or ""),
            permalink_url=str(data.get("permalink_url", "") or ""),
            parent_id=str(data.get("parent_id", "") or ""),
            is_hidden=bool(data.get("is_hidden", False)),
            can_hide=bool(data.get("can_hide", False)),
            can_remove=bool(data.get("can_remove", False)),
            status=str(data.get("status", "new") or "new"),
            fetched_at=str(data.get("fetched_at", utc_now_iso()) or utc_now_iso()),
            last_seen_at=str(data.get("last_seen_at", utc_now_iso()) or utc_now_iso()),
        )
