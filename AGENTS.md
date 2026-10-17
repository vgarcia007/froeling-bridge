# Arbeitskontext für Fröling Bridge

## Einstieg in jede Session

1. `git status --short --branch` und Submodulstatus prüfen; vorhandene Benutzeränderungen erhalten.
2. `docs/project-context.md` und `docs/decisions.md` lesen. Falls vorhanden, zusätzlich `.local/operator-context.md` lesen; dort liegen ausschließlich lokale Betreiberangaben. Öffentliche Beispieladressen sind keine Live-Ziele.
3. Für Fachfragen `docs/README.md` und die dort verlinkte Bestandsaufnahme lesen. Quellcode ist die Autorität für Bestandsverhalten; Annahmen und Empfehlungen davon unterscheiden.

Mit dem Benutzer auf Deutsch und konkret kommunizieren. Er möchte schrittweise einen Python-Nachbau auf Grundlage belegter Protokoll-/Datenbankkenntnisse entwickeln und hat die autonome Umsetzung des Offline-Kerns beauftragt. Routineentscheidungen selbst treffen und dokumentieren; nur bei tatsächlich fehlenden Freigaben oder blockierenden Informationen nachfragen.

## Ziel und feste Grenzen

- p4d ist die verbindliche funktionale Vorlage. Vor Änderungen den vollständigen relevanten Ablauf in Protokoll, Dienst, Datenbank und Webmenü sowie die bestehenden Fachnotizen abgleichen. Namen, Menüpfade, Adress-/Wochentagszuordnung und Cacheverhalten gehören zum Funktionsumfang, nicht zu späteren kosmetischen Extras. Benutzer möchte nicht erneut auf bereits dokumentiertes Originalverhalten hinweisen müssen.
- Empfangene Heizungsdaten nach dem Original verlustfrei lesen; keine Eingabevalidierung auf Rohantworten anwenden. Abweichungen ausdrücklich belegen, begründen und testen. Moderne Darstellung darf keine namenlosen Rohadressen oder zusätzliche manuelle Leseschritte anstelle vorhandener p4d-Funktionen einführen.

- Schwerpunkt: Heizung lesen, Parameter zuverlässig schreiben, moderne API und Servicemenü; einfache Installation.
- Bestehende MariaDB und historische Messreihen weiterführen; p4d als Rückfalloption erhalten.
- Kein dauerhafter Parallelbetrieb zweier unabhängiger serieller Heizungsdienste als Default.
- Charts, Dashboards, Pelletverwaltung und weitere Integrationen zunächst außerhalb des Kernumfangs.
- Lokaler API-Prototyp: Flask 3.1/Waitress 3, PyMySQL 1.1 und /api/v1; siehe docs/service.md. Webmenü: paketiertes HTML/CSS/JavaScript. Lesender Hosttest mit Rückkehr: docs/host-test.md. Produktionsauthentifizierung, endgültige Installation und neue Projektlizenz sind noch offen.
- Herkunft und Arbeit von Jörg Wendel und den p4d-Mitwirkenden respektvoll würdigen. Keine unbelegte Kritik oder Behauptung einer offiziellen Zusammenarbeit.

## Aktuelle Absprache: unverändert beobachten

Benutzer lässt den Stand zunächst einige Tage laufen und prüft selbst. Ohne neuen Auftrag keine weiteren Deployments, Neustarts oder Heizungs-Schreibtests. Bestehende automatische Erfassung, Aufzeichnung und Gesundheitsüberwachung unverändert laufen lassen. Aktuellen Quell-/Dokumentationsstand auf GitHub sichern; bei Rückmeldung mit dem dokumentierten Stand fortsetzen.

## Aktuelle Heizungs-Schreibfreigabe (17.10.2026)

