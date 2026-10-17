# Eigenständiger Betrieb ab 0.5.0 (Korrekturstand 0.5.3)

Die Bridge kann ohne p4d und ohne MariaDB starten. Sie liest Sensorbeschreibungen, Menü und Zeitprogramme direkt aus der Steuerung. SQLite speichert den Arbeitskatalog und Einstellungen lokal; MariaDB ist ausschließlich die optionale p4d-kompatible Historie. Protokoll und Darstellung orientieren sich an linux-p4d von Jörg Wendel und Mitwirkenden.

## Neue Installation

Debian/Ubuntu mit systemd, Python >=3.9 und einem seriellen Heizungsadapter:

```sh
git clone --recurse-submodules git@github.com:vgarcia007/froeling-bridge.git
cd froeling-bridge
sudo bash deploy/install-standalone.sh
```

Das Skript richtet Python-Umgebung, Dienstbenutzer, Adapterrechte und Autostart ein. Fehlende Debian/Ubuntu-venv-Unterstützung und fuser werden installiert. Bei eindeutigem Adapter wird dessen dauerhafter `/dev/serial/by-id/…`-Pfad gewählt. Bei mehreren Adaptern muss der richtige ausgewählt werden. Danach kann optional eine MariaDB-Verbindung eingegeben werden; Passwort verdeckt, keine manuellen SQL-Befehle. Eine bestehende Verbindung der bisherigen Bridge-Einrichtung wird automatisch übernommen.

Für unbeaufsichtigte Einrichtung eine **private** JSON-Datei vorbereiten und übergeben:

```sh
sudo bash deploy/install-standalone.sh --config /geschuetzt/bridge-settings.json
```

Felder: `device` (absoluter Gerätepfad), optional `host` (Standard `0.0.0.0`), `port` (8000), `interval` (60 Sekunden), `history` mit `host`, `port`, `database`, `user`, `password`. Keine Zugangsdaten in Shellargumente schreiben. Der native Dienst verwendet `/var/lib/froeling-bridge`; CLI-Demos erlauben eigene Zustandsordner.

Das auf dem konkreten Zielhost beobachtete Zeitprogramm-Antwortprofil `43 -> 42` wird bei Einrichtung vorbelegt. `reply_profile` kann es ausdrücklich ersetzen. First/Next-Discovery akzeptiert auf Next sowohl den First- als auch den Next-Antwortcode derselben Liste; fremde Antworten und ungültige Prüfsummen bleiben Fehler. Dies bildet die ursprünglichen p4d-Listenabläufe ab, ohne beliebige Antwortbefehle freizugeben.

0.5.1 korrigiert die quellenbasierten Listenabläufe: vor Sensor- und Menülisten jeweils `CHECK` mit `Tescht ;-)`; kurze nicht abschließende Einträge überspringen wie p4d (`wrnEmpty`/`wrnSkip`). Die Höchstzahl zählt auch übersprungene Einträge. Eine einzelne Anfrage/Antwort erhält maximal zwei Sekunden innerhalb der längeren Gesamtfrist; diese Frist wird bei fragmentierten Antworten nicht neu gestartet. Das Original verwendet zwei Sekunden für den Header und eigene Byte-Lesefristen. Die Bridge begrenzt zusätzlich die gesamte einzelne Anfrage/Antwort.

`/api/v1/runtime.last_failure` und das Dienstjournal nennen Phase, Fehlerklasse und bei Listenfehlern Anfragebefehl sowie Eintragsnummer. Beliebige Betriebssystem-/Datenbankfehlermeldungen und rohe Betriebswerte werden nicht ausgegeben. Der letzte Fehler bleibt nach einer Erholung als Diagnose erhalten.

Ein alter p4d-Host kehrt beim ersten vom Worker gemeldeten Startfehler sofort zu p4d zurück. `status` bleibt auch während Aktivierung erreichbar; `rollback` signalisiert einen Abbruch, bevor es begrenzt auf die Dienstsperre wartet. Der unabhängige Starttimer bleibt zusätzliche Absicherung. Ein 24-Stunden-Test beobachtet erst funktionierenden Lesebetrieb; er ist keine Wartezeit ohne Monitoring.

