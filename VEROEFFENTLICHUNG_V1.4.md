# Veröffentlichung v1.4

## Neu

- Bei jeder Planung gibt es den Button **Jetzt veröffentlichen**.
- Ein Hintergrunddienst prüft alle 30 Sekunden, ob eine Planung fällig ist.
- Unterstützt werden Textbeiträge, ein Bild und mehrere Bilder.
- Fehler werden direkt bei der Planung angezeigt.

## Railway

Es sind keine neuen Variablen nötig. Die vorhandenen META-Variablen und `APP_STORAGE_DIR=/app/storage` bleiben bestehen.

Nach dem Deployment wird eine bereits überfällige Planung beim nächsten Scheduler-Lauf verarbeitet. Das dauert normalerweise höchstens 30 Sekunden.

## Noch nicht enthalten

Direkte Videoveröffentlichung ist noch nicht aktiviert. Ein solcher Versuch wird als fehlgeschlagen markiert und mit einer verständlichen Fehlermeldung angezeigt.
