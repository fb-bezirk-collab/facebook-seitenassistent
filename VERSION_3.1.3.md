# Version 3.1.3 – NÖN-Abo-Test mit gespeicherter Sitzung

## Änderung

Der Abo-Zugriffstest startet nicht mehr bei jedem Klick einen neuen NÖN-Login.

- Eine vorhandene, frische automatische Sitzung wird zuerst wiederverwendet.
- Ein neuer Login wird nur aufgebaut, wenn keine verwendbare Sitzung vorhanden ist.
- Falls ein Artikelabruf auf eine Login-/Anmeldeseite umleitet, wird die Sitzung einmal automatisch erneuert und der Test wiederholt.
- Die Oberfläche zeigt an, ob die gespeicherte Sitzung verwendet oder eine neue Sitzung aufgebaut wurde.

Damit wird verhindert, dass ein bereits eingeloggter NÖN-Browser fälschlich als Fehler behandelt wird, nur weil dort kein Passwortfeld mehr vorhanden ist.