0.5.2 behandelt wiederholte Sensordefinitionen wie Original-`initValueFacts`/`addValueFact`: pro Typ und Adresse ein Sensor, spätere Definition aktualisiert die Metadaten; individuelle Auswahl und Aufzeichnungsflags bleiben erhalten. Die echte Steuerung hat beim Erststart 161 wiederholte Definitionen geliefert. Die frühere pauschale Ablehnung war ein Fehler der Bridge.

Der unabhängige `froeling-bridge-health.timer` prüft alle 30 Sekunden ausschließlich die gespeicherten HTTP-Ansichten. Er öffnet weder Adapter noch Datenbank. Eine aktuelle Statusantwort allein genügt bei ausgewählten Messsensoren nicht: mindestens eine ausgewählte Messung muss aus der Steuerung stammen und innerhalb von drei Abfrageintervallen (mindestens 180 Sekunden) gelesen worden sein. Nach 60 Sekunden anhaltendem Fehler kehrt ein vorhandener p4d-Host über den normalen Helfer zum Original zurück; ein neuer Host startet die Bridge neu. Einzelne defekte Sensoren lösen bei sonst aktuellen Messwerten keine vollständige Umschaltung aus. MariaDB-Ausfall löst keine Rückkehr aus, solange das Live-Monitoring funktioniert. Die initiale abgesicherte Umschaltung hat ihren eigenen Starttimer; auf einem neuen Host erhält ein fehlerfreier Katalogneuaufbau ausreichend Zeit.

Bei einer vorhandenen laufenden p4d-Installation ist der Wechsel ausdrücklich zu wählen:

```sh
sudo bash deploy/install-standalone.sh --take-over-p4d
```

Aktive alte Testfenster werden abgewiesen. Das Skript prüft Port und Prozessinspektion, hält vor der Umschaltung einen unabhängigen Rückkehrtimer bereit und wartet auf abgeschlossene Discovery sowie mindestens einen erfolgreichen Sammeldurchlauf. Originaldateien und alte Releases bleiben erhalten. Ein fremdes Releaseverzeichnis wird nicht übernommen; identische abgebrochene Einrichtung kann fortgesetzt werden.

Webmenü/API: `http://SERVER-IP:8000`. Beim ersten Start kann der Aufbau großer Menükataloge mehrere Minuten benötigen; `/api/v1/runtime` zeigt die aktuelle Phase. Eine unvollständige Discovery ersetzt keinen vollständigen Katalog.

## Laufender Betrieb und Fehler

- Statusprüfung alle 10 Sekunden, Messwertdurchlauf standardmäßig alle 60 Sekunden. Zustandswechsel löst einen zusätzlichen Durchlauf aus. Abfragen und Benutzerjobs teilen einen seriellen Besitzer.
- Alle Sensoren werden katalogisiert, nicht automatisch alle abgefragt. Ohne vorhandene Einstellungen sind erreichbare unterstützte Messwert-/I/O-Menüeinträge und UD 1–3 ausgewählt; Historie zunächst aus. Vorhandene Auswahl und individuelle Titel werden aus p4d übernommen. Ein noch nicht unterstützter Sensortyp bleibt sichtbar.
- SQLite: `catalogue.sqlite3` speichert Katalog, Einstellungen, letzte Werte, ausstehende DB-Einstellungen und Schreibjournal. `time-programs-cache.json` hält vollständige Zeitprogramme. Nach Neustart werden alte Werte als gespeichert/veraltet angezeigt, bis neue Heizungsantworten vorliegen.
- Bei beschädigter SQLite-Datei wird die Datei samt zugehörigen Nebenfiles unter `.damaged-*` erhalten und ein neuer Katalog aus der Heizung aufgebaut. Individuelle Einstellungen benötigen ein Backup; sie lassen sich nicht aus der Heizung rekonstruieren. Unbekannte zukünftige SQLite-Schemaversionen werden ausdrücklich abgewiesen.
- Verbindungsfehler schließen die defekte serielle Sitzung. Spätere Leseversuche öffnen eine neue exklusive Sitzung, mit begrenztem Wiederanlaufabstand bis 30 Sekunden. Der fehlgeschlagene Auftrag selbst wird nicht wiederholt. UI/API bleiben erreichbar und kennzeichnen die Verbindung getrennt von ihrer eigenen HTTP-Erreichbarkeit.
- Auf einem neuen Host startet systemd einen abgestürzten Prozess neu. Auf dem ursprünglichen p4d-Host gibt es stattdessen unmittelbare OnFailure-Rückkehr zu p4d; automatische Prozessneustarts werden dort deaktiviert, damit sie den Rückfall nicht verzögern. Ein normaler serieller Wiederverbindungsversuch läuft im Prozess und löst keine konkurrierende p4d-Instanz aus.

