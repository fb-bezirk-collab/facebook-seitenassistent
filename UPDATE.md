# Update 2.4.0

## Neu

- `app/media_monitor/analysis.py`
- `templates/media_analysis.html`

## Geändert

- `app/media_monitor/storage.py`
- `app/routers/media_monitor.py`
- `templates/media_monitor.html`
- `CHANGELOG.md`
- `UPDATE.md`

## Funktion

Im Medienmonitor steht bei jeder Meldung jetzt „KI analysieren“. Die Analyse läuft als Hintergrundjob. Die Detailseite aktualisiert sich während der Verarbeitung automatisch und zeigt danach eine strukturierte redaktionelle Analyse. Wenn ein Artikel zu einem bereits erkannten medienübergreifenden Ereignis gehört, werden die weiteren Quellen in die Analyse einbezogen.

Es werden keine Beiträge automatisch erstellt oder veröffentlicht. Das bleibt für den nächsten Entwicklungsschritt vorgesehen.
