# Version 3.3.0 – Sammelupdate

## Änderungen

- KI-Bilder verwenden standardmäßig `gpt-image-2`.
- Kommentarbewertung neu abgestuft: sachliche Gegenmeinung bleibt niedrig; feindselige/verhöhnende/persönlich herabsetzende Kommentare werden als Provokation mit mittlerer Priorität behandelt; starke Beschimpfungen bleiben hoch.
- Kommentarabruf mit Fortschrittsanzeige pro Seite, Abbruch, Stale-Job-Heilung nach Railway-Restart und Zeitlimits pro Meta-Aufruf/Seite.
- Kommentare werden nach jeder Seite zwischengespeichert.
- Medienmonitor: robustere Mojibake-/UTF-8-Reparatur und persistente Bereinigung bereits gespeicherter Texte.
