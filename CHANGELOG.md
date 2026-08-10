## 2.1.0 – Multi-Source-Medienmonitor
- Kurier, Heute und oe24 zusätzlich zu Krone eingebunden.
- Quellen werden unabhängig voneinander abgerufen; ein Einzel-Fehler stoppt den Gesamtabruf nicht.
- Quellenstatistik im Medienmonitor ergänzt.
- Gemeinsamer HTML-/JSON-LD-Parser für Medien ohne geeigneten RSS-Feed ergänzt.

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

## 2.1.1 – Veröffentlichungszeit Heute/oe24
- Veröffentlichungszeit bei Heute und oe24 wird bei fehlenden Startseiten-Daten direkt aus der Artikelseite gelesen.
- Unterstützt JSON-LD, article:published_time, weitere Meta-Tags, <time datetime> und sichtbare Datums-/Zeitangaben.
- Bereits gespeicherte Heute-/oe24-Meldungen ohne Zeit werden beim erneuten Abruf nachträglich ergänzt, sofern sie noch im aktuellen Abruf enthalten sind.

## 2.2.0 – Erweiterte Medienquellen
- ORF ergänzt (öffentlicher RSS-Newsfeed).
- Der Standard ergänzt (öffentlicher RSS-Newsroom-Feed).
- Die Presse ergänzt.
- exxpress ergänzt.
- Salzburger Nachrichten ergänzt.
- Kleine Zeitung ergänzt (Politik, Österreich und Wirtschaft per RSS).
- NÖN ergänzt.
- APA ergänzt, beschränkt auf öffentlich sichtbare Top-News auf apa.at.
- Gemeinsamer RSS-Parser und gemeinsamer Homepage-/Metadaten-Fetcher ergänzt.
- Unabhängige Fehlerbehandlung pro Quelle beibehalten.

## 2.2.1
- Medienabruf auf Hintergrundjob umgestellt, um Railway-Upstream-Timeouts bei vielen Quellen zu vermeiden.
- Statusanzeige und automatisches Neuladen während eines laufenden Abrufs ergänzt.

## 2.3.0
- APA-Zeitstempel mit zweistelligem Jahr und Sekunden werden erkannt und bei bekannten Artikeln nachgetragen.
- Medienübergreifende KI-Erkennung für identische konkrete Nachrichtenereignisse ergänzt.
- Kennzeichnung: 2 Quellen = Mehrere Medien, 3+ binnen 12h = TRENDING, 4+ binnen 6h = BREAKING.
- Trend-Quellen und kurze Themenbezeichnung werden direkt im Medienmonitor angezeigt.