```sh
sudo /usr/local/sbin/froeling-bridge-control status
sudo /usr/local/sbin/froeling-bridge-control rollback
sudo /usr/local/sbin/froeling-bridge-control start
journalctl -u froeling-bridge.service -n 60
```

Auf einem neuen Host ohne p4d beendet `rollback` den Dienst und nimmt ihn aus dem Autostart. Auf dem ursprünglichen Host stellt es p4d mit dessen ursprünglicher Autostarteinstellung wieder her. Diese neue Rückkehr meldet den Dienstzustand; ein tatsächlicher neuer Originalmesspunkt muss für den Abnahmenachweis zusätzlich kontrolliert werden.

## Sensoren und API

`GET /api/v1/sensors` ist der Einstieg: Originalname `title`, individueller Name `usrtitle`, Einheit, Identität aus **type + address**, `active`, `recording`, `supported` und `latest`. Sensoren können ohne Menüeintrag existieren; Menüzeilen-IDs sind keine dauerhaft garantierten Sensoradressen.

`latest=null` bedeutet: kein Wert vorhanden. Ansonsten beschreiben `observed_at`, `age_seconds`, `origin` und `stale` die tatsächliche Beobachtung. `origin=local-persisted` ist ein gespeicherter Stand nach Neustart, kein neuer Heizungswert. GET löst keine Heizungsabfrage aus. Frische Werte über die bestehenden `measurement`-/`status`-Jobs anfordern, deren Ergebnis nicht automatisch eine Historienaufzeichnung auslöst.

```http
PATCH /api/v1/sensors/VA/43
Content-Type: application/json

{"active": true, "record": false}
```

Adresse 43 ist nur ein Beispiel; aus dem eigenen Katalog übernehmen. Ausschalten löscht keine Historie. `record=true` sorgt auch bei `active=false` für die notwendige Abfrage. Änderungen werden lokal gespeichert und nach MariaDB gespiegelt; während eines DB-Ausfalls bleiben sie als ausstehend sichtbar. Späte Übernahme alter DB-Einstellungen überschreibt keine bereits lokal geänderten Sensoren.

`/api/v1/runtime` zeigt Discovery, Heizungsverbindung, lokale Speicherprobleme, Historienverbindung, tatsächlich gespeicherte Punkte, ausgelassene Zyklen, ausstehende Einstellungen und Verdichtung. Der im Sammlerstatus akzeptierte Historien-Auftrag ist noch keine Commit-Bestätigung; die tatsächliche Speicherung steht im Historienstatus.

OpenAPI: `/api/v1/openapi.json`. `/values`, `/history` und die vorhandenen Jobs bleiben kompatibel. Bestandsansicht und alte Hardwaretests erlauben keine Sensoränderungen.

## MariaDB ohne manuelle Tabellenarbeit

Der Historien-Worker verbindet sich unabhängig vom Heizungsworker. Bei nicht vorhandener/leerer DB legt er sechs benötigte p4d-0.10.2-kompatible Tabellen und Indizes aus dem paketierten bereinigten Bestands-Snapshot an. Dies ist kein vollständiger Ersatz sämtlicher p4d-Nebenfunktionen. Erstellen erfordert entsprechende Datenbankberechtigungen; Fehler werden sichtbar, ohne Live-Betrieb zu beenden.

Bestehende DBs werden geprüft und nicht migriert oder neu initialisiert. Bestehende Messreihen, Menüzeilen und individuelle Auswahl bleiben erhalten. Neue Sensordefinitionen können ergänzt werden; bestehende Auswahlflags ändern sich nur bei einer entsprechenden Benutzeränderung. Eine selbst begonnene leere Einrichtung kann anhand des lokalen Einrichtungsmarkers fortgesetzt werden; unbekannte Teilbestände werden erhalten und als unpassend gemeldet.

