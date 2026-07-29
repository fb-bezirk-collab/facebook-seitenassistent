import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv, set_key

from app.config import BASE_DIR


ENV_FILE = BASE_DIR / ".env"


@dataclass
class MetaConfig:
    app_id: str = ""
    app_secret: str = ""
    config_id: str = ""
    redirect_uri: str = ""
    user_access_token: str = ""

    @property
    def is_configured(self) -> bool:
        return bool(
            self.app_id
            and self.app_secret
            and self.config_id
            and self.redirect_uri
        )


class MetaConfigService:
    def __init__(
        self,
        env_file: Path = ENV_FILE,
    ):
        self.env_file = env_file
        self._ensure_env_file_exists()

    def load(self) -> MetaConfig:
        load_dotenv(
            dotenv_path=self.env_file,
            override=True,
        )

        return MetaConfig(
            app_id=os.getenv(
                "META_APP_ID",
                "",
            ).strip(),
            app_secret=os.getenv(
                "META_APP_SECRET",
                "",
            ).strip(),
            config_id=os.getenv(
                "META_CONFIG_ID",
                "",
            ).strip(),
            redirect_uri=os.getenv(
                "META_REDIRECT_URI",
                "",
            ).strip(),
            user_access_token=os.getenv(
                "META_USER_ACCESS_TOKEN",
                "",
            ).strip(),
        )

    def save_user_access_token(
        self,
        token: str,
    ) -> None:
        clean_token = token.strip()

        if not clean_token:
            raise ValueError(
                "Das Facebook-Zugriffstoken ist leer."
            )

        set_key(
            dotenv_path=str(self.env_file),
            key_to_set="META_USER_ACCESS_TOKEN",
            value_to_set=clean_token,
        )

        os.environ[
            "META_USER_ACCESS_TOKEN"
        ] = clean_token

    def _ensure_env_file_exists(self) -> None:
        if self.env_file.exists():
            return

        self.env_file.write_text(
            "META_APP_ID=\n"
            "META_APP_SECRET=\n"
            "META_CONFIG_ID=\n"
            "META_REDIRECT_URI="
            "http://localhost:8000/facebook/callback\n"
            "META_USER_ACCESS_TOKEN=\n",
            encoding="utf-8",
        )