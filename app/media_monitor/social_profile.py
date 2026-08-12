from __future__ import annotations

from pathlib import Path

from app.config import DATA_DIR


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE_FILE = PROJECT_ROOT / "profiles" / "fpoe_social_media.md"
CUSTOM_PROFILE_FILE = DATA_DIR / "fpoe_social_media.md"


def load_social_media_profile() -> str:
    """Lädt die persistent gespeicherte Fassung, sonst das Repo-Standardprofil."""
    for path in (CUSTOM_PROFILE_FILE, DEFAULT_PROFILE_FILE):
        try:
            text = path.read_text(encoding="utf-8").strip()
            if text:
                return text
        except OSError:
            continue
    return ""


def load_default_social_media_profile() -> str:
    try:
        return DEFAULT_PROFILE_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def save_social_media_profile(text: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cleaned = (text or "").strip()
    if not cleaned:
        raise ValueError("Das FPÖ-Social-Media-Profil darf nicht leer sein.")
    CUSTOM_PROFILE_FILE.write_text(cleaned + "\n", encoding="utf-8")


def reset_social_media_profile() -> None:
    try:
        CUSTOM_PROFILE_FILE.unlink()
    except FileNotFoundError:
        pass
