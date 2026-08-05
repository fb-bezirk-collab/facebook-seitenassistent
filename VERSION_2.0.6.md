# Version 2.0.6 – Instagram-Reels

## Neu

- Lokale Videodateien können auf Instagram als Reel veröffentlicht werden.
- Gespeicherte Facebook-Reel-/Videolinks werden vor der Veröffentlichung aufgelöst und als tatsächliche Videodatei gespeichert.
- Videos werden zu Cloudinary hochgeladen und für Instagram als MP4 mit H.264/AAC vorbereitet.
- Das Reel wird zusätzlich im normalen Instagram-Feed angezeigt (`share_to_feed=true`).
- Die bestehende Container-Statusprüfung wartet bei Videos bis zu zehn Minuten auf `FINISHED`.
- Für größere Videodateien verwendet Cloudinary einen stückweisen Upload.

## Unverändert

- Instagram-Bildbeiträge
- Facebook-Veröffentlichungen
- Planung und automatische Zeitverteilung
- Bearbeitbare KI-Textvarianten

## Erste Ausbaustufe

Pro Entwurf wird auf Instagram zunächst ein einzelnes Video als Reel veröffentlicht. Mehrere Videos oder gemischte Instagram-Karussells sind noch nicht enthalten.
