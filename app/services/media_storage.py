from datetime import date
from pathlib import Path
from uuid import uuid4


class MediaStorage:
    def __init__(self, base_dir: str | Path = "uploads/facebook"):
        self.base_dir = Path(base_dir)

    def create_file_path(self, file_extension: str) -> Path:
        today = date.today().isoformat()
        target_dir = self.base_dir / today
        target_dir.mkdir(parents=True, exist_ok=True)

        clean_extension = file_extension.lower().lstrip(".") or "bin"
        return target_dir / f"{uuid4().hex}.{clean_extension}"
