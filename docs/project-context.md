# Aktueller Projektkontext

Zuletzt aktualisiert: 16.10.2026. Diese Datei ist der Einstieg für neue Sessions; technische Details stehen in den verlinkten Fachnotizen.

## Ziel und Zusammenarbeit

Der Benutzer betreibt Original-p4d bereits auf einem anderen Rechner. Er möchte eine einfacher installierbare Python-Variante mit einer richtigen API und einem modernen Menü zum Lesen und Schreiben von Heizungsparametern. Andere Webinterfacefunktionen haben geringe Priorität. Die vorhandene MariaDB samt Historie soll weitergeführt werden; p4d bleibt Rückfalloption.

Zunächst wurde Analyse und Dokumentation vereinbart. Nach dem Bestandsabgleich hat der Benutzer die autonome Umsetzung des Offline-Python-Protokollkerns mit Simulator freigegeben; Rückfragen nur bei tatsächlich blockierenden Entscheidungen. Die weitere Implementierung erfolgt schrittweise. Der Originalautor und seine Arbeit sollen respektvoll gewürdigt werden.

Das öffentliche Repository ist `https://github.com/vgarcia007/froeling-bridge`. Überprüfte Projektänderungen werden auf `main` gesichert; betreiberspezifische Konfiguration und privater Kontext bleiben lokal. Der Checkout kann in einem beliebigen Arbeitsverzeichnis liegen.

## Aktuelle Phase und abgeschlossene Arbeit

- p4d-Referenz geklont und unverändert auf `4d1176c4a9081893e4c2cc27a535bb2bc4737d0a` festgelegt. Fork und Original-`master` zeigten beim Vergleich auf denselben Commit.
- Referenz als Submodul unter `reference/linux-p4d` registriert; Hauptbranch des neuen Projekts: `main`.
- README mit Ziel, aktuellem Reifegrad, Dank, Herkunft und Checkout-/Prüfanleitung angelegt.
- Protokoll, Menü-/Schreibabläufe und Referenz-Datenbank dokumentiert; [Einstieg](README.md).
- Offline-Prüfwerkzeug für Original-C++-Encoder/Decoder und acht synthetische Telegramme vorhanden.
- Python-Paket 0.1.0 unter `src/froeling_bridge` implementiert: Framing, typisierte Payloads, exklusive Transaktionen, Client, Simulator und Offline-CLI. Python >=3.9, keine externen Laufzeitabhängigkeiten. Installation per `pip install .`; Dokumentation: [Python-Kern](python-core.md).
- Leseoperationen für Status, Firmware/Zeit, Messwerte, I/O, Parameter, Discovery, Fehler und Zeitprogramme. Parameter-/Zeitprogrammänderungen nur gegen Simulator implementiert; striktes Nachlesen und keine automatischen Wiederholungen.
- Kein TTY-Transport, keine HTTP-API und kein DB-Adapter. Dieser Implementierungsschritt hat den Live-Server, die Live-DB und den Port nicht kontaktiert.
- Live-Datenbank am 16.10.2026 mit ausdrücklicher Nur-Lesen-Erlaubnis untersucht: Transaktion `READ ONLY`, ausschließlich SELECT/SHOW, abschließend ROLLBACK und Verbindung geschlossen.
- Lesender SSH-Abgleich durchgeführt: Quellcheckout `1bc324dc46296a6bd1f8bbeffe2527efe3da2446` / `0.10.2`, keine getrackten Änderungen; Binärdatei am Dienstpfad enthält `0.10.2-GIT1bc324d`. Prozessabbild und Prozess-Locale waren nicht direkt lesbar. Details: [Live-Server](live-server.md).
- Bereinigte Live-Schemastruktur und Unterschiede in [Live-Datenbankbefund](live-database.md) und [Schemasnapshot](live-schema.json) erfasst. Keine Produktivdaten geändert.

## Wichtigste Erkenntnisse

- COM1, 57.600 Baud, 8N1, Big-Endian-Words, eigene Byte-Maskierung und XOR-Prüfsumme.
- Messwerte (`30`) und Parameter (`55`) haben unterschiedliche Metadaten. Historienwerte sind bereits skaliert.
- Menüstruktur wird entdeckt; manche Darstellungen und Zeitprogrammzuordnungen sind in p4d fest codiert.
- Normaler Parameterschreibpfad: frische Abfragen → `39` → zwei Antworten → `55` nachlesen. Die fachliche Bedeutung der beiden Antworten muss durch echte Mitschnitte belegt werden.
- Zeitprogramme verwenden `42`/`43`/`50`, vier Intervalle und Zehn-Minuten-Schritte. Alter Handler kann nach Fehlern trotzdem DB und Erfolgsmeldung aktualisieren.
- DATETIME wird als lokale Hostzeit gespeichert; genaue Hostzeitzone nicht allein aus der SQL-Systemabkürzung ableiten.
- Live-Schema stimmt bei Namen, SQL-Typen und Primärschlüsselkennungen vollständig mit dem installierten 0.10.2-Dictionary überein. Es weicht vom jüngeren Referenzdictionary ab: `peaks.timemin/timemax` fehlen, `valuefacts.parameter` fehlt, `valuefacts.invert` und Tabelle `scripts` sind zusätzlich vorhanden. Ein Start des aktuellen p4d gegen die Alt-DB könnte sie verändern und ist nicht Teil der Freigabe.

