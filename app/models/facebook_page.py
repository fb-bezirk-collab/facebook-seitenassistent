from dataclasses import asdict, dataclass


@dataclass
class FacebookPage:
    page_id: str
    name: str
    access_token: str = ""
    is_default: bool = False
    is_active: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(
        cls,
        data: dict,
    ) -> "FacebookPage":
        return cls(
            page_id=str(data.get("page_id", "")),
            name=str(data.get("name", "")),
            access_token=str(
                data.get("access_token", "")
            ),
            is_default=bool(
                data.get("is_default", False)
            ),
            is_active=bool(
                data.get("is_active", True)
            ),
        )