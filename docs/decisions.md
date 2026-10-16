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

Python-/API-Framework, endgültiger DB-Treiber, API-Vertrag, Frontendtechnik, Authentifizierung, Installations-/Deploymentweg und Lizenz für neu geschriebene Projektteile. PyMySQL in der lokalen Untersuchungsumgebung ist keine Architekturentscheidung.
