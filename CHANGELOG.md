# 2.8.1

- Autor-Fallback über direkte Comment-Abfrage ergänzt.
- Diagnose für fehlende `from`-Daten ergänzt.
- Autor-Diagnose in der Kommentaransicht sichtbar.
- Bestehende Kommentardaten bleiben kompatibel.

## 2.7.2
- Meta-Login: tatsächliche Token-Berechtigungen werden nach OAuth geprüft.
- Fehlendes `pages_read_user_content` wird bereits beim Verbinden klar gemeldet.
- Keine Änderung am funktionierenden Facebook-Login-for-Business-Flow mit `config_id`.

# Changelog

## 2.6.0
- KI-Redaktionsanalyse kann mit ausgewählter Headline und Facebook-Variante direkt in den bestehenden Entwurfsworkflow übernommen werden.
- Hashtags und alle KI-Textvarianten werden mitgenommen.
- Medienmeldung ↔ Entwurf wird dauerhaft verknüpft.
- Entwurfseditor zeigt Herkunft und interne KI-Metadaten.
- Medienmonitor kennzeichnet bereits erzeugte Entwürfe.

# 2.5.3
- Facebook-Kommunikationsprofil deutlich geschärft.
- Politisch relevante, im Artikel belegte Angaben zu Staatsangehörigkeit/Herkunft, Asyl-/Migrationsbezug, Aufenthaltsstatus oder religiösem Zwang werden bei relevanten Fällen nicht mehr wegneutralisiert.
- Facebook-Varianten als politische Arbeitsentwürfe statt neutraler Presseschau definiert.
- `Kampagnenstil` ersetzt die bisherige mobilfreundliche Variante.
- Pointierte, emotionale und Kampagnen-Varianten erhalten eine klarere politische Kernbotschaft.
- Fakten-, Verfahrens- und Quellenregeln bleiben bestehen; keine erfundenen Angaben oder Kollektivzuschreibungen.
- Alte Analysen mit Feld `mobil` bleiben in der Oberfläche lesbar.

# 2.5.2
- KI-Analyse befüllt jetzt die vollständige Redaktionsmaske.
- Politische Brisanz und Kommunikationspotenzial 0–10.
- Priorität inklusive Begründung.
- FPÖ-NÖ-orientierter politischer Kommunikationsansatz auf Basis belegter Fakten.
- Vier Headline-Varianten.
- Vier Facebook-Arbeitsentwürfe.
- Zielgruppen, Grafikidee, Faktencheck und Hashtags.
- Alte Analysen bleiben kompatibel.

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

## 2.3.1 – Aktive Medienmonitor-Filter
- Live-Volltextsuche für Titel, KI-Kurzfassung, Begründung, Kategorie, Region und Quelle aktiviert.
- Quellenfilter dynamisch aus den angezeigten Meldungen erzeugt, inklusive Trefferzahlen.
- Themenfilter dynamisch aus den vorhandenen KI-Kategorien erzeugt, inklusive Trefferzahlen.
- Statusfilter aktiviert: Offen, Gemerkt, Freigegeben, Verworfen, Trending, Breaking und Alle.
- Filter sind miteinander kombinierbar und arbeiten vollständig im Browser ohne neuen Server-/KI-Aufruf.
- Live-Zähler für Treffer, Quellen, Trending und Breaking ergänzt.

## 2.3.2 – Mehrbild-Import, Zufallsverteilung, Quellen-Retry
- Facebook-Mehrbildbeiträge: zusätzliche Foto-Unterseiten werden eingelesen.
- Doppelte CDN-Varianten desselben Bildes werden vermieden.
- "Varianten automatisch verteilen" mischt Seiten und Varianten bei jedem Klick zufällig, bei weiterhin möglichst ausgewogener Verteilung.
- Generische Medienquellen wiederholen Timeout-/Verbindungsfehler einmal automatisch; Timeout auf 30 Sekunden erhöht.

## 2.4.0 – KI-Detailanalyse im Medienmonitor

