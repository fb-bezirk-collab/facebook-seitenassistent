# Version 3.1.1 – NÖN-Abo mit Railway-Zugangsdaten

## Neu

- Primärer NÖN-Abo-Zugriff über `NOEN_USERNAME` und `NOEN_PASSWORD` aus Railway Variables.
- Das Passwort wird von der App weder in GitHub noch im Datenordner gespeichert.
- Playwright öffnet NÖN, sucht die Login-Maske, meldet sich an und speichert nur die erzeugte Sitzung verschlüsselt.
- Die automatische Sitzung wird bis zu sechs Stunden wiederverwendet und danach erneuert.
- Eigener Button **„NÖN jetzt anmelden / Sitzung erneuern“** in den Einstellungen.
- Der Abo-Test führt bewusst einen frischen Login durch und vergleicht anschließend öffentlichen und eingeloggten Artikelabruf.
- Der Cookie-Pilot aus 3.1.0 bleibt intern als Fallback kompatibel, wird aber in der Oberfläche nicht mehr angeboten.
- Wenn NÖN Captcha, Zwei-Faktor-Anmeldung oder einen nicht automatisch erfassbaren Login verlangt, erscheint eine konkrete Fehlermeldung; der Medienmonitor fällt weiterhin auf öffentliche Inhalte zurück.

## Railway Variables

```text
NOEN_USERNAME=
NOEN_PASSWORD=
NOEN_LOGIN_URL=   # optional
```
