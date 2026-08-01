import json
from pathlib import Path

from app.config import PAGES_FILE, SETTINGS_FILE
from app.models.facebook_page import FacebookPage
from app.models.settings import AppSettings


class SettingsService:
    def __init__(
        self,
        settings_file: Path = SETTINGS_FILE,
        pages_file: Path = PAGES_FILE,
    ):
        self.settings_file = settings_file
        self.pages_file = pages_file

        self._ensure_files_exist()

    def load_settings(self) -> AppSettings:
        data = self._read_json(
            self.settings_file,
            default={},
        )

        if not isinstance(data, dict):
            return AppSettings()

        return AppSettings.from_dict(data)

    def save_settings(
        self,
        settings: AppSettings,
    ) -> None:
        self._write_json(
            self.settings_file,
            settings.to_dict(),
        )

    def load_pages(self) -> list[FacebookPage]:
        data = self._read_json(
            self.pages_file,
            default=[],
        )

        if not isinstance(data, list):
            return []

        pages: list[FacebookPage] = []

        for item in data:
            if not isinstance(item, dict):
                continue

            page = FacebookPage.from_dict(item)

            if not page.page_id or not page.name:
                continue

            pages.append(page)

        return pages

    def save_pages(
        self,
        pages: list[FacebookPage],
    ) -> None:
        self._write_json(
            self.pages_file,
            [
                page.to_dict()
                for page in pages
            ],
        )

    def _ensure_files_exist(self) -> None:
        self.settings_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.pages_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if not self.settings_file.exists():
            self._write_json(
                self.settings_file,
                AppSettings().to_dict(),
            )

        if not self.pages_file.exists():
            self._write_json(
                self.pages_file,
                [],
            )

    @staticmethod
    def _read_json(
        file_path: Path,
        default,
    ):
        try:
            content = file_path.read_text(
                encoding="utf-8"
            ).strip()

            if not content:
                return default

            return json.loads(content)

        except (
            OSError,
            json.JSONDecodeError,
        ):
            return default

    @staticmethod
    def _write_json(
        file_path: Path,
        data,
    ) -> None:
        file_path.write_text(
            json.dumps(
                data,
                ensure_ascii=False,
                indent=4,
            ),
            encoding="utf-8",
        )