Im aktuellen Standalonebetrieb erzeugt `record=A` Messpunkte für normale Sensoren. UD 1–3 (Status, Betriebsart, Heizungszeit) werden ab 0.5.5 wie bei p4d intern immer aufgezeichnet, unabhängig vom gespeicherten Flag. `samples` und `peaks` werden gemeinsam transaktional geschrieben. MariaDB-Ausfälle erzeugen gemeldete Aufzeichnungslücken; kein nachträglicher Puffer und kein Wiederholen unklarer Commits. Die begrenzte Arbeitswarteschlange ist kein garantierter Ausfallspeicher.

Verdichtung übernimmt `p4d.aggregateHistory` und `p4d.aggregateInterval` (aktuell im Bestand 91 Tage/30 Minuten; Defaults ebenso). Täglich um 01:00 Europe/Berlin, höchstens sieben Tagespakete pro Lauf mit gespeichertem Fortschritt. Nur vollständige alte Intervalle: Kennung A, Intervallende, auf zwei Stellen gerundeter `sum(value)/count(*)`-Wert und ursprüngliche Anzahl. Text stammt deterministisch vom letzten Messpunkt im Intervall. Vorhandene Aggregate werden nicht überschrieben; Konfliktintervalle bleiben mit ihren Einzelwerten erhalten und werden gezählt. Einfügen und Löschen erfolgen pro Tagespaket in derselben Transaktion. Ungültige Verdichtungseinstellungen deaktivieren die Verdichtung, nicht die Aufzeichnung.

## Heizungs-Schreiben und Abnahme

Im neuen Hardwarebetrieb bleibt Schreiben standardmäßig gesperrt. Die Parameter-/Zeit-Schreibpfade sind implementiert. Auf der Bestandsanlage wurde normales Parameterschreiben am 17.10.2026 mit Änderung und Rückstellung der LED-Helligkeit bestätigt und anschließend freigeschaltet; Zeitprogramm-Schreiben bleibt gesperrt. Simulator-Modus dient zur Prüfung der Abläufe:

```sh
.venv/bin/python -m froeling_bridge serve --mode standalone-demo --state-dir .local/demo-independent
```

Für den vereinbarten Hardwaretest steht `python -m froeling_bridge.validate_write` bereit. Es verlangt ausdrücklich Gerätepfad, genau ausgewählten Parameter/Wert beziehungsweise Zeitadresse/Intervall und einen privaten Zustands-/Nachweispfad. Nur bei vollständig bestätigter Änderung wird automatisch der vorherige Wert zurückgestellt und nachgelesen. Bei unklarem Ausgang erfolgt keine automatische Wiederholung oder vermutete Rückstellung; dann ist manuelles Nachlesen erforderlich. `--simulate` erzeugt ausdrücklich **keinen** gültigen Hardware-Nachweis.

Erst nach vereinbartem echten Test wird dessen Nachweis über `write_validation` in der geschützten Dienstkonfiguration ausgewählt. Gerät, beobachtete Firmware und die tatsächlich geprüften Operationen müssen passen. Parameter- und Zeit-Schreiben werden getrennt freigegeben; die API liefert `write_operations`. Vor einem Hardwaretest den seriellen Dienst kontrolliert stoppen; niemals parallel öffnen. Dieser Test wird nicht durch Installation, Discovery oder Browseraufruf ausgelöst.

## Sicherung und Wiederherstellung

```sh
sudo /opt/froeling-bridge/0.5.0/venv/bin/python -I -m froeling_bridge.state_backup backup --archive /geschuetzt/bridge-backup.zip
sudo /opt/froeling-bridge/0.5.0/venv/bin/python -I -m froeling_bridge.state_backup restore --archive /geschuetzt/bridge-backup.zip
```

Backup verwendet die SQLite-Backupfunktion und enthält Katalog/Einstellungen, letzte Werte, Zeitcache und die geschützte Konfiguration einschließlich optionaler DB-Zugangsdaten. Datei 0600; privat aufbewahren. **MariaDB-Historie ist nicht enthalten.** Restore nur bei gestopptem Dienst in leere Zielpfade. Heizungs-Schreibfreigaben werden nicht automatisch auf einen anderen Rechner übertragen. Nach Root-Restore führt die erneute Installation die Besitzrechte für den Dienstbenutzer korrekt nach.