Der Benutzer hat den konkreten LED-Helligkeitstest mit Änderung um einen Prozentpunkt und unmittelbarer Rückstellung bestätigt. Test am echten Gerät erfolgreich: frische Ausgangsmetadaten, Änderung, beide Bestätigungen, frisches Nachlesen, Rückstellung und erneutes Nachlesen. Danach wie vereinbart `write_parameter` für das normale p4d-Parametermenü aktiviert. Aktuelle Produktionskonfiguration verwendet den geschützten Geräte-/Firmware-Nachweis unter `/etc/froeling-bridge/write-validation.json`. Keine eigene Parameter-Freigabeliste; dieselben sechs Menütypen wie p4d. Zeitprogramm-Schreiben bleibt gesperrt (`write_time_range` nicht validiert). Keine weiteren beliebigen Teständerungen autorisiert. Frühere pauschale Heizungs-Schreibsperren weiter unten sind historische Freigabestände.

Benutzer fragt nach Bootverhalten und sagt ausdrücklich „nicht machen“: keinen Hostneustart ausführen. Lesend bestätigt: Bridge enabled/active, p4d disabled/inactive, Gesundheits-Timer enabled/active; wirksame Host-Drop-in setzt `Restart=no` und `OnFailure` auf Rückkehr zu p4d.

## Aktueller administrativer Zugriff (17.10.2026)

Administrative Zugriffsdaten und Berechtigungen werden ausschließlich im privaten Betreiberkontext festgehalten. Bestehende Autorisierung beachten, verfügbare Rechte bei Bedarf lesend prüfen und den laufenden Betrieb schützen. Daraus folgt keine Freigabe für Heizungsänderungen.

## Neuer Auftrag: eigenständiger Ersatz ab 0.5.0

Der Benutzer hat den Plan für unabhängigen Erststart, Discovery, lokale SQLite-Arbeitsdaten, optionale automatische MariaDB-Einrichtung, Sensor-Auswahl und Verdichtung ausdrücklich zur Implementierung freigegeben. Live-Werte und Menü haben Vorrang vor Historie. Dies erweitert die früheren Nur-Lesen-/Nur-samples-Grenzen im beschriebenen Umfang:

- Eigenständige Installation und Discovery ohne p4d-Bestand, bestehende DB kompatibel weiterführen, neue/leere DB nach expliziter Konfiguration automatisch erstellen. Kein ungefragtes Migrieren bestehender DBs.
- Sensor-Abfrage-/Recordflags dürfen über die neue Oberfläche/API geändert und mit valuefacts synchronisiert werden. Historienverdichtung nach vorhandener Konfiguration ist beauftragt; Einfügen/Löschen transaktional und zunächst separat testen. Agent darf keine Live-Flags nur zum Test umschalten.
- MariaDB-Fehler dürfen Live-Abfragen und Menü nicht beenden. Lokale SQLite-Datei ist dauerhaft, keine Historienpflicht. Wiederherstellung ohne Katalog muss durch Discovery funktionieren.
- Heizungsparameter bleiben bis zum separat vereinbarten Test mit ausgewähltem Parameter und Zielwert gesperrt. Implementierung der Schreibfreigabe ist autorisiert; tatsächliche Heizungs-Schreibtests sind dadurch nicht pauschal erlaubt.
- Hardware-Abnahme verlangt vollständige Discovery, 24 Stunden echten Lesebetrieb und kontrollierten Hostneustart. Nicht aus Simulator-/Pseudo-TTY-Erfolg ableiten. Installation/Abnahme sind von implementiertem Code klar zu unterscheiden.
- Neue Anleitung docs/standalone.md ist maßgeblich. Historische Angaben zu reiner DB-Aufzeichnung/15-Minuten-Grenzen weiter unten sind nur Kontext.

## Aktuelle Freigabe: produktive Aufzeichnung und Dauerbetrieb

Der Benutzer hat nach dem erfolgreichen Lesefenster ausdrücklich bestätigt: „ja wir schreiben nun auch un lassen es laufen“. Dies erweitert die bisherigen Grenzen ausschließlich wie folgt:

