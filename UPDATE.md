# Version 2.1.0 – Krone, Kurier, Heute und oe24

## Neu
- `app/media_monitor/fetchers/common.py`
  - gemeinsamer HTML-/JSON-LD-Parser für Medienseiten
- `app/media_monitor/fetchers/kurier.py`
  - KURIER über den offiziellen RSS-Feed
- `app/media_monitor/fetchers/heute.py`
  - Heute über die Startseite mit JSON-LD-/Link-Fallback
- `app/media_monitor/fetchers/oe24.py`
  - oe24 über die Startseite mit JSON-LD-/Link-Fallback

## Geändert
- `app/media_monitor/fetchers/__init__.py`
  - Export aller vier Quellen
- `app/media_monitor/service.py`
  - alle vier Medien werden in einem Durchlauf abgerufen
  - jede Quelle läuft unabhängig; eine fehlerhafte Quelle blockiert die anderen nicht
  - Quellenstatistik pro Abruf
- `app/routers/media_monitor.py`
  - Übergabe der Quellenstatistik an die Oberfläche
- `templates/media_monitor.html`
  - Abrufmeldung zeigt Krone, Kurier, Heute und oe24 getrennt an
  - Fehlermeldungen gelten nun für den gesamten Medienabruf

## Unverändert
- bestehende KI-Bewertung
- regelbasierter Vorfilter
- Dublettenschutz innerhalb der gespeicherten Meldungen
- Grenzwert 6,5 Punkte

## Nächster geplanter Schritt
Trending-/Breaking-Erkennung: dieselbe Geschichte in mehreren Medien erkennen und als TRENDING bzw. BREAKING kennzeichnen.
