from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read_text(relative_path: str) -> str:
    path = PROJECT_ROOT / relative_path
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"Redaktionsdatei konnte nicht gelesen werden: {relative_path}") from exc


def load_analysis_schema() -> dict[str, Any]:
    path = PROJECT_ROOT / "schemas" / "analysis_output.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Das JSON-Schema für die Medienanalyse konnte nicht geladen werden.") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Das JSON-Schema für die Medienanalyse ist ungültig.")
    return data


def build_analysis_system_prompt() -> str:
    sections = [
        _read_text("prompts/analysis_prompt.md"),
        "\n# AKTIVES KOMMUNIKATIONSPROFIL\n" + _read_text("profiles/fpoe_noe.md"),
        "\n# ZUSATZPROFIL KOMMUNALPOLITIK\n" + _read_text("profiles/kommunalpolitik.md"),
        "\n# REDAKTIONELLE WISSENSREGELN\n" + _read_text("knowledge/argumentation.md"),
        _read_text("knowledge/kommunalpolitik.md"),
        _read_text("knowledge/headline_style.md"),
        _read_text("knowledge/facebook_style.md"),
        _read_text("knowledge/sprachregeln.md"),
        _read_text("knowledge/themenschwerpunkte.md"),
        _read_text("knowledge/gemeinderecht.md"),
    ]
    return "\n\n---\n\n".join(section for section in sections if section.strip())
