# Update 3.0.2

## Neu
- `app/media_monitor/fetchers/unzensuriert.py`
- `app/media_monitor/fetchers/nius_at.py`
- `app/media_monitor/fetchers/fob.py`
- `app/media_monitor/fetchers/zurzeit.py`
- `app/media_monitor/fetchers/nfz.py`
- `VERSION_3.0.2.md`

## Geändert
- `app/media_monitor/fetchers/__init__.py`
- `app/media_monitor/service.py`
- `CHANGELOG.md`
- `UPDATE.md`

## Update 3.0.3
Gegenüber 3.0.2 wurden geändert:
- `app/media_monitor/fetchers/common.py`
- `app/media_monitor/fetchers/generic.py`
- `app/media_monitor/fetchers/nius_at.py`
- `app/media_monitor/storage.py`

Neu:
- `VERSION_3.0.3.md`
## Update 3.1.0
NÖN-Abo-Pilot: neue Medien-Abo-Einstellungen, verschlüsselte Session-Cookies und automatische Verwendung bei NÖN-KI-Analysen.

## Update 3.1.1
In Railway zusätzlich `NOEN_USERNAME` und `NOEN_PASSWORD` setzen und neu deployen. Danach unter Einstellungen → Medien-Abos zuerst „NÖN jetzt anmelden / Sitzung erneuern“ verwenden. `NOEN_LOGIN_URL` ist nur optional nötig, falls die Login-Maske nicht automatisch gefunden wird.
