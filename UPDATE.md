# Update 2.2.1 – Upstream-Timeout-Fix

## Ursache
Mit 12 Medienquellen plus KI-Bewertung dauerte ein manueller Abruf länger als ein einzelner Railway-HTTP-Request. Railway konnte den Request daher mit `upstream error` abbrechen, obwohl der eigentliche Medienabruf noch arbeitete.

## Neu
- `app/media_monitor/job.py`
  - führt den Medienabruf als Hintergrundjob aus
  - speichert den aktuellen Jobstatus dauerhaft unter `data/media_monitor_job.json`

## Geändert
- `app/routers/media_monitor.py`
  - startet den Abruf sofort im Hintergrund und antwortet dem Browser ohne langen Warte-Request
- `templates/media_monitor.html`
  - zeigt „Abruf läuft …“
  - aktualisiert die Seite während des Abrufs automatisch alle 5 Sekunden
  - zeigt nach Abschluss wieder die Statistik pro Quelle

## Unverändert
Die 12 Medienquellen, Dublettenerkennung, Vorfilter und KI-Bewertung bleiben unverändert.

## Version 2.3.0 – APA-Zeitfix + Trending/Breaking

NEU:
- `app/media_monitor/trending.py`
  - KI-gestützte medienübergreifende Erkennung desselben konkreten Nachrichtenereignisses
  - 2 Quellen: „Mehrere Medien“
  - 3+ Quellen innerhalb von 12 Stunden: „TRENDING“
  - 4+ Quellen innerhalb von 6 Stunden: „BREAKING“

GEÄNDERT:
- `app/media_monitor/fetchers/common.py`
  - sichtbare Datumsangaben mit zweistelligem Jahr und optionalen Sekunden
  - unterstützt insbesondere APA-Format wie `Freitag, 07.08.26, 14:31:53`
- `app/media_monitor/service.py`
  - Trending-Erkennung nach Vorfilter und KI-Bewertung
- `app/media_monitor/job.py`
  - speichert Anzahl erkannter Themencluster
- `app/routers/media_monitor.py`
  - übergibt Trendstatistik an die Oberfläche
- `templates/media_monitor.html`
  - Badges für Mehrere Medien / TRENDING / BREAKING und Quellenliste

HINWEIS:
Die einzelnen Artikel bleiben erhalten. Die Trend-Erkennung markiert zusammengehörige Meldungen, ohne sie zu löschen oder automatisch zu veröffentlichen.
