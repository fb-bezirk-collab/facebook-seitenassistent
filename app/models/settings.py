from dataclasses import asdict, dataclass


@dataclass
class AppSettings:
    facebook_app_id: str = ""
    facebook_app_secret: str = ""
    facebook_user_token: str = ""

    openai_api_key: str = ""
    openai_model: str = ""

    default_page_id: str = ""
    default_rewrite_mode: str = "original"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(
        cls,
        data: dict,
    ) -> "AppSettings":
        return cls(
            facebook_app_id=str(
                data.get("facebook_app_id", "")
            ),
            facebook_app_secret=str(
                data.get("facebook_app_secret", "")
            ),
            facebook_user_token=str(
                data.get("facebook_user_token", "")
            ),
            openai_api_key=str(
                data.get("openai_api_key", "")
            ),
            openai_model=str(
                data.get("openai_model", "")
            ),
            default_page_id=str(
                data.get("default_page_id", "")
            ),
            default_rewrite_mode=str(
                data.get(
                    "default_rewrite_mode",
                    "original",
                )
            ),
        )