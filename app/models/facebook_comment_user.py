from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class FacebookCommentUserState:
    user_key: str
    display_name: str = ""
    status: str = "normal"  # normal | watchlist | blocked
    note: str = ""
    last_action: str = ""
    last_action_at: str = ""
    page_block_status: dict[str, str] = field(default_factory=dict)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "FacebookCommentUserState":
        raw_page_status = data.get("page_block_status", {})
        return cls(
            user_key=str(data.get("user_key", "") or ""),
            display_name=str(data.get("display_name", "") or ""),
            status=str(data.get("status", "normal") or "normal"),
            note=str(data.get("note", "") or ""),
            last_action=str(data.get("last_action", "") or ""),
            last_action_at=str(data.get("last_action_at", "") or ""),
            page_block_status={str(k): str(v) for k, v in raw_page_status.items()} if isinstance(raw_page_status, dict) else {},
            updated_at=str(data.get("updated_at", utc_now_iso()) or utc_now_iso()),
        )
