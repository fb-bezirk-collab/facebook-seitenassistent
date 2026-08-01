from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from app.models.platform import get_platform


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class SocialAccount:
    id: str
    platform: str
    name: str
    external_id: str = ""
    username: str = ""
    active: bool = True
    connection_status: str = "manual"
    source: str = "manual"
    can_publish: bool = False
    created_at: str = field(default_factory=utc_now_iso)

    @property
    def platform_name(self) -> str:
        definition = get_platform(self.platform)
        return definition.name if definition else self.platform.capitalize()

    @property
    def display_name(self) -> str:
        if self.username:
            return f"{self.name} (@{self.username.lstrip('@')})"
        return self.name

    @property
    def is_connected(self) -> bool:
        return self.connection_status == "connected"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SocialAccount":
        platform = str(
            data.get("platform", "facebook")
        ).lower().strip()

        definition = get_platform(platform)
        default_publish = bool(
            definition and definition.can_publish
        )

        return cls(
            id=str(data.get("id", "")),
            platform=platform,
            name=str(data.get("name", "")).strip(),
            external_id=str(
                data.get("external_id", "")
            ).strip(),
            username=str(
                data.get("username", "")
            ).strip().lstrip("@"),
            active=bool(data.get("active", True)),
            connection_status=str(
                data.get("connection_status", "manual")
            ).strip() or "manual",
            source=str(
                data.get("source", "manual")
            ).strip() or "manual",
            can_publish=bool(
                data.get("can_publish", default_publish)
            ),
            created_at=str(
                data.get("created_at", utc_now_iso())
            ),
        )
