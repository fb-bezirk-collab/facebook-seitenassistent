import json
import os
from dataclasses import dataclass

import requests


class AiConfigurationError(RuntimeError):
    """Die OpenAI-Konfiguration fehlt oder ist unvollständig."""


class AiGenerationError(RuntimeError):
    """Beim Erstellen der Textvarianten ist ein Fehler aufgetreten."""


@dataclass(frozen=True)
class AiVariant:
    title: str
    text: str

    def to_dict(self) -> dict[str, str]:
        return {"title": self.title, "text": self.text}


class AiService:
    """Erstellt drei abgewandelte Facebook-Texte über die OpenAI Responses API."""

    api_url = "https://api.openai.com/v1/responses"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = (api_key or os.getenv("OPENAI_API_KEY", "")).strip()
        self.model = (model or os.getenv("OPENAI_MODEL", "gpt-5-mini")).strip()

    def create_variants(self, source_text: str, instructions: str = "") -> list[AiVariant]:
        cleaned_text = source_text.strip()
        if not cleaned_text:
            raise AiGenerationError("Bitte zuerst einen Beitragstext eingeben.")
        if not self.api_key:
            raise AiConfigurationError(
                "OPENAI_API_KEY ist nicht konfiguriert. Bitte die Variable in Railway speichern und neu deployen."
            )

        prompt = self._build_prompt(cleaned_text, instructions.strip())
        payload = {
            "model": self.model,
            "input": prompt,
            "max_output_tokens": 2200,
        }

        try:
            response = requests.post(
                self.api_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=90,
            )
        except requests.RequestException as exc:
            raise AiGenerationError(f"OpenAI ist derzeit nicht erreichbar: {exc}") from exc

        if response.status_code >= 400:
            message = self._api_error_message(response)
            raise AiGenerationError(f"OpenAI-Fehler: {message}")

        try:
            data = response.json()
        except ValueError as exc:
            raise AiGenerationError("OpenAI hat keine gültige Antwort geliefert.") from exc

        output_text = self._extract_output_text(data)
        variants = self._parse_variants(output_text)
        if len(variants) != 3:
            raise AiGenerationError("Die KI-Antwort enthielt nicht genau drei verwendbare Varianten.")
        return variants

    @staticmethod
    def _build_prompt(source_text: str, instructions: str) -> str:
        extra = instructions or "Keine zusätzlichen Vorgaben."
        return f"""
Du bist ein erfahrener deutschsprachiger Redakteur für Facebook-Seiten.
Erstelle aus dem Ausgangstext drei eigenständige, veröffentlichungsfertige Varianten.

Verbindliche Regeln:
- Fakten, Namen, Zahlen, Zitate und Kernaussage dürfen nicht erfunden oder verändert werden.
- Keine zusätzlichen Behauptungen ergänzen.
- Keine Anrede mit Gender-Sonderzeichen.
- Österreichische Schreibweise verwenden.
- Hashtags und Emojis nur passend und sparsam einsetzen.
- Keine Einleitungen wie „Hier sind drei Varianten“.
- Jede Variante muss ohne weitere Erklärung direkt auf Facebook verwendbar sein.

Die drei Stile:
1. „Sachlich“: klar, professionell und gut verständlich.
2. „Facebook“: lebendig, emotionaler und aufmerksamkeitsstark, aber nicht übertrieben.
3. „Kurz und prägnant“: deutlich kürzer, zugespitzt und mit klarer Kernaussage.

Zusätzliche Vorgaben der Benutzerin:
{extra}

Ausgangstext:
---
{source_text}
---

Antworte ausschließlich als gültiges JSON-Array in genau dieser Form:
[
  {{"title":"Sachlich","text":"..."}},
  {{"title":"Facebook","text":"..."}},
  {{"title":"Kurz und prägnant","text":"..."}}
]
""".strip()

    @staticmethod
    def _extract_output_text(data: dict) -> str:
        direct = data.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()

        parts: list[str] = []
        for output in data.get("output", []):
            if not isinstance(output, dict):
                continue
            for content in output.get("content", []):
                if not isinstance(content, dict):
                    continue
                text = content.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
        return "\n".join(parts).strip()

    @staticmethod
    def _parse_variants(raw_text: str) -> list[AiVariant]:
        value = raw_text.strip()
        if value.startswith("```"):
            value = value.removeprefix("```json").removeprefix("```")
            value = value.removesuffix("```").strip()

        try:
            items = json.loads(value)
        except json.JSONDecodeError as exc:
            raise AiGenerationError("Die KI-Antwort konnte nicht als Textvarianten gelesen werden.") from exc

        if not isinstance(items, list):
            return []

        variants: list[AiVariant] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "Variante").strip()
            text = str(item.get("text") or "").strip()
            if text:
                variants.append(AiVariant(title=title, text=text))
        return variants[:3]

    @staticmethod
    def _api_error_message(response: requests.Response) -> str:
        try:
            data = response.json()
            error = data.get("error", {})
            message = error.get("message") if isinstance(error, dict) else None
            if message:
                return str(message)
        except ValueError:
            pass
        return response.text.strip() or f"HTTP {response.status_code}"
