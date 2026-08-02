from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class InstagramConnection:
    instagram_id: str
    username: str
    name: str
    access_token: str
    token_expires_at: str = ""
    profile_picture_url: str = ""
    active: bool = True
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "InstagramConnection":
        return cls(
            instagram_id=str(data.get("instagram_id", "")).strip(),
            username=str(data.get("username", "")).strip().lstrip("@"),
            name=str(data.get("name", "")).strip(),
            access_token=str(data.get("access_token", "")).strip(),
            token_expires_at=str(data.get("token_expires_at", "")).strip(),
            profile_picture_url=str(data.get("profile_picture_url", "")).strip(),
            active=bool(data.get("active", True)),
            created_at=str(data.get("created_at", utc_now_iso())),
        )
