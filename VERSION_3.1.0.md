# Version 3.1.0 – NÖN-Abo-Pilot

## Neu

- Medien-Abos in den Einstellungen, zunächst für NÖN.
- Es wird kein NÖN-Passwort gespeichert. Hinterlegt wird ausschließlich die aktive Browser-Sitzung als Cookie-Header.
- Die Sitzungsdaten werden verschlüsselt im persistenten Datenordner (`data/media_subscriptions.enc`) gespeichert.
- NÖN-Abo-Sitzung kann gespeichert, getestet und getrennt werden.
- Test vergleicht öffentlichen und angemeldeten Abruf eines konkreten NÖN-Artikels.
- KI-Analyse verwendet bei `noen.at` automatisch die hinterlegte Sitzung.
- Analyse-Seite kennzeichnet, wenn die NÖN-Abo-Sitzung beim Artikelabruf verwendet wurde.
- Alle übrigen Medienquellen bleiben unverändert.

## Sicherheit

- Keine NÖN-Zugangsdaten im Repository.
- Kein Benutzername oder Passwort im Datenordner.
- Sitzungs-Cookies werden mit Fernet verschlüsselt gespeichert.
- Optional kann `MEDIA_SESSION_SECRET` als eigener Railway-Schlüssel gesetzt werden; sonst wird ein separater Schlüssel aus `SESSION_SECRET` abgeleitet.
