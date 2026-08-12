from __future__ import annotations

import json
from pathlib import Path

from app.config import COMMENT_AI_JOB_FILE, COMMENT_JOB_FILE, COMMENT_REFRESH_JOB_FILE, COMMENTS_FILE
from app.models.facebook_comment import FacebookComment


class CommentStorage:
    def __init__(
        self,
        comments_file: Path = COMMENTS_FILE,
        job_file: Path = COMMENT_JOB_FILE,
        ai_job_file: Path = COMMENT_AI_JOB_FILE,
        refresh_job_file: Path = COMMENT_REFRESH_JOB_FILE,
    ):
        self.comments_file = comments_file
        self.job_file = job_file
        self.ai_job_file = ai_job_file
        self.refresh_job_file = refresh_job_file
        self.comments_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.comments_file.exists():
            self.save([])
        if not self.job_file.exists():
            self.save_job({"state": "idle"})
        if not self.ai_job_file.exists():
            self.save_ai_job({"state": "idle"})
        if not self.refresh_job_file.exists():
            self.save_refresh_job({"state": "idle"})

    def load(self) -> list[FacebookComment]:
        try:
            raw = json.loads(self.comments_file.read_text(encoding="utf-8") or "[]")
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(raw, list):
            return []
        return [
            FacebookComment.from_dict(item)
            for item in raw
            if isinstance(item, dict) and item.get("comment_id")
        ]

    def save(self, comments: list[FacebookComment]) -> None:
        self.comments_file.write_text(
            json.dumps(
                [comment.to_dict() for comment in comments],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def get(self, comment_id: str) -> FacebookComment | None:
        return next((item for item in self.load() if item.comment_id == comment_id), None)

    def update(self, comment: FacebookComment) -> None:
        comments = self.load()
        for index, current in enumerate(comments):
            if current.comment_id == comment.comment_id:
                comments[index] = comment
                self.save(comments)
                return
        comments.append(comment)
        self.save(comments)

    def load_job(self) -> dict:
        try:
            data = json.loads(self.job_file.read_text(encoding="utf-8") or "{}")
        except (OSError, json.JSONDecodeError):
            return {"state": "idle"}
        return data if isinstance(data, dict) else {"state": "idle"}

    def save_job(self, data: dict) -> None:
        self.job_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_ai_job(self) -> dict:
        try:
            raw = json.loads(self.ai_job_file.read_text(encoding="utf-8") or "{}")
        except (OSError, json.JSONDecodeError):
            return {"state": "idle"}
        return raw if isinstance(raw, dict) else {"state": "idle"}

    def save_ai_job(self, data: dict) -> None:
        self.ai_job_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_refresh_job(self) -> dict:
        try:
            raw = json.loads(self.refresh_job_file.read_text(encoding="utf-8") or "{}")
        except (OSError, json.JSONDecodeError):
            return {"state": "idle"}
        return raw if isinstance(raw, dict) else {"state": "idle"}

    def save_refresh_job(self, data: dict) -> None:
        self.refresh_job_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
