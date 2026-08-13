import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


def _storage_root() -> Path:
    configured = (
        os.getenv("APP_STORAGE_DIR", "").strip()
        or os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "").strip()
    )
    return Path(configured).expanduser().resolve() if configured else BASE_DIR


STORAGE_ROOT = _storage_root()
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
UPLOADS_DIR = STORAGE_ROOT / "uploads"
DATA_DIR = STORAGE_ROOT / "data"
PLAYWRIGHT_PROFILE_DIR = STORAGE_ROOT / "playwright_profile"
NOEN_PLAYWRIGHT_PROFILE_DIR = STORAGE_ROOT / "playwright_noen_profile"

SETTINGS_FILE = DATA_DIR / "settings.json"
PAGES_FILE = DATA_DIR / "pages.json"
POSTS_FILE = DATA_DIR / "posts.json"
META_TOKEN_FILE = DATA_DIR / "meta_user_access_token.txt"
PUBLICATIONS_FILE = DATA_DIR / "publications.json"
SOCIAL_ACCOUNTS_FILE = DATA_DIR / "social_accounts.json"
INSTAGRAM_ACCOUNTS_FILE = DATA_DIR / "instagram_accounts.json"
COMMENTS_FILE = DATA_DIR / "facebook_comments.json"
COMMENT_JOB_FILE = DATA_DIR / "facebook_comment_job.json"
COMMENT_AI_JOB_FILE = DATA_DIR / "facebook_comment_ai_job.json"
COMMENT_REFRESH_JOB_FILE = DATA_DIR / "facebook_comment_refresh_job.json"
COMMENT_USERS_FILE = DATA_DIR / "facebook_comment_users.json"
MEDIA_SUBSCRIPTIONS_FILE = DATA_DIR / "media_subscriptions.enc"


def create_required_directories() -> None:
    directories = (
        TEMPLATES_DIR,
        STATIC_DIR,
        STATIC_DIR / "css",
        STATIC_DIR / "js",
        STATIC_DIR / "images",
        UPLOADS_DIR,
        DATA_DIR,
        PLAYWRIGHT_PROFILE_DIR,
        NOEN_PLAYWRIGHT_PROFILE_DIR,
    )

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
