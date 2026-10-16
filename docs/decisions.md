# Entscheidungsprotokoll

Hier stehen dauerhafte Vereinbarungen, keine ungeprüften Annahmen. Neuere Entscheidungen ergänzen oder ersetzen ältere ausdrücklich.

## 16.10.2026 — Richtung und erster Arbeitsumfang

- Eigenständiger Python-Nachbau mit Schwerpunkt Heizung lesen, Parameter schreiben, dokumentierte API und modernes Servicemenü.
- Zuerst Bestandsanalyse und Dokumentation; noch kein Python-Heizungsprototyp.
- Bestehende MariaDB samt Historie weiterführen; Original-p4d als Rückfalloption erhalten. Dauerhafter Parallelbetrieb zweier Logger ist nicht das Standardziel.
- Charts, Dashboards und weitere Integrationen zunächst nachrangig.
- Protokollverhalten aus Originalcode ableiten, Annahmen und unbekannte Felder ausdrücklich kennzeichnen. Tatsächliche Hardwarekompatibilität erst mit echten Belegen bestätigen.

## 16.10.2026 — Name, Herkunft und Sicherung

- Name und Remote: `froeling-bridge`, `git@github.com:vgarcia007/froeling-bridge.git`, zunächst privat.
- Benutzer beauftragt Einrichtung, Commit und Push; zusammenhängende Arbeitsstände sollen im Remote gesichert werden.
- p4d als unverändertes, gepinntes Git-Submodul einbinden; Referenzcommit `4d1176c4a9081893e4c2cc27a535bb2bc4737d0a`.
- README würdigt Jörg Wendel (horchi), die Mitwirkenden und p4d als Grundlage. Keine offizielle Verbindung zum Originalprojekt oder Hersteller behaupten.
- `AGENTS.md`, `project-context.md` und dieses Protokoll dienen der Fortsetzung in neuen Sessions.
- Zugangsdaten, Rohberichte, Datenbankdumps und lokale Mitschnitte nicht ins Repository aufnehmen; für deren Sicherung wird keine Git-Backup-Zusage gemacht.

## 16.10.2026 — Zugang zur laufenden Datenbank

- Benutzer stellt `live-db.con` bereit, ausdrücklich nur zum lesenden Umsehen.
- Keine Änderungen an Live-Daten, Schema, Rechten oder Server; keinen p4d-Daemon dagegen starten.
- Struktur- und eng begrenzte Metadatenabfragen zulässig. Verbindung zusätzlich über eine Read-only-Transaktion absichern.
- Nur bereinigte Schema-/Kompatibilitätsbefunde tracken. Private Rohdaten lokal ignorieren.
- Die DB-Zugriffserlaubnis enthält keine Freigabe für Heizungs-Schreibversuche oder Hoständerungen.

## 16.10.2026 — Lesender SSH-Zugang und installierter Zielstand

- Benutzer stellt `live-server-ssh.con` für die angebotene lesende Bestandsaufnahme bereit. Keine Änderungen am Live-Host, Dienst oder Port.
- Benutzer bestätigt den RS232-USB-Adapter auf dem Live-Server unter `/dev/ttyUSB0`; kein paralleles Öffnen zu p4d.
- Als vorhandener Zielstand ist nun p4d 0.10.2 / Commit `1bc324dc46296a6bd1f8bbeffe2527efe3da2446` belegt (Quellcheckout und Versionskennung der Dienstpfad-Binärdatei). Beleggrenzen stehen in `live-server.md`.
- Der jüngere Referenz-Submodul-Pin bleibt erhalten. Für DB-Kompatibilität das tatsächliche 0.10.2-Schema verwenden, keine automatische Migration auf den jüngeren Stand.
- Existierende Logausschnitte nur offline analysieren. Kein neuer Schreibtest und keine Änderung der Logstufe.

## 16.10.2026 — Autonome Umsetzung des Offline-Kerns