## Zugriff, private Dateien und Grenzen

- `live-db.con` wurde vom Benutzer lokal angelegt und enthält DB-Zugangsdaten. Sie ist ignoriert; nicht ausgeben oder committen. Die Nur-Lesen-Beschränkung gilt auch in zukünftigen Sessions.
- `.local/live-db-inspection.json` enthält den privaten Rohbericht einschließlich begrenzter Beispielzeilen; er ist ignoriert und nicht Teil der Git-Sicherung.
- `.venv` enthält für die Untersuchung PyMySQL 1.1.2. Das ist ein lokales Hilfsmittel, keine getroffene Entscheidung zum Datenbanktreiber der Anwendung.
- `live-server-ssh.con` enthält den bereitgestellten SSH-Zugang und bleibt ignoriert. SSH ist nur für lesende Bestandsaufnahme freigegeben, nicht für Heizungsschreiben, Service-Neustarts oder Hoständerungen. Private Berichte und SSH-Hostschlüssel liegen unter `.local/`.
- Der Benutzer bestätigt den Adapter unter `/dev/ttyUSB0` auf dem Live-Server. Port nicht öffnen oder parallel zu p4d verwenden.
- Vorhandene Dateilog-Ausschnitte enthalten reale Empfangsframes, darunter gültige `0x39`-Frames bei fehlgeschlagenen Statusabfragen. Kein vollständiger Parameterschreibmitschnitt. Rohlogs bleiben lokal.
- Heizungsmodell, genaue Firmware und Locale des p4d-Prozesses sind noch unbekannt. Die Hostzeitzone ist als `Europe/Berlin` belegt; SSH-Shell-Locale nicht mit Prozess-Locale gleichsetzen.

## Prüfungen

- `PYTHONPATH=src python3 -m unittest discover -s tests -v`: 72 Tests für Codec, Payloads, simulierte Transaktionen, Ausfälle, Abbrüche, Konkurrenz und CLI bestanden.
- Normale Paketinstallation in der lokalen `.venv`, zusätzlich Wheel-Installation ohne Zusatzabhängigkeiten in einer frischen Umgebung und ausführbare Demo außerhalb des Checkouts geprüft. Ein Editable-Install mit deren altem pip funktioniert nicht; normaler Installationsweg ist dokumentiert.

- `python3 docs/tools/verify_protocol_examples.py`: acht synthetische Frames, 65.536 16-Bit-Muster mit beiden Vorzeicheninterpretationen und ungültige/abgeschnittene Escapes erfolgreich geprüft.
- 154 unveränderliche Quellverweise aus der ersten Bestandsaufnahme geprüft; zusätzliche relative Links bei Repository-Einrichtung geprüft.
- Referenzcheckout sauber. Live-Schemasnapshot enthält ausschließlich Strukturinformationen, keine Verbindungsdaten oder Datenzeilen.
- Sicherungsprüfung für jedes Arbeitspaket: lokalen Commit und Remote-Commit auf `origin/main` vergleichen. Den tatsächlichen Sicherungsstand über Git prüfen, nicht aus dieser Datei ableiten.

## Nächster sinnvoller Schritt

1. Den DB-Kompatibilitätsadapter gegen das bekannte 0.10.2-Schema und lokale Fixtures planen/implementieren; zunächst keine Live-Schreibanbindung. Danach API und modernes Menü darauf aufbauen.
2. Der Offline-Protokollkern ist vorhanden. Sein Default-Antwortprofil (Requestcode = Antwortcode, zwei 0x39-Antworten) ist ausdrücklich nur Simulation; echte Zuordnungen weiter anhand von Mitschnitten belegen.
3. Heizungsmodell/Firmware und eine vollständige reale Schreibfolge noch gesondert ermitteln. Dafür keinen Schreibversuch, keine Änderung der Logkonfiguration und kein paralleles Öffnen von COM1 eigenständig auslösen.
4. HTTP-/UI-Framework, Produktionsinstallation, Authentifizierung und Lizenz für neue Projektteile sind weiter offen. Der Standardbibliotheks-Kern trifft diese Entscheidungen nicht vorweg.

Die ausführliche Reihenfolge und die Befundliste stehen in [findings-and-next-steps.md](findings-and-next-steps.md). Entscheidungen werden in [decisions.md](decisions.md) fortgeführt.
