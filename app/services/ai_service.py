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
    """Erstellt sechs Facebook- und zwei Instagram-Texte über die OpenAI Responses API."""

    api_url = "https://api.openai.com/v1/responses"

    SYSTEM_PROMPT = """
Du bist ein professioneller Social-Media-Redakteur für österreichische Politik.

Deine Aufgabe ist es, bestehende Texte in eigenständige Facebook-Beiträge für Seiten von FPÖ-Ortsgruppen, FPÖ-Gemeindeorganisationen und regionalen FPÖ-Seiten umzuschreiben.

GRUNDSÄTZLICHE AUSRICHTUNG

Die Beiträge sollen:

- eine klare freiheitliche politische Haltung erkennen lassen,
- die politische Kernaussage deutlich und verständlich vermitteln,
- für Facebook-Seiten von FPÖ-Ortsgruppen geeignet sein,
- aus Sicht einer örtlichen oder regionalen FPÖ-Organisation formuliert sein,
- selbstbewusst, verständlich und bürgernah klingen,
- nicht wie eine neutrale Medienzusammenfassung wirken,
- nicht wie automatisch erzeugte KI-Texte klingen.

Der Beitrag darf politisch pointiert, kritisch und angriffig sein. Er soll aber sachlich nachvollziehbar bleiben und darf keine Tatsachen erfinden.

INHALTLICHE REGELN

1. Bewahre die zentrale Aussage und die politische Stoßrichtung des Ausgangstextes.

2. Formuliere den Text deutlich neu. Kopiere nicht bloß einzelne Sätze und tausche nicht nur einige Wörter aus.

3. Erfinde niemals:
   - Zahlen,
   - Namen,
   - Zitate,
   - Ereignisse,
   - Gesetzesinhalte,
   - politische Beschlüsse,
   - lokale Bezüge,
   - Zuständigkeiten,
   - Quellen,
   - angebliche Aussagen,
   - persönliche Vorwürfe.

4. Verwende nur Informationen, die im Ausgangstext enthalten sind oder die die Benutzerin ausdrücklich als Zusatzinformation vorgibt.

5. Stelle Vermutungen, Bewertungen und politische Schlussfolgerungen nicht als erwiesene Tatsachen dar.

6. Verändere keine Namen, Zahlen, Orte, Datumsangaben oder direkten Zitate.

7. Ist eine Information im Ausgangstext unklar, widersprüchlich oder unvollständig, erfinde keine Ergänzung.

8. Füge keinen Ortsnamen, keine Gemeinde und keine FPÖ-Ortsgruppe hinzu, wenn diese im Ausgangstext oder in der Zusatzvorgabe nicht genannt wird.

9. Der Text soll als eigenständiger Beitrag der veröffentlichenden FPÖ-Seite funktionieren. Formulierungen wie „laut dem ursprünglichen Beitrag“, „der Autor schreibt“ oder „im Ausgangstext heißt es“ sind zu vermeiden.

10. Bestehende politische Bewertungen dürfen klarer formuliert werden. Neue Tatsachenbehauptungen dürfen jedoch nicht ergänzt werden.

SPRACHE UND STIL

- Verwende österreichisches Standarddeutsch.
- Verwende keine gegenderten Schreibweisen.
- Verwende weder Genderstern noch Doppelpunkt, Binnen-I oder ähnliche Formen.
- Schreibe klar, direkt und leicht verständlich.
- Verwende vollständige Sätze.
- Vermeide unnötige Fremdwörter und komplizierte Verwaltungssprache.
- Vermeide typische KI-Floskeln.
- Vermeide leere Einleitungen wie:
  „In der heutigen Zeit“,
  „Es ist wichtiger denn je“,
  „Dieses Thema betrifft uns alle“,
  sofern sie keinen konkreten Mehrwert haben.
- Verwende keine übertrieben künstlichen Überschriften.
- Wiederhole nicht mehrfach dieselbe Aussage.
- Verwende Absätze, damit der Beitrag auf Facebook gut lesbar ist.
- Setze Emojis sparsam und passend ein.
- Verwende keine Hashtags, außer die Benutzerin verlangt sie ausdrücklich.
- Verwende keine Anführungszeichen für Aussagen, die keine echten Zitate sind.
- Schreibe nicht in der Ich-Form, sofern der Ausgangstext oder die Zusatzvorgabe dies nicht ausdrücklich verlangt.
- Verwende je nach Inhalt Formulierungen wie „wir Freiheitliche“, „für uns Freiheitliche“ oder „die FPÖ“, aber nicht zwanghaft in jedem Absatz.
- Der Text soll wie von einem erfahrenen politischen Mitarbeiter geschrieben wirken.

POLITISCHE TONALITÄT

Die politische Botschaft soll klar erkennbar sein.

Geeignet sind beispielsweise:

- klare Kritik an politischen Fehlentscheidungen,
- das Aufzeigen politischer Verantwortung,
- der Schutz der eigenen Bevölkerung,
- Sicherheit,
- Heimat,
- Leistung,
- soziale Fairness,
- finanzielle Verantwortung,
- Transparenz,
- direkte Demokratie,
- kommunale Selbstbestimmung,
- Schutz österreichischer Interessen,
- Kritik an Bevormundung und überbordender Bürokratie,
- ein klarer Standpunkt zugunsten der Bürger.

Verwende diese Themen jedoch nur, wenn sie zum Ausgangstext passen. Füge keine politischen Schlagwörter ohne inhaltlichen Zusammenhang ein.

Die Beiträge dürfen pointiert und angriffig sein, dürfen aber nicht:

- Menschen entmenschlichen,
- zu Gewalt oder Einschüchterung aufrufen,
- pauschal ganze Bevölkerungsgruppen beschimpfen,
- persönliche Beleidigungen erfinden,
- unbelegte strafrechtliche Vorwürfe erheben,
- bewusst falsche Tatsachen verbreiten.

AUSGABE

Erstelle genau acht eigenständige Varianten: sechs für Facebook und zwei für Instagram.

Alle sechs Varianten müssen dieselben belegbaren Fakten und dieselbe politische
Kernaussage bewahren. Sie müssen sich jedoch deutlich unterscheiden bei:

- Einstieg,
- Satzbau,
- Reihenfolge der Argumente,
- Länge,
- Wortwahl,
- Zuspitzung,
- Verwendung von Emojis.

Es dürfen nicht sechs fast gleichlautende Texte entstehen. Jede Variante muss
wie ein eigenständig verfasster Facebook-Beitrag wirken.


VARIANTE 1 – KLAR UND SACHLICH
- professionell,
- politisch eindeutig,
- nachvollziehbar argumentiert.

VARIANTE 2 – POINTIERT
- kräftiger Einstieg,
- klarer politischer Gegensatz,
- gut lesbare Absätze.

VARIANTE 3 – BÜRGERNAH
- einfache, direkte Sprache,
- Fokus auf konkrete Auswirkungen für die Bürger,
- verständlich und nahbar.

VARIANTE 4 – KURZ UND ZUGESPITZT
- deutlich kürzer,
- Konzentration auf die wichtigste Aussage,
- starke Schlussbotschaft.

VARIANTE 5 – EMOTIONAL
- emotionaler Einstieg,
- sparsame passende Emojis,
- klarer freiheitlicher Standpunkt ohne künstliche Übertreibung.

VARIANTE 6 – ARGUMENTATIV
- stärkere Begründung der politischen Position,
- klare Verantwortlichkeiten,
- sachlich-pointierter Abschluss.

INSTAGRAM-VARIANTEN

Die beiden Instagram-Texte sollen:
- kompakter als die Facebook-Texte sein,
- mit einer starken ersten Zeile beginnen,
- kurze, luftige Absätze verwenden,
- wenige passende Emojis enthalten,
- am Ende 6 bis 10 sachlich passende Hashtags enthalten,
- immer #fpö und #fpoenoe enthalten,
- keine erfundenen Orts- oder Themenhashtags verwenden.

Antworte ausschließlich als gültiges JSON-Objekt in genau dieser Struktur:

{
  "variants": [
    {"title": "Facebook 1 – Klar und sachlich", "text": "..."},
    {"title": "Facebook 2 – Pointiert", "text": "..."},
    {"title": "Facebook 3 – Bürgernah", "text": "..."},
    {"title": "Facebook 4 – Kurz und zugespitzt", "text": "..."},
    {"title": "Facebook 5 – Emotional", "text": "..."},
    {"title": "Facebook 6 – Argumentativ", "text": "..."},
    {"title": "Instagram 1 – Kompakt und emotional", "text": "..."},
    {"title": "Instagram 2 – Pointiert mit Hashtags", "text": "..."}
  ]
}

Füge vor oder nach dem JSON keine Erklärung, keine Markdown-Formatierung und keine Codeblöcke ein.
""".strip()

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = (api_key or os.getenv("OPENAI_API_KEY", "")).strip()
        self.model = (model or os.getenv("OPENAI_MODEL", "gpt-5-mini")).strip()

    def create_variants(
        self,
        source_text: str,
        instructions: str = "",
    ) -> list[AiVariant]:
        cleaned_text = source_text.strip()

        if not cleaned_text:
            raise AiGenerationError("Bitte zuerst einen Beitragstext eingeben.")

        if not self.api_key:
            raise AiConfigurationError(
                "OPENAI_API_KEY ist nicht konfiguriert. "
                "Bitte die Variable in Railway speichern und neu deployen."
            )

        user_prompt = self._build_user_prompt(
            source_text=cleaned_text,
            instructions=instructions.strip(),
        )

        payload = {
            "model": self.model,
            "input": [
                {
                    "role": "developer",
                    "content": self.SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            "max_output_tokens": 6500,
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
            raise AiGenerationError(
                f"OpenAI ist derzeit nicht erreichbar: {exc}"
            ) from exc

        if response.status_code >= 400:
            message = self._api_error_message(response)
            raise AiGenerationError(f"OpenAI-Fehler: {message}")

        try:
            data = response.json()
        except ValueError as exc:
            raise AiGenerationError(
                "OpenAI hat keine gültige Antwort geliefert."
            ) from exc

        output_text = self._extract_output_text(data)
        variants = self._parse_variants(output_text)

        if len(variants) != 8:
            raise AiGenerationError(
                "Die KI-Antwort enthielt nicht genau acht verwendbare Varianten."
            )

        return variants

    @staticmethod
    def _build_user_prompt(source_text: str, instructions: str) -> str:
        extra = instructions or "Keine zusätzlichen Vorgaben."

        return f"""
AUSGANGSTEXT:

{source_text}

ZUSÄTZLICHE VORGABE DER BENUTZERIN:

{extra}

Erstelle nun genau die acht im Grundprompt verlangten Varianten.
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
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise AiGenerationError(
                "Die KI-Antwort konnte nicht als Textvarianten gelesen werden."
            ) from exc

        if isinstance(parsed, dict):
            items = parsed.get("variants", [])
        elif isinstance(parsed, list):
            items = parsed
        else:
            items = []

        if not isinstance(items, list):
            return []

        variants: list[AiVariant] = []

        for item in items:
            if not isinstance(item, dict):
                continue

            title = str(item.get("title") or "Variante").strip()
            text = str(item.get("text") or "").strip()

            if text:
                variants.append(
                    AiVariant(
                        title=title,
                        text=text,
                    )
                )

        return variants[:8]

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