- Neue Detailanalyse pro Medienmeldung über den Button „KI analysieren“.
- Der öffentlich lesbare Artikeltext wird nach Möglichkeit direkt von der Originalseite eingelesen; bei Paywall oder technischer Sperre wird auf Anreißer/Metadaten zurückgefallen.
- Die Analyse läuft im Hintergrund, damit lange Artikel- oder OpenAI-Antwortzeiten keinen Railway-Upstream-Timeout auslösen.
- Neue Analysebereiche: Kurzüberblick, Kernaussagen/Fakten, politische Einordnung, Bedeutung für die Bevölkerung, Social-Media-Potenzial, offene Prüfpunkte, Gegenpositionen/Einwände, sachliche Aufhänger und Arbeitsüberschriften.
- Bei bereits erkannten Trending-/Breaking-Clustern werden die weiteren Medien desselben konkreten Ereignisses in die Analyse einbezogen und auf der Detailseite verlinkt.
- Analyse kann jederzeit aktualisiert werden; der vorherige Medienabruf und die Filterlogik bleiben unverändert.

## 2.4.1
- Manuelle Beitragserstellung: Mehrbild-Auswahl deutlich verbessert.
- Dateien können in mehreren Auswahlvorgängen gesammelt werden.
- Vorschau und Entfernen einzelner Medien vor dem Speichern ergänzt.

## 2.5.0 – Prompt- und Wissensbasis
- Versionierbare Prompt-Struktur unter `prompts/` eingeführt.
- Kommunikationsprofile unter `profiles/` eingeführt, zunächst FPÖ Niederösterreich und Kommunalpolitik.
- Redaktionelle Wissensdateien unter `knowledge/` eingeführt.
- JSON-Schemas unter `schemas/` ausgelagert.
- Die bestehende KI-Analyse lädt ihren Systemprompt und ihr Schema nun aus diesen Dateien statt aus hart im Python-Code hinterlegten Texten.
- Bestehende Analyse-Oberfläche und JSON-Felder bleiben kompatibel.

## 2.7.0 – Facebook-Kommentar-Monitor Phase 1
- Zentraler Kommentar-Posteingang für alle verbundenen Facebook-Seiten ergänzt.
- Kommentarabruf als Hintergrundjob umgesetzt.
- Dublettenerkennung über Facebook-Comment-ID.
- Suche sowie Seiten- und Statusfilter ergänzt.
- Ausblenden, Wieder einblenden, Löschen und lokales Erledigt-Markieren direkt aus der App möglich.
- Seitenweise Abrufstatistik und unabhängige Fehlerbehandlung ergänzt.

## 2.7.3
- KI-Kategorisierung, Priorität und Moderationsempfehlung für Facebook-Kommentare ergänzt.
- Hintergrundjob zur Bewertung unanalysierter Kommentare ergänzt.
- Filter nach KI-Kategorie und neue Kennzahlen ergänzt.
- KI-Antwortvorschläge mit Copy-Funktion ergänzt; keine automatische Veröffentlichung.
- Autor-Fallback verständlicher dargestellt, wenn Meta keine `from`-Daten liefert.
## 2.7.4
- Kommentar-Moderation deutlich zurückhaltender ausgerichtet.
- Normale politische Kritik/Forderungen werden nicht mehr als Beleidigung oder hohe Priorität behandelt.
- Kategorien `Meinung/Kritik` und `Drohung/Gewalt` ergänzt.
- Hohe Priorität auf echte Beschimpfungen, Drohungen/Gewalt und gefährlichen Scam beschränkt.
- Bestehende 2.7.3-KI-Bewertungen werden automatisch zur Neubewertung markiert.

## 2.7.5
- Moderationsprofil in `profiles/comment_moderation.md` ausgelagert.
- KI-Moderation deutlich zurückhaltender; politische Kritik wird nicht als Beleidigung behandelt.
- Bewertungs-Version auf 2.7.5 erhöht.