## Stand des Nachweises

Automatisierte Tests, separate MariaDB, echte Pseudo-TTY mit HTTP, Browser und reale systemd-Ersatzdienste prüfen die Implementierung. Eine isolierte Debian-Installation prüft Paketinstallation, Dienstbenutzer/Rechte, seriellen Erststart und Wiederholung; systemd-Aufrufe sind in diesem Container simuliert und separat gegen echte Ersatzdienste geprüft. Auf der tatsächlichen Steuerung sind vollständige Discovery, aktuelle Werte, fortlaufende Aufzeichnung und Dienstneustart mit 0.5.2 bestätigt. Die 24h-Beobachtung läuft im Hintergrund bei funktionierendem Monitoring. Noch erforderlich: deren erfolgreicher Abschluss, kontrollierter Neustart des gesamten Hosts und ein separat vereinbarter realer Zeitprogramm-Schreibtest. Normales Parameterschreiben wurde inzwischen durch den LED-Test bestätigt. Ein Hostneustart ist aktuell ausdrücklich nicht beauftragt. Bis dahin keine Zusage vollständiger Hardwarevalidierung.


Reproduzierbare Zusatzprüfungen aus dem Checkout:

```sh
PYTHONPATH=src .venv/bin/python docs/tools/verify_standalone_pty.py
sudo .venv/bin/python docs/tools/verify_standalone_lifecycle.py --run-local-spares
python3 docs/tools/monitor_standalone.py --url http://SERVER-IP:8000 --report .local/24h-read-report.json
```

Der Monitor fragt nur HTTP-Zustand/Cache ab, sendet keine Heizungsjobs und speichert keine Messwerte/Zugangsdaten. Standarddauer 24 Stunden; ein abgebrochener oder fehlgeschlagener Lauf wird nicht als bestanden ausgegeben. Vorhandene Berichte werden erhalten. Native Installationsprüfung: `docs/tools/verify_native_install.py --in-container` ausschließlich in einem wegwerfbaren Debian-Container mit Python, psmisc und sudo, Checkout read-only unter `/source`. Sie ersetzt nur dort systemd-Kommandos durch den Testadapter; auf dem Host wird sie ausdrücklich abgewiesen.

### Parametermenü ab 0.5.3

