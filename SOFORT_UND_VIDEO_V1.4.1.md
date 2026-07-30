# Version 1.4.1 – Sofort veröffentlichen und Videos

## Neu

- In der Planungsübersicht steht bei allen noch nicht veröffentlichten oder stornierten Einträgen der Button **Jetzt veröffentlichen**.
- Derselbe Button bleibt auch in der Detailansicht des Entwurfs vorhanden.
- Videobeiträge werden nun auf Facebook veröffentlicht.

## Videologik

1. Bereits lokal gespeicherte Videodateien werden direkt hochgeladen.
2. Direkte MP4-/MOV-/M4V-/WEBM-URLs werden Facebook als `file_url` übergeben.
3. Bei einem Facebook-Reel- oder Facebook-Videolink öffnet die Anwendung den Link kurz im Hintergrund, ermittelt die eigentliche Videodatei, speichert sie im persistenten Upload-Ordner und lädt sie danach auf die gewählte Facebook-Seite hoch.

Der erste Video-Versuch kann deshalb deutlich länger dauern als ein Text- oder Bildbeitrag.

## Deployment

- Projektdateien ersetzen und deployen.
- Keine `.env` hochladen.
- Keine neuen Railway-Variablen erforderlich.
- Der vorhandene fehlgeschlagene Videobeitrag kann nach dem Deployment über **Jetzt veröffentlichen** erneut versucht werden.
