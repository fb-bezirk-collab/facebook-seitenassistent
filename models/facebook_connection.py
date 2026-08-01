from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class FacebookConnection:
    user_id: str = ""
    user_name: str = ""
    token_type: str = ""
    token_expires_at: str = ""
    connected_at: str = ""
    refreshed_at: str = ""

    @property
    def is_connected(self) -> bool:
        return bool(self.user_id or self.user_name)

    @property
    def is_expired(self) -> bool:
        if not self.token_expires_at:
            return False
        try:
            expires_at = datetime.fromisoformat(self.token_expires_at)
        except ValueError:
            return False
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at <= datetime.now(timezone.utc)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "FacebookConnection":
        return cls(
            user_id=str(data.get("user_id", "")).strip(),
            user_name=str(data.get("user_name", "")).strip(),
            token_type=str(data.get("token_type", "")).strip(),
            token_expires_at=str(data.get("token_expires_at", "")).strip(),
            connected_at=str(data.get("connected_at", "")).strip(),
            refreshed_at=str(data.get("refreshed_at", "")).strip(),
        )

    @classmethod
    def create(
        cls,
        *,
        user_id: str,
        user_name: str,
        token_type: str = "",
        expires_in: int | None = None,
        previous_connected_at: str = "",
    ) -> "FacebookConnection":
        now = datetime.now(timezone.utc)
        expires_at = ""
        if expires_in and expires_in > 0:
            expires_at = (now + timedelta(seconds=expires_in)).isoformat(timespec="seconds")
        return cls(
            user_id=user_id.strip(),
            user_name=user_name.strip(),
            token_type=token_type.strip(),
            token_expires_at=expires_at,
            connected_at=previous_connected_at or now.isoformat(timespec="seconds"),
            refreshed_at=now.isoformat(timespec="seconds"),
        )