Die Bearbeitung folgt dem p4d-Menüumfang: unterstützte Zahlen-, Ja/Nein- und Uhrzeitparameter sowie benannte Zeitprogramme. Aktuelle Editorwerte und Grenzen kommen aus der Steuerung; einmal „Speichern“ genügt. Nachlesen, Fehlermeldung bei unklarem Ausgang und Schreibsperren bleiben erhalten. Details und Simulator-Browserprüfung in [parameter-menu.md](parameter-menu.md#bedienung-nach-originalvorlage-ab-053). Die Installation allein erweitert keine Heizungs-Schreibfreigaben. Auf dem Bestandsrechner wurde `write_parameter` anschließend nach dem vereinbarten erfolgreichen LED-Test ausdrücklich aktiviert.

### Heizungsfehlerspeicher ab 0.5.4

Die Bridge liest die vollständige First-/Next-Fehlerliste beim Start, danach im Sammelintervall (standardmäßig 60 Sekunden) und bei erkanntem Zustandswechsel. Derselbe serielle Worker verhindert Parallelzugriffe. Nur ein vollständig gelesener und auswertbarer Stand ersetzt den persistenten SQLite-Cache. Ein Lesefehler erhält alte Daten mit ihrem ursprünglichen Zeitstempel und sichtbarer Fehlermeldung.

`GET /api/v1/errors` und die Webansicht „Fehlerspeicher“ liefern diesen Cache ohne neue Heizungsabfrage. `available`, `observed_at`, `age_seconds`, `stale`, `error` und `last_attempt` unterscheiden eine aktuelle leere Liste von fehlenden oder alten Daten. Die Liste zeigt zuordenbare Vorkommnisse des aktuellen Steuerungsfehlerspeichers; zusätzliche ältere MariaDB-Einträge bleiben erhalten.

Bei konfigurierter MariaDB synchronisiert der getrennte Historienworker die bestehende p4d-Tabelle `errors`. Zuordnung und Zustandsübergänge folgen `P4d::updateErrors`: Schlüssel Fehlernummer und Auftretenszeit, „gekommen“/„gegangen“/„quittiert“, `time1`/`time4`/`time2`. Bestehende IDs, Quittierungen, Mailzähler und außerhalb des Steuerungsspeichers liegende Historie bleiben erhalten. Keine Fehlerquittierung wird an die Heizung gesendet. Ein fehlgeschlagener DB-Abgleich wird separat in `/api/v1/runtime.history.controller_errors` gemeldet und beeinträchtigt weder aktuelle Messungen noch die übrige Aufzeichnung. Der DB-Abgleich wird nach 30 Sekunden erneut versucht, ohne neue serielle Schreibbefehle. Bestehende Tabellen werden nicht migriert; eine neue/leere Datenbank erhält die kompatible Fehler-Tabelle automatisch.

**Bestehende SQL-Clients:** Original-p4d erzwingt für Status, Betriebsart und Heizungszeit (UD 1–3) die interne Aufzeichnung in `applyConfigurationSpecials`, auch wenn das gespeicherte Recordflag ausgeschaltet ist. Der Standalone-Nachbau übernimmt dies ab 0.5.5; eine zuvor dokumentierte gegenteilige Aussage war falsch. Gespeicherte Flags bleiben unverändert. API-Livewerte sind weiterhin von MariaDB unabhängig. SQL-Clients sollten den Messzeitpunkt prüfen, um einen ausgefallenen Collector nicht mit einem aktuellen Zustand zu verwechseln.

Ein vorhandener Client liest `samples` für `address=1 AND type='UD'` nach `updsp DESC`. Das liefert bei aktiver Aufzeichnung aktuell den richtigen Status, ist aber gegenüber Verdichtung anfällig: `updsp` bezeichnet die Datenbankaktualisierung, nicht den Messzeitpunkt. Für den jüngsten Einzelmesspunkt verwenden:

```sql
SELECT text, time
FROM samples
WHERE address = 1 AND type = 'UD' AND aggregate = 'S'
ORDER BY time DESC
LIMIT 1;
```

Der Client sollte `time` auf ausreichende Aktualität prüfen. Ein erfolgreicher SELECT allein belegt keinen laufenden Heizungszugriff. Diese Empfehlung ändert weder die vorhandene Clientsoftware noch ihre Recordflags.

### Automatische interne Werte ab 0.5.5

`GET /api/v1/sensors` liefert `recording` als effektive Aufzeichnung, `configured_recording` als gespeichertes Flag und `recording_required` für die automatische UD-Regel. Bei UD 1–3 ist `recording=true` auch bei leerem/ausgeschaltetem Flag. Die Webansicht kennzeichnet diese Werte ausdrücklich als automatisch aufgezeichnet; ihr Historie-Kästchen ist aktiviert und nicht abschaltbar. Normale Sensorflags bleiben frei einstellbar. Automatische Aufzeichnung führt ohne konfigurierte MariaDB nicht zur Pflicht, eine Historien-DB einzurichten; Livewerte funktionieren weiterhin allein.

Originalbeleg: [applyConfigurationSpecials im Referenzstand](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/specific.c#L389), ebenso im tatsächlich installierten Originalquellstand 1bc324d. Der Speicherpfad allein zeigt nur die Prüfung des **bereits intern überschriebenen** Recordflags; daraus darf keine Abhängigkeit vom sichtbaren gespeicherten Flag abgeleitet werden.

### Darstellung des Fehlerspeichers

Ab 0.5.5 verwenden Fehlermeldungen eigene Einträge mit voller Textbreite, Zustandskennzeichnung und zugehörigen Zeitpunkten. Sie verwenden nicht mehr das Menü-Raster mit schmaler Symbolspalte. Auf kleinen Displays stehen die Zeitpunkte untereinander; auf dem Desktop nebeneinander. Auch die Kopfzeile bricht bei sehr kleinen Displays um.

`PYTHONPATH=src .venv/bin/python docs/tools/verify_error_browser.py --simulate-only` prüft im Chromium 320/390/768/1440 Pixel, lange fiktive Meldungen, alle drei Zustände, Zeitdarstellung, Seitenbreite und sichere Textausgabe ohne HTML-Auswertung. Ausschließlich Simulator, kein Zugriff auf die echte Heizung.