- Benutzer beauftragt nach dem Versions-/Schemaabgleich die Umsetzung des Offline-Protokollkerns und Simulators, möglichst ohne weitere Interaktion. Die frühere Beschränkung auf reine Dokumentation ist für diesen Baustein aufgehoben.
- Python >=3.9 mit Standardbibliothek und setuptools-Paketierung; keine externen Laufzeitabhängigkeiten und keine Vorentscheidung zu HTTP-/DB-Frameworks.
- Exklusive vollständige Transaktionen mit Gesamtdeadline. Nach Protokoll-/Transportfehlern Sitzung sperren; keine automatische Wiederholung oder blindes Leeren des Streams.
- Änderungserfolg nur nach passend interpretiertem Nachlesen. Nach begonnenem Schreibversuch ohne vollständige Bestätigung `WriteOutcomeUnknown`; abweichendes gültiges Nachlesen separat als `WriteVerificationError`.
- Zeitprogramme mit nullbasiertem Index 0..3, frischem Einlesen aller vier Intervalle und expliziten Zehn-Minuten-Schritten; keine implizite Rundung.
- Antwortcodes des Simulators sind eine unbestätigte Echo-Konvention und austauschbar. Kein physischer TTY-Transport; alle Demo-/Testdaten synthetisch. Keine Änderung der Live-Zugriffsgrenzen.

## Noch nicht entschieden

Frontendtechnik, Produktionsauthentifizierung, endgültiger Deploymentweg und Lizenz für neue Projektteile. Framework, DB-Treiber und API-Vertrag für den lokalen Prototyp wurden inzwischen wie unten beschrieben entschieden.


## 16.10.2026 — Kontinuierliche Datensammlung und lokale API

- Benutzer beauftragt Umsetzung des erweiterten Plans: kompatible DB-Anbindung, kontinuierliche Sammlung/Speicherung, HTTP-API und simuliertes Parameterschreiben; modernes Browsermenü folgt.
- Ein Schreibmitschnitt aus dem alten Webinterface ist keine Voraussetzung. Code ist die Implementierungsgrundlage; unbekannte Antwortdetails ausdrücklich kennzeichnen und später gesondert an der Hardware prüfen.
- Python >=3.9 erhalten. Flask >=3.1,<3.2, Waitress >=3,<4 und PyMySQL >=1.1,<1.2 im optionalen Service-Extra. Protokollkern bleibt unabhängig.
- Lokaler Prototyp bindet ausschließlich an 127.0.0.1; kein Debugger/Reload. Drei getrennte Modi demo/demo-db/database. Bestandsansicht ausschließlich lesend, kein vermischter Live-/Simulatorbetrieb.
- Aufzeichnungsintervall standardmäßig 60 Sekunden, keine Überlappung oder Aufholbursts. Einzelner Heizungsbesitzer mit vollständigen Transaktionen und FIFO; Datenbankarbeit getrennt davon.
- Lokales Schreiben ausschließlich auf benannte Testdatenbanken unter Loopback. Kein Produktivwriter, keine automatische Migration und keine Initialisierung beim Dienststart. Testwerkzeug erzeugt bekannten Schemaausschnitt und synthetische Fixtures ausdrücklich separat.
- samples und peaks transaktional; Sensoridentität, bereits skalierte Werte, S-Kennung, lokale Europe/Berlin-Zeit und Unix-Metafelder erhalten. Schlüsselkonflikte aktualisieren Werte und updsp, erhalten inssp. Kein Daten-Nachlieferungspuffer; unklare Commit-Ergebnisse nicht wiederholen.
- Unterstützte Sammlung: VA, DO/DI/AO, UD 1–3; weitere Typen sichtbar überspringen. Aggregation/Bereinigung vor vollständiger Ablösung gesondert implementieren. Bestehende Historie/Metadaten und Fremdintegrationen nicht verändern.
- /api/v1 mit dokumentiertem OpenAPI-Vertrag. Jobs queued/running/completed/failed, Schreibbestätigung weiterhin ausschließlich durch Nachlesen. FIFO 64, maximal 1.000 flüchtige Jobresultate; keine Wiederholung nach Neustarts.
- Kein Zugriff auf Live-DB/-Server und kein Portzugriff im Implementierungspaket. Keine neue Freigabe für produktive Schreibtests oder Dienstaktionen abgeleitet.
