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