- Dauerbetrieb mit exklusivem Heizungs-Lesezugriff und Messwertaufzeichnung in der bestehenden p4d-Datenbank ist autorisiert. Nur `samples` und `peaks` über den geprüften kompatiblen Recorder fortführen; Metadaten und Historie ansonsten lesend. Keine Schemaänderung, Initialisierung, Löschung oder neue Aggregation.
- Umschaltung einschließlich p4d-Stop/Autostartwechsel, neuem Bridge-Autostart und Rückfall zu p4d ist autorisiert. Originalinstallation erhalten. Eigener Produktionsdienst ohne 15-Minuten-Limit; siehe docs/production.md.
- Heizungsparameter schreiben bleibt ausdrücklich gesperrt. Testbetrieb/Bestandsansicht behalten ihre bisherigen Schreibgrenzen. Historische Nur-Lesen-Angaben weiter unten beschreiben die frühere Freigabe und werden durch diesen Abschnitt nur im genannten Umfang ersetzt.
- Administrative Zugriffslage privat dokumentieren; erforderliche Rechte vor freigegebenen Aktionen prüfen. Keine zusätzlichen Heizungs-Schreibrechte daraus ableiten.

## Live-Datenbank: ausdrücklich nur lesen

Der Benutzer hat am 16.10.2026 Zugang zur laufenden Original-p4d-Datenbank über die lokale Datei `live-db.con` gegeben, ausschließlich zum Umsehen.

- Keine Änderungen an Daten, Schema, Benutzern, Berechtigungen oder Servereinstellungen. Keine Migrationen, Schreibtests, Initialisierung, Bereinigung oder Aggregation gegen die Live-DB.
- Keinen p4d-Daemon gegen die Live-DB starten: schon Startup/Default-Lesen kann Schema und Konfiguration ändern.
- Ausschließlich eng begrenzte lesende SQL-Abfragen (`SELECT`, `SHOW`); Tabellen-Metadaten bevorzugen. Kein `SELECT FOR UPDATE`, keine Sperr-/Adminoperationen und keine teuren Volltabellenanalysen der Historie.
- Wo vom Treiber unterstützt, eine read-only Session/Transaktion als zusätzliche Schranke setzen; das ist kein Ersatz für die Beschränkung der SQL-Abfragen.
- Zugangsdaten nicht ausgeben, committen oder in Shellargumente schreiben. `live-db.con` bleibt ignoriert. Keine vollständigen Config-/User-Dumps, Token, privaten Netzadressen oder privaten Betriebsdaten ins Repository aufnehmen.
- Repository-Dokumentation darf bereinigte Schema-/Kompatibilitätsbefunde enthalten. Raw-Ergebnisse und Mitschnitte bleiben lokal und ignoriert.
- Schreibversuche gehören später ausschließlich auf eine separate DB-Kopie; direkte Heizungs-Schreibtests müssen gesondert mit dem Benutzer vereinbart werden.

## Live-Server per SSH: Bestandsaufnahme und freigegebener Lesetest

Der Benutzer stellt `live-server-ssh.con` für den zuvor angebotenen lesenden SSH-Zugriff bereit. Auch diese Datei bleibt ignoriert und wird nicht ausgegeben. Private SSH-Ergebnisse und Hostschlüssel liegen unter `.local/`, nicht im Repository. Der Benutzer hat inzwischen den erweiterten Plan einschließlich Webmenü, vorbereiteter einmaliger Einrichtung und 15-minütigem lesendem Hardwaretest ausdrücklich zur Umsetzung beauftragt; das aktualisiert die frühere reine SSH-Bestandsaufnahme-Freigabe wie folgt.

