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
