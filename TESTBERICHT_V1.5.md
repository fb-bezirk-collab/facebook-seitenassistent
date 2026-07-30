# Testbericht Version 1.5.0

Durchgeführt am 30.07.2026:

- Python-Module vollständig kompiliert.
- FastAPI-Anwendung erfolgreich importiert; Version 1.5.0.
- Jinja-Vorlage `draft_edit.html` geparst und mit Beispieldaten gerendert.
- Zwei ausgewählte Facebook-Seiten erzeugen zwei getrennte Veröffentlichungen.
- Erneutes Absenden derselben Seiten zum selben Zeitpunkt erzeugt keine Duplikate.
- Testveröffentlichung auf zwei Seiten: eine erfolgreich, eine fehlgeschlagen.
- Der Fehler einer Seite blockiert die erfolgreiche Veröffentlichung auf der anderen Seite nicht.
- Status und externe Beitrags-ID werden je Seite getrennt gespeichert.
