# Railway-Deployment – Facebook Seitenassistent 1.0

## 1. Dateien auf GitHub hochladen

Das Repository muss im Hauptverzeichnis mindestens enthalten:

- `app/`
- `templates/`
- `requirements.txt`
- `Dockerfile`
- `.dockerignore`
- `.gitignore`

Nicht hochladen: `.env`, `.venv`, `data`, `uploads`, `playwright_profile`.

## 2. Railway mit GitHub verbinden

1. In Railway **New Project** wählen.
2. **GitHub Repository** anklicken.
3. Das Repository `facebook-seitenassistent` auswählen.
4. Railway erkennt das `Dockerfile` automatisch und startet den Build.

## 3. Persistentes Volume anlegen

Beim Railway-Service unter **Settings → Volumes** ein Volume hinzufügen.

Mount Path:

```text
/app/storage
```

Dort werden dauerhaft gespeichert:

- `/app/storage/data`
- `/app/storage/uploads`
- `/app/storage/playwright_profile`

## 4. Railway-Variablen eintragen

Unter **Variables**:

```text
META_APP_ID=...
META_APP_SECRET=...
META_CONFIG_ID=...
META_REDIRECT_URI=https://DEINE-DOMAIN/facebook/callback
PLAYWRIGHT_HEADLESS=true
APP_STORAGE_DIR=/app/storage
```

`META_USER_ACCESS_TOKEN` ist optional. Ein beim OAuth-Login erzeugtes Token wird im Volume gespeichert.

## 5. Domain erzeugen

Unter **Settings → Networking** eine Railway-Domain erzeugen.

Danach `META_REDIRECT_URI` auf diese Domain setzen, z. B.:

```text
https://facebook-seitenassistent-production.up.railway.app/facebook/callback
```

Dieselbe URL muss in der Meta-App als gültige OAuth-Redirect-URI eingetragen werden.

## 6. Funktionstest

- Startseite: `/`
- Healthcheck: `/health`
- Entwürfe: `/drafts`
- Einstellungen: `/settings`

Erwartete Healthcheck-Antwort:

```json
{"status":"ok","version":"1.0.0"}
```

## Wichtiger Hinweis zu Facebook/Playwright

Auf Railway läuft Chromium ohne sichtbares Browserfenster (`headless`). Das lokale Browserprofil wird nicht automatisch auf Railway übertragen. Falls Facebook den Import nur mit einem bestehenden Login zulässt, muss der Login-/Cookie-Workflow später noch speziell für den Serverbetrieb gelöst werden.
