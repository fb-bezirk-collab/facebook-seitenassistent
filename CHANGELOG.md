# Version 2.0.6 – Instagram-Reels

- Einzelne Videodateien werden über Cloudinary als Instagram-Reel veröffentlicht.
- Facebook-Reel-Links werden mit dem bestehenden Video-Resolver in eine lokale Videodatei aufgelöst.
- Cloudinary bereitet Videos als MP4/H.264/AAC vor.
- Instagram-Containerstatus wird bei Videos bis `FINISHED` abgefragt.
- Größere Videos werden stückweise zu Cloudinary hochgeladen.

# Version 1.5.0 – Mehrfachveröffentlichung

- Mehrere Facebook-Seiten gleichzeitig per Checkbox auswählen.
- Pro Seite wird eine eigene Veröffentlichung mit eigenem Status erzeugt.
- Ein Beitrag kann sofort auf allen noch offenen Seiten veröffentlicht werden.
- Einzelne fehlgeschlagene Seiten blockieren die übrigen Veröffentlichungen nicht.
- Doppelte Planungen für dieselbe Seite und denselben Zeitpunkt werden vermieden.
- Bestehende Einzelplanung, Scheduler, Bildbeiträge und Reel-Linkbeiträge bleiben erhalten.

# Version 1.4.2

- Button „Jetzt veröffentlichen“ in der Planungsübersicht
- Facebook-Reels und Videos werden als Linkbeiträge veröffentlicht
- kein Video-Download und kein Video-Upload
- fehlgeschlagene Planungen können erneut veröffentlicht werden

# Changelog

## 1.2.0

- Veröffentlichungsplanung pro Entwurf
- Mehrere Veröffentlichungen je Beitrag
- Unterschiedliche Plattformen, Konten und Zeitpunkte
- Statusverwaltung: geplant, bereit, veröffentlicht, fehlgeschlagen, storniert
- Zentrale Planungsübersicht
- Verwaltung manueller Facebook-, Instagram-, X- und TikTok-Konten
- Automatische Übernahme verbundener Facebook-Seiten
- Löschen eines Entwurfs entfernt auch zugehörige Planungen
- Neue persistente Dateien `data/publications.json` und `data/social_accounts.json`

## 1.4.0
- Direkte Facebook-Veröffentlichung über „Jetzt veröffentlichen“
- Automatischer Scheduler prüft alle 30 Sekunden fällige Planungen
- Veröffentlichung von Text, Einzelbild und mehreren Bildern
- Fehleranzeige und Speicherung der Facebook-Beitrags-ID
- Lokale Planungszeiten werden als Europe/Vienna interpretiert

## 1.4.1
- Button „Jetzt veröffentlichen“ direkt in der Veröffentlichungsplanung ergänzt.
- Sofortveröffentlichung leitet wieder zur aufrufenden Ansicht zurück.
- Facebook-Videobeiträge werden über den Page-Videos-Endpunkt veröffentlicht.
- Direkte Videodatei-URLs werden per `file_url` übergeben.
- Bei Facebook-/Reel-Seitenlinks wird die tatsächliche Videodatei ermittelt, lokal gespeichert und hochgeladen.
