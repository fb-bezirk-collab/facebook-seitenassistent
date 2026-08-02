import os
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class InstagramConfig:
    app_id: str
    app_secret: str
    redirect_uri: str
    public_base_url: str

    @property
    def is_configured(self) -> bool:
        return bool(self.app_id and self.app_secret and self.redirect_uri)


def load_instagram_config() -> InstagramConfig:
    redirect_uri = os.getenv("INSTAGRAM_REDIRECT_URI", "").strip()
    public_base_url = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")

    if not public_base_url and redirect_uri:
        parsed = urlparse(redirect_uri)
        if parsed.scheme and parsed.netloc:
            public_base_url = f"{parsed.scheme}://{parsed.netloc}"

    return InstagramConfig(
        app_id=os.getenv("INSTAGRAM_APP_ID", "").strip(),
        app_secret=os.getenv("INSTAGRAM_APP_SECRET", "").strip(),
        redirect_uri=redirect_uri,
        public_base_url=public_base_url,
    )
