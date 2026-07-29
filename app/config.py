from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
UPLOADS_DIR = BASE_DIR / "uploads"
DATA_DIR = BASE_DIR / "data"

SETTINGS_FILE = DATA_DIR / "settings.json"
PAGES_FILE = DATA_DIR / "pages.json"
POSTS_FILE = DATA_DIR / "posts.json"


def create_required_directories() -> None:
    directories = (
        TEMPLATES_DIR,
        STATIC_DIR,
        STATIC_DIR / "css",
        STATIC_DIR / "js",
        STATIC_DIR / "images",
        UPLOADS_DIR,
        DATA_DIR,
    )

    for directory in directories:
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )