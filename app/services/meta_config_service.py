import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from app.config import BASE_DIR, META_TOKEN_FILE


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
        return bool(self.app_id and self.app_secret and self.config_id and self.redirect_uri)


class MetaConfigService:
    def __init__(self, env_file: Path = ENV_FILE, token_file: Path = META_TOKEN_FILE):
        self.env_file = env_file
        self.token_file = token_file
        self.token_file.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> MetaConfig:
        if self.env_file.exists():
            load_dotenv(dotenv_path=self.env_file, override=False)

        persisted_token = ""
        try:
            persisted_token = self.token_file.read_text(encoding="utf-8").strip()
        except OSError:
            pass

        return MetaConfig(
            app_id=os.getenv("META_APP_ID", "").strip(),
            app_secret=os.getenv("META_APP_SECRET", "").strip(),
            config_id=os.getenv("META_CONFIG_ID", "").strip(),
            redirect_uri=os.getenv("META_REDIRECT_URI", "").strip(),
            user_access_token=(
                os.getenv("META_USER_ACCESS_TOKEN", "").strip() or persisted_token
            ),
        )

    def save_user_access_token(self, token: str) -> None:
        clean_token = token.strip()
        if not clean_token:
            raise ValueError("Das Facebook-Zugriffstoken ist leer.")

        self.token_file.write_text(clean_token, encoding="utf-8")
        os.environ["META_USER_ACCESS_TOKEN"] = clean_token
