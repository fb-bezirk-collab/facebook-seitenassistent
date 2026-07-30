# Version 1.4.2 – Sofort veröffentlichen und Video als Link

Diese Version veröffentlicht Video- und Reel-Beiträge bewusst **nicht als Video-Upload**.

Bei einem importierten Videobeitrag werden verwendet:

- der importierte Beitragstext
- der gespeicherte Original-Link, zum Beispiel `https://www.facebook.com/reel/...`

Die App erstellt daraus über den Facebook-Feed-Endpunkt einen normalen Linkbeitrag. Das Video wird weder heruntergeladen noch im Railway-Storage gespeichert und auch nicht erneut zu Facebook hochgeladen.

## Sofort veröffentlichen

In der Veröffentlichungsplanung befindet sich bei allen noch nicht veröffentlichten Beiträgen der Button **„Jetzt veröffentlichen“**. Auch ein zuvor fehlgeschlagener Beitrag kann damit erneut veröffentlicht werden.

## Bereits fehlgeschlagene Videoplanung

Nach dem Deployment kann die vorhandene Planung mit dem Status `failed` geöffnet oder direkt über **„Jetzt veröffentlichen“** erneut gestartet werden.
