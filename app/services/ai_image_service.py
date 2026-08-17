from __future__ import annotations

import base64
import os
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont, ImageStat

from app.services.media_storage import MediaStorage


class AiImageError(RuntimeError):
    pass


class AiImageService:
    responses_url = "https://api.openai.com/v1/responses"
    images_url = "https://api.openai.com/v1/images/generations"

    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.text_model = os.getenv("OPENAI_MEDIA_ANALYSIS_MODEL", os.getenv("OPENAI_MODEL", "gpt-5-mini")).strip()
        self.image_model = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2").strip()
        self.storage = MediaStorage()

    def suggest_prompt(self, *, title: str, text: str, source_url: str = "", source_hint: str = "", image_brief: str = "") -> str:
        if not self.api_key:
            raise AiImageError("OPENAI_API_KEY ist nicht konfiguriert.")
        content = (text or "").strip()
        if not content:
            raise AiImageError("Für einen Bildvorschlag wird zuerst ein Beitragstext benötigt.")
        developer = (
            "Du erstellst präzise Bildprompts für politische Social-Media-Beiträge in Österreich. "
            "Erfinde keine Personen, Zitate, Zahlen, Logos oder konkreten Tatsachen. "
            "Der Bildinhalt soll die Kernaussage des Beitrags visuell transportieren, vorzugsweise als "
            "plausibles Symbolbild. Keine Schrift, Schlagzeilen, Logos, Wasserzeichen oder Texttafeln im Motiv. "
            "Wenn eine reale Person nicht sicher aus dem gelieferten Text hervorgeht, verwende keine identifizierbare Person. "
            "Antworte ausschließlich mit dem fertigen deutschsprachigen Bildprompt, ohne Einleitung."
        )
        user = f"Titel: {title.strip()}\n\nBeitrag:\n{content[:7000]}"
        if image_brief.strip():
            user += f"\n\nVorgabe des Benutzers für das Bild (besonders wichtig):\n{image_brief.strip()[:3000]}"
        if source_hint.strip():
            user += f"\n\nVorhandene Bildidee aus der Medienanalyse: {source_hint.strip()[:1500]}"
        if source_url.strip():
            user += "\n\nEs gibt einen verlinkten Medienartikel als Quelle; er dient nur dem Kontext."
        payload = {
            "model": self.text_model,
            "input": [
                {"role": "developer", "content": developer},
                {"role": "user", "content": user},
            ],
            "reasoning": {"effort": "minimal"},
            "text": {"verbosity": "low"},
            "max_output_tokens": 2200,
        }
        try:
            response = requests.post(
                self.responses_url,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=90,
            )
        except requests.RequestException as exc:
            raise AiImageError(f"OpenAI ist derzeit nicht erreichbar: {exc}") from exc
        if response.status_code >= 400:
            raise AiImageError(self._error_message(response))
        try:
            data = response.json()
        except ValueError as exc:
            raise AiImageError("OpenAI hat keine gültige Antwort geliefert.") from exc
        result = self._extract_output_text(data).strip().strip('"')
        if not result:
            raise AiImageError("Es konnte kein Bildprompt erzeugt werden.")
        return result

    def refine_prompt(self, *, current_prompt: str, change_request: str, title: str = "", text: str = "") -> str:
        if not self.api_key:
            raise AiImageError("OPENAI_API_KEY ist nicht konfiguriert.")
        current = (current_prompt or "").strip()
        change = (change_request or "").strip()
        if not current:
            raise AiImageError("Es gibt noch keinen Bildprompt zum Überarbeiten.")
        if not change:
            raise AiImageError("Bitte einen Änderungswunsch eingeben.")
        developer = (
            "Du überarbeitest einen bestehenden deutschsprachigen Bildprompt für einen politischen Social-Media-Beitrag in Österreich. "
            "Setze den Änderungswunsch gezielt um und erhalte alle sinnvollen Teile des bisherigen Prompts. "
            "Erfinde keine Personen, Zitate, Zahlen, Logos oder Tatsachen. Keine Schrift, Schlagzeilen, Logos oder Wasserzeichen im Motiv. "
            "Antworte ausschließlich mit dem vollständig überarbeiteten Bildprompt, ohne Erklärung."
        )
        user = f"Bisheriger Bildprompt:\n{current[:5000]}\n\nÄnderungswunsch:\n{change[:2500]}"
        if title.strip() or text.strip():
            user += f"\n\nKontext des Beitrags:\nTitel: {title.strip()}\n{text.strip()[:3500]}"
        payload = {
            "model": self.text_model,
            "input": [{"role": "developer", "content": developer}, {"role": "user", "content": user}],
            "reasoning": {"effort": "minimal"},
            "text": {"verbosity": "low"},
            "max_output_tokens": 2200,
        }
        try:
            response = requests.post(self.responses_url, headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}, json=payload, timeout=90)
        except requests.RequestException as exc:
            raise AiImageError(f"OpenAI ist derzeit nicht erreichbar: {exc}") from exc
        if response.status_code >= 400:
            raise AiImageError(self._error_message(response))
        try:
            data = response.json()
        except ValueError as exc:
            raise AiImageError("OpenAI hat keine gültige Antwort geliefert.") from exc
        result = self._extract_output_text(data).strip().strip('"')
        if not result:
            raise AiImageError("Der Bildprompt konnte nicht überarbeitet werden.")
        return result

    def generate_image(self, *, prompt: str, style: str = "fotorealistisch") -> str:
        if not self.api_key:
            raise AiImageError("OPENAI_API_KEY ist nicht konfiguriert.")
        clean_prompt = (prompt or "").strip()
        if not clean_prompt:
            raise AiImageError("Bitte zuerst einen Bildprompt eingeben.")
        style_instruction = {
            "fotorealistisch": "Fotorealistische Darstellung, glaubwürdige österreichische Pressefoto-Ästhetik.",
            "pressefoto": "Authentischer Pressefoto-Stil, natürliche Beleuchtung, dokumentarische Wirkung.",
            "illustration": "Hochwertige politische Editorial-Illustration, klar und seriös.",
            "cartoon": "Pointierte, aber nicht beleidigende politische Cartoon-Illustration.",
            "aquarell": "Hochwertige Aquarell-Illustration mit klar erkennbarer Bildaussage.",
            "cinematic": "Dramatische cineastische Bildsprache, realistische Lichtstimmung.",
            "symbolbild": "Klares, hochwertiges Symbolbild mit starker visueller Metapher.",
        }.get(style, "Fotorealistische Darstellung.")
        final_prompt = (
            f"{style_instruction}\n\n{clean_prompt}\n\n"
            "Format: quadratische Social-Media-Grafik. Keine eingebauten Wörter, Beschriftungen, Untertitel, "
            "Logos oder Wasserzeichen. Am unteren rechten Rand etwas ruhige Bildfläche freihalten; "
            "die Anwendung setzt dort später selbst die Kennzeichnung 'Erstellt mit KI'."
        )
        payload = {
            "model": self.image_model,
            "prompt": final_prompt,
            "size": "1024x1024",
            "quality": "medium",
            "n": 1,
        }
        try:
            response = requests.post(
                self.images_url,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=180,
            )
        except requests.RequestException as exc:
            raise AiImageError(f"Bild-KI ist derzeit nicht erreichbar: {exc}") from exc
        if response.status_code >= 400:
            raise AiImageError(self._error_message(response))
        try:
            data = response.json()
            item = (data.get("data") or [])[0]
        except (ValueError, IndexError, TypeError) as exc:
            raise AiImageError("Die Bild-KI hat keine verwendbare Bildantwort geliefert.") from exc

        raw: bytes
        b64 = item.get("b64_json") if isinstance(item, dict) else None
        url = item.get("url") if isinstance(item, dict) else None
        if b64:
            try:
                raw = base64.b64decode(b64)
            except ValueError as exc:
                raise AiImageError("Das erzeugte Bild konnte nicht dekodiert werden.") from exc
        elif url:
            try:
                image_response = requests.get(url, timeout=90)
                image_response.raise_for_status()
                raw = image_response.content
            except requests.RequestException as exc:
                raise AiImageError(f"Das erzeugte Bild konnte nicht geladen werden: {exc}") from exc
        else:
            raise AiImageError("Die Bild-KI hat weder Bilddaten noch eine Bild-URL geliefert.")

        target = self.storage.create_file_path("png")
        self._save_with_ai_label(raw, target)
        return str(target)

    def _save_with_ai_label(self, raw: bytes, target: Path) -> None:
        try:
            with Image.open(BytesIO(raw)) as source:
                image = source.convert("RGB")
        except Exception as exc:
            raise AiImageError("Das erzeugte Bildformat konnte nicht verarbeitet werden.") from exc

        width, height = image.size
        text = "Erstellt mit KI"
        font_size = max(14, round(min(width, height) * 0.021))
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", font_size)
        except OSError:
            font = ImageFont.load_default()
        draw = ImageDraw.Draw(image)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        margin = max(10, round(min(width, height) * 0.012))
        x = max(margin, width - tw - margin)
        y = max(margin, height - th - margin)

        sample_left = max(0, x - margin // 2)
        sample_top = max(0, y - margin // 2)
        sample = image.crop((sample_left, sample_top, width, height)).convert("L")
        luminance = ImageStat.Stat(sample).mean[0] if sample.size[0] and sample.size[1] else 128
        fill = (245, 245, 245) if luminance < 135 else (25, 25, 25)
        stroke = (20, 20, 20) if luminance < 135 else (245, 245, 245)
        draw.text((x, y), text, font=font, fill=fill, stroke_width=max(1, font_size // 14), stroke_fill=stroke)
        target.parent.mkdir(parents=True, exist_ok=True)
        image.save(target, format="PNG", optimize=True)

    @staticmethod
    def _extract_output_text(data: dict) -> str:
        direct = data.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct
        parts: list[str] = []
        for output in data.get("output", []) or []:
            if not isinstance(output, dict):
                continue
            for content in output.get("content", []) or []:
                if not isinstance(content, dict):
                    continue
                text = content.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)

    @staticmethod
    def _error_message(response: requests.Response) -> str:
        try:
            data = response.json()
            error = data.get("error", {})
            if isinstance(error, dict) and error.get("message"):
                return f"OpenAI-Fehler: {error['message']}"
        except ValueError:
            pass
        return f"OpenAI-Fehler HTTP {response.status_code}."
