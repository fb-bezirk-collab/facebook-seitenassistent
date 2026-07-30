# Facebook-Verknüpfung einrichten – Version 1.3

## 1. Meta-App vorbereiten

In **Meta for Developers** eine App mit Facebook Login bzw. Facebook Login for Business einrichten.

Benötigte Berechtigungen:

- `pages_show_list`
- `pages_read_engagement`
- `pages_manage_posts`

Die App muss die Facebook-Seiten sehen dürfen, die später im Assistenten verwendet werden sollen.

## 2. Gültige OAuth-Weiterleitungs-URI

In der Meta-App als gültige OAuth Redirect URI exakt eintragen:

`https://DEINE-RAILWAY-DOMAIN.up.railway.app/facebook/callback`

Die Adresse muss exakt mit `META_REDIRECT_URI` übereinstimmen, einschließlich `https://` und ohne zusätzlichen Schrägstrich am Ende.

## 3. Railway-Variablen

Unter **Railway → Service → Variables** setzen:

- `META_APP_ID`
- `META_APP_SECRET`
- `META_REDIRECT_URI`
- `META_CONFIG_ID` (nur bei Facebook Login for Business; sonst leer lassen)

Bereits vorhanden bleiben:

- `APP_STORAGE_DIR=/app/storage`
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`
- `SESSION_SECRET`

## 4. Verbindung herstellen

1. Neue Version deployen.
2. Im Seitenassistenten **Einstellungen** öffnen.
3. **Mit Facebook verbinden** anklicken.
4. Bei Facebook anmelden und die gewünschten Seiten freigeben.
5. Nach der Rückkehr die Seiten aktivieren oder deaktivieren.
6. **Seitenauswahl speichern** anklicken.

Nur aktivierte Seiten erscheinen in der Veröffentlichungsplanung.

## 5. Verbindung erneuern oder trennen

Unter **Einstellungen** kann die Verbindung jederzeit erneuert oder vollständig getrennt werden. Beim Trennen werden User-Token, Verbindungsdaten und gespeicherte Facebook-Seiten aus dem Railway-Volume entfernt.

## Hinweis zum App-Modus

Solange die Meta-App im Entwicklungsmodus ist, können normalerweise nur App-Rollen bzw. berechtigte Testkonten die Verbindung verwenden. Für andere Facebook-Nutzer sind je nach Einsatz App Review und Advanced Access für die benötigten Berechtigungen erforderlich.
