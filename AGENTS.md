# Arbeitskontext für Fröling Bridge

## Einstieg in jede Session

1. `git status --short --branch` und Submodulstatus prüfen; vorhandene Benutzeränderungen erhalten.
2. `docs/project-context.md` und `docs/decisions.md` lesen. Falls vorhanden, zusätzlich `.local/operator-context.md` lesen; dort liegen ausschließlich lokale Betreiberangaben. Öffentliche Beispieladressen sind keine Live-Ziele.
3. Für Fachfragen `docs/README.md` und die dort verlinkte Bestandsaufnahme lesen. Quellcode ist die Autorität für Bestandsverhalten; Annahmen und Empfehlungen davon unterscheiden.

Mit dem Benutzer auf Deutsch und konkret kommunizieren. Er möchte schrittweise einen Python-Nachbau auf Grundlage belegter Protokoll-/Datenbankkenntnisse entwickeln und hat die autonome Umsetzung des Offline-Kerns beauftragt. Routineentscheidungen selbst treffen und dokumentieren; nur bei tatsächlich fehlenden Freigaben oder blockierenden Informationen nachfragen.

## Ziel und feste Grenzen

- Schwerpunkt: Heizung lesen, Parameter zuverlässig schreiben, moderne API und Servicemenü; einfache Installation.
- Bestehende MariaDB und historische Messreihen weiterführen; p4d als Rückfalloption erhalten.
- Kein dauerhafter Parallelbetrieb zweier unabhängiger serieller Heizungsdienste als Default.
- Charts, Dashboards, Pelletverwaltung und weitere Integrationen zunächst außerhalb des Kernumfangs.
- Framework, API-Vertrag, Installation und neue Projektlizenz sind noch nicht entschieden. Nicht als bereits vereinbart darstellen.
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

## Live-Server per SSH: ausschließlich Bestandsaufnahme

Der Benutzer stellt `live-server-ssh.con` für den zuvor angebotenen lesenden SSH-Zugriff bereit. Auch diese Datei bleibt ignoriert und wird nicht ausgegeben. Private SSH-Ergebnisse und Hostschlüssel liegen unter `.local/`, nicht im Repository.

- Zulässig sind lesende Prüfungen von Quellcheckout, Binärdatei, Dienstmetadaten, Locale/Zeitzone und vorhandenen Logs. Keine Installationen, Dateiänderungen oder Dienstaktionen auf dem Live-Server.
- Keinen weiteren p4d-Prozess starten; auch keine vermeintlichen Versions-/Hilfeflags ausführen, solange deren Nebenwirkungsfreiheit nicht belegt ist.
- Der RS232-USB-Adapter liegt laut Benutzer auf dem Live-Server unter `/dev/ttyUSB0`. Den Port nicht öffnen, konfigurieren oder parallel zum laufenden p4d benutzen. Ein `stat` auf den Gerätepfad ist eine reine Metadatenprüfung.
- Vorhandener Quellcommit, lokale Änderungen und tatsächlich laufende Binärdatei sind getrennte Belege. Eine Gleichheit nicht allein aus einem vorhandenen Checkout folgern.
- Bestehende Logs dürfen begrenzt gelesen werden; keine Logstufe ändern oder neuen Heizungsverkehr für Mitschnitte auslösen.
- Nur bereinigte fachliche Befunde dokumentieren; keine privaten Hostnamen, IPs, Benutzerpfade, Zugangsdaten oder ungefilterten Logs committen.

## Repository und Referenz

- Eigenes Remote: `git@github.com:vgarcia007/froeling-bridge.git`, öffentlich; keine persönlichen Betriebsdaten veröffentlichen.
- Originalcode als Submodul: `reference/linux-p4d`, Herkunft `https://github.com/vgarcia007/linux-p4d.git`.
- Untersuchte Referenz: `4d1176c4a9081893e4c2cc27a535bb2bc4737d0a`. Referenzcode unverändert lassen und nicht still aktualisieren.
- Python-Kern: `src/froeling_bridge`, Anleitung `docs/python-core.md`. Python >=3.9, keine externen Laufzeitabhängigkeiten. Tests: `PYTHONPATH=src python3 -m unittest discover -s tests -v`.
- Zusätzliche Offline-Prüfung: `python3 docs/tools/verify_protocol_examples.py`. Sie prüft Original-Bytecodierung, nicht die reale Schreibsemantik.
- Default-Antwortcodes des Simulators sind unbestätigte Annahmen. Keinen TTY-Adapter oder Live-Betrieb daraus als bereits geprüft ableiten.

## Kontinuität und Sicherung

- Nach abgeschlossenen Arbeitspaketen `docs/project-context.md` aktualisieren: belegte Ergebnisse, aktuelle Phase, Prüfungen, offene Punkte, nächster Schritt. Dauerhafte Entscheidungen in `docs/decisions.md` ergänzen.
- Bestehende Fachnotizen aktualisieren statt widersprüchliche Parallelzusammenfassungen anzulegen. Keine privaten Gedankengänge, Zugangsdaten oder ungefilterten Tool-Ausgaben als Kontext speichern.
- Der Benutzer möchte bereinigte Arbeitsstände im öffentlichen Repository sichern. Zusammenhängende, überprüfte Änderungen committen und auf den eingerichteten Branch pushen; keine Force-Pushes oder destruktiven Git-Operationen. Benutzeränderungen nur einbeziehen, wenn sie zum autorisierten Arbeitspaket gehören.
- Vor Commit/Push staged Diff, ignorierte Verbindungsdatei und Submodul-Pin prüfen. Falls Push scheitert, lokalen Commit erhalten und den fehlenden Remote-Stand klar berichten.
- Im Abschluss nennen, was tatsächlich gespeichert/gepusht wurde und was noch unbestätigt ist. Ein Push ist keine Zusage eines vollständigen Backups: lokale Secrets und ignorierte Artefakte sind davon ausgeschlossen.
