from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class SocialAccount:
    id: str
    platform: str
    name: str
    external_id: str = ""
    active: bool = True
    connection_status: str = "manual"
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SocialAccount":
        return cls(
            id=str(data.get("id", "")),
            platform=str(data.get("platform", "facebook")).lower().strip(),
            name=str(data.get("name", "")).strip(),
            external_id=str(data.get("external_id", "")).strip(),
            active=bool(data.get("active", True)),
            connection_status=str(data.get("connection_status", "manual")),
            created_at=str(data.get("created_at", utc_now_iso())),
        )