## 2.8.0
- Moderations-Schnellfilter und Dropdown „Moderation empfohlen“/„Antwort empfohlen“.
- KI-Kategorie Off-Topic ergänzt.
- Seitenübergreifende Benutzerübersicht mit Historie, Wiederholungsmustern und Risiko-Score.
- Interne Beobachtungsliste für Kommentatoren.
- Facebook-Sperren/Entsperren auf allen eindeutig bekannten Seiten-PSIDs.
- Sicherheitslogik für Page-Scoped User IDs und mehrdeutige Namenszuordnungen.


## 2.8.2
- Alle offenen Kommentare automatisch in 200er-Blöcken bewerten
- KI-Fehler je Kommentar speichern und wiederholen
- Kommentar-Medien/Attachments erfassen und anzeigen

## 2.8.3
- Erweiterter Abruf von Facebook-Comment-Attachments inklusive Story-Attachment-Mediendaten.
- Link-Kommentare erhalten bei fehlender Meta-Vorschau eine OpenGraph-Bildvorschau der öffentlichen Zielseite.
- Bestehende Kommentare werden beim nächsten Abruf nachträglich um Medienvorschauen ergänzt.
- Leere Sticker-/Medienkommentare werden ohne automatische Inhaltsbewertung als unkritische Medienkommentare gekennzeichnet.
- Medien-Diagnose im Kommentar-Monitor ergänzt.

## 2.8.4
- Hintergrundjob zum Nachaktualisieren bereits gespeicherter Facebook-Kommentare.
- Fehlende Medien-/Linkvorschauen werden direkt über bekannte Comment-IDs nachgeladen.
- Fortschrittsanzeige und persistenter Refresh-Status ergänzt.

## 2.8.5
- Facebook-Foto-/Video-Permalinks haben Vorrang vor externen URLs aus Kommentartexten.
- Keine OpenGraph-Fallbacks mehr bei erkannten Facebook-Medienkommentaren.
- Falsch gespeicherte externe Vorschaubilder werden beim Aktualisieren bestehender Kommentare entfernt.
- Anzeige „Facebook-Medium öffnen“ für Facebook-Medienreferenzen.


## 3.0.0 – Medienmonitor → Facebook-Linkbeitrag
- Neuer Facebook-Linkshare-Workflow aus der KI-Analyse.
- Ein-Klick-Linkentwurf aus dem Medienmonitor.
- FacebookPublisher übergibt Originalartikel als `link` an `/feed`.
- Linkentwürfe sind auf Facebook beschränkt und separat mit der Medienmeldung verknüpft.

## 3.0.1
- Editierbares FPÖ-Social-Media-Profil ergänzt.
- Neue themenspezifische Social-Media-Frames und Sprachregeln.
- Profil kann in Einstellungen ohne Deploy geändert werden.
- Persistente benutzerdefinierte Fassung im data-Ordner.
- Analyseprompt wird pro KI-Analyse dynamisch neu geladen.

## 3.0.2
- Medienmonitor um Unzensuriert, NIUS Österreich, FoB News, ZurZeit und NFZ erweitert.
- NIUS wird ausschließlich über `/tag/oesterreich` eingelesen.
- Neue Quellen laufen unabhängig; einzelne Abruffehler blockieren den Gesamtlauf nicht.

## 3.0.3
- Zentraler UTF-8-/Mojibake-Fix für HTML-Medien.
- Bestehende Artikel können über Quelle + URL textlich korrigiert werden, ohne Dubletten.
- Eigener NIUS-Österreich-Fetcher für die clientseitig gerenderte Tag-Seite.
## 3.1.0
- NÖN-Abo-Pilot mit verschlüsselter Sitzungsablage, Testfunktion und Abo-Abruf für KI-Analysen.

## 3.1.1
- NÖN-Abo: automatischer Login über Railway-Variablen `NOEN_USERNAME`/`NOEN_PASSWORD`.
- Zugangsdaten werden nicht im Projekt gespeichert; nur die erzeugte Sitzung wird verschlüsselt persistiert.
- Automatische Sitzungserneuerung und Login-Test in den Einstellungen.