- Für freigegebene Hostarbeiten vorher Umfang und erforderliche Rechte prüfen. Persönliche Zugriffs- und Berechtigungsdetails stehen ausschließlich im privaten Betreiberkontext; sie gehören nicht in die öffentliche Dokumentation.
- Keinen weiteren p4d-Prozess starten; auch keine vermeintlichen Versions-/Hilfeflags ausführen, solange deren Nebenwirkungsfreiheit nicht belegt ist.
- Der Adapter liegt unter `/dev/ttyUSB0`. Nur innerhalb des vorbereiteten hardware-read-Testfensters nach aktiviertem Rückkehrtimer, beendetem p4d und geprüfter Portfreigabe öffnen. Kein Parallelzugriff. Keine Heizungs-Schreibbefehle; Originaldatenbank bleibt strikt lesend, Aufzeichnung nur in separater Test-MariaDB. Außerhalb dieses Ablaufs Port nicht öffnen oder konfigurieren.
- Vorhandener Quellcommit, lokale Änderungen und tatsächlich laufende Binärdatei sind getrennte Belege. Eine Gleichheit nicht allein aus einem vorhandenen Checkout folgern.
- Bestehende Logs dürfen begrenzt gelesen werden; keine Logstufe ändern oder neuen Heizungsverkehr für Mitschnitte auslösen.
- Nur bereinigte fachliche Befunde dokumentieren; keine privaten Hostnamen, IPs, Benutzerpfade, Zugangsdaten oder ungefilterten Logs committen.

## Repository und Referenz

- Eigenes Remote: `git@github.com:vgarcia007/froeling-bridge.git`, öffentlich; keine persönlichen Betriebsdaten veröffentlichen.
- Originalcode als Submodul: `reference/linux-p4d`, Herkunft `https://github.com/vgarcia007/linux-p4d.git`.
- Untersuchte Referenz: `4d1176c4a9081893e4c2cc27a535bb2bc4737d0a`. Referenzcode unverändert lassen und nicht still aktualisieren.
- Python-Kern: `src/froeling_bridge`, Anleitung `docs/python-core.md`. Python >=3.9, Kern ohne externe Laufzeitabhängigkeiten. Optional `.[service]` für API/DB; Anleitung `docs/service.md`. Tests: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v`; MariaDB-Integration nur mit explizitem `FROELING_TEST_DB_CONFIG` für separate lokale Test-DB.
- Zusätzliche Offline-Prüfung: `python3 docs/tools/verify_protocol_examples.py`. Sie prüft Original-Bytecodierung, nicht die reale Schreibsemantik.
- Reale Schreibmitschnitte dienen zusätzlicher Hardwarevalidierung, blockieren aber die quellenbasierte Implementierung nicht. Default-Antwortcodes des Simulators sind unbestätigte Annahmen. Keinen TTY-Adapter oder Live-Betrieb daraus als bereits geprüft ableiten.

## Kontinuität und Sicherung

- Nach abgeschlossenen Arbeitspaketen `docs/project-context.md` aktualisieren: belegte Ergebnisse, aktuelle Phase, Prüfungen, offene Punkte, nächster Schritt. Dauerhafte Entscheidungen in `docs/decisions.md` ergänzen.
- Bestehende Fachnotizen aktualisieren statt widersprüchliche Parallelzusammenfassungen anzulegen. Keine privaten Gedankengänge, Zugangsdaten oder ungefilterten Tool-Ausgaben als Kontext speichern.
- Der Benutzer möchte bereinigte Arbeitsstände im öffentlichen Repository sichern. Zusammenhängende, überprüfte Änderungen committen und auf den eingerichteten Branch pushen; keine Force-Pushes oder destruktiven Git-Operationen. Benutzeränderungen nur einbeziehen, wenn sie zum autorisierten Arbeitspaket gehören.
- Vor Commit/Push staged Diff, ignorierte Verbindungsdatei und Submodul-Pin prüfen. Falls Push scheitert, lokalen Commit erhalten und den fehlenden Remote-Stand klar berichten.
- Im Abschluss nennen, was tatsächlich gespeichert/gepusht wurde und was noch unbestätigt ist. Ein Push ist keine Zusage eines vollständigen Backups: lokale Secrets und ignorierte Artefakte sind davon ausgeschlossen.
