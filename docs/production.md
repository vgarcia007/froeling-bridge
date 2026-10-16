# Dauerbetrieb mit bestehender p4d-Datenbank

Ab 0.4.0 ist `hardware-live` der ausdrücklich freigegebene Aufzeichnungsbetrieb: echte Heizung lesen, `samples` und `peaks` in der vorhandenen Datenbank fortführen. Heizungsparameter bleiben schreibgeschützt. Keine Initialisierung, Migration, Löschung oder Veränderung von Menü, Sensorenauswahl und Konfiguration. Der Benutzer hat diesen Wechsel nach dem erfolgreichen Lesetest ausdrücklich beauftragt.

## Einrichtung auf dem vorbereiteten Host

Das geprüfte private Paket wird unter `~/froeling-bridge-live-0.4.0` bereitgestellt. Es enthält Wheel und sämtliche benötigten Abhängigkeiten für den Zielhost. Vorhandene Zugangsdaten werden aus `/etc/froeling-bridge-test/source-db.json` verwendet; keine Übernahme einer Testdatenbank und keine erneute Eingabe.

```sh
sudo bash ~/go-live.sh
```

Das Skript prüft alle Prüfsummen, installiert ein getrenntes Release unter `/opt/froeling-bridge/0.4.0` und kontrolliert das vorhandene Datenbankschema ausschließlich lesend. Ein bereits bestehendes fremdes Release wird erhalten. Das getestete 0.3.0-Release bleibt erhalten. Wiederholung nach Installationsabbruch ist möglich, solange der Release-Marker identisch ist.

Der feste root-Helfer `/usr/local/sbin/froeling-bridge-live` unterstützt ausschließlich `start`, `rollback` und `status`. Für den sudo-Aufrufer werden diese festen Aktionen passwortlos eingerichtet; allgemeine administrative Rechte werden dadurch nicht gewährt.

## Umschaltung

1. Original-p4d, Adapter, Tabellen/Schlüssel/InnoDB und Sensorenauswahl prüfen. Aktives Testfenster zuerst abschließen.
2. Unabhängigen Fünf-Minuten-Rückkehrtimer scharfstellen. Dieser schützt nur die Aktivierung.
3. Simulator-Vorschau beenden, Port 8000 prüfen, alten Testtimer ausschalten.
4. p4d stoppen und mit fuser die Freigabe von `/dev/ttyUSB0` feststellen.
5. p4d-Autostart deaktivieren, `froeling-bridge.service` aktivieren und starten. Original-Dateien bleiben erhalten.
6. Zwei erfolgreiche Sammeldurchläufe sowie einen neuen Original-DB-Messpunkt über einen vorhandenen Sensorschlüssel bestätigen. Erst danach Aktivierungstimer abschalten.

Im normalen Betrieb besteht **keine Laufzeitbegrenzung**. Messintervall 60 Sekunden, Webmenü/API direkt über `http://SERVER-IP:8000`. Der frühere Simulator-Port zeigt damit echte Daten. Port 8001 gehört weiterhin ausschließlich zum alten begrenzten Testdienst.

Der Dienst startet beim Booten. `Conflicts` und exklusive TTY-Sperren verhindern einen parallelen seriellen Besitzer. Bei Protokoll-/Datenbankfehler oder überschrittener Sammlerdeadline beendet sich die Bridge; `OnFailure` stellt p4d samt Autostart wieder her. Kein blindes Wiederholen unklarer Datenbank-Commits oder Heizungsaufträge.

## Kontrolle und Rückkehr

```sh
sudo /usr/local/sbin/froeling-bridge-live status
sudo /usr/local/sbin/froeling-bridge-live rollback
journalctl -u froeling-bridge.service -n 60
```

Rückkehr beendet zuerst die Bridge und prüft den seriellen Port, bevor p4d gestartet wird. Die Bridge wird aus dem Autostart genommen, p4d wieder aktiviert. Neue Originalmesspunkte werden bis zu 90 Sekunden geprüft; fehlende Bestätigung wird ausdrücklich als Fehler gemeldet. Bei Host-/Adapterausfall ist ein erfolgreicher Rückfall nicht garantiert.

## Daten und Grenzen

- Metadaten/Historie lesen weiterhin über Read-only-Transaktionen. Nur `store_cycle` schreibt, atomar in `samples` und `peaks`, mit vorhandener Sensoridentität, lokaler Berlin-Zeit und p4d-Metastempeln.
- Zeitprogramme behalten echte Menünamen/Wochentage und gemeinsamen persistenten Cache unter `/var/lib/froeling-bridge/time-programs-cache.json`. Ein vorhandener Testcache wird einmalig übernommen. Keine dauerhaft wachsenden seriellen Rohmitschnitte im Dauerbetrieb.
- Die Oberfläche erklärt den aktiven Dauerbetrieb und das tatsächliche Datenbankziel. Heizungs-Schreibjobs bleiben auf API-, Client- und Transportebene gesperrt.
- Neue Rohmesspunkte werden aufbewahrt. Automatische Aggregation/Bereinigung und zusätzliche p4d-Integrationen sind bisher nicht nachgebaut; vorhandene historische Aggregate bleiben erhalten. Aufbewahrung wird gesondert umgesetzt, ohne den Bestand vorzeitig zu löschen.
- LAN-Betrieb ohne neue Anmeldung entspricht dem ausdrücklich gewünschten Zugriff. Kein Internetzugriff/Portforwarding wird eingerichtet.

Prüfung: `tests/test_production.py`, gesamte Testsuite mit separater MariaDB und `docs/tools/verify_production_rollback.py --run-local-spares` (sudo). Letzteres verwendet ausschließlich eindeutig benannte Ersatzdienste und prüft echte systemd-Ausfall-/Timer-Rückkehr samt Autostartauswahl, ohne Heizung oder Originaldatenbank zu berühren.
