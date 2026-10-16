# Aktueller Projektkontext

Zuletzt aktualisiert: 16.10.2026. Diese Datei ist der Einstieg für neue Sessions; technische Details stehen in den verlinkten Fachnotizen.

## Ziel und Zusammenarbeit

Der Benutzer betreibt Original-p4d bereits auf einem anderen Rechner. Er möchte eine einfacher installierbare Python-Variante mit einer richtigen API und einem modernen Menü zum Lesen und Schreiben von Heizungsparametern. Andere Webinterfacefunktionen haben geringe Priorität. Die vorhandene MariaDB samt Historie soll weitergeführt werden; p4d bleibt Rückfalloption.

Zunächst wurde ausdrücklich Analyse und Dokumentation vereinbart, kein Python-Heizungsprototyp. Die weitere Implementierung wird schrittweise gemeinsam geplant. Der Originalautor und seine Arbeit sollen respektvoll gewürdigt werden.

Das öffentliche Repository ist `https://github.com/vgarcia007/froeling-bridge`. Überprüfte Projektänderungen werden auf `main` gesichert; betreiberspezifische Konfiguration und privater Kontext bleiben lokal. Der Checkout kann in einem beliebigen Arbeitsverzeichnis liegen.

## Aktuelle Phase und abgeschlossene Arbeit

- p4d-Referenz geklont und unverändert auf `4d1176c4a9081893e4c2cc27a535bb2bc4737d0a` festgelegt. Fork und Original-`master` zeigten beim Vergleich auf denselben Commit.
- Referenz als Submodul unter `reference/linux-p4d` registriert; Hauptbranch des neuen Projekts: `main`.
- README mit Ziel, aktuellem Reifegrad, Dank, Herkunft und Checkout-/Prüfanleitung angelegt.
- Protokoll, Menü-/Schreibabläufe und Referenz-Datenbank dokumentiert; [Einstieg](README.md).
- Offline-Prüfwerkzeug für Original-C++-Encoder/Decoder und acht synthetische Telegramme vorhanden. Keine Python-Kommunikationsbibliothek implementiert.
- Live-Datenbank am 16.10.2026 mit ausdrücklicher Nur-Lesen-Erlaubnis untersucht: Transaktion `READ ONLY`, ausschließlich SELECT/SHOW, abschließend ROLLBACK und Verbindung geschlossen.
- Bereinigte Live-Schemastruktur und Unterschiede in [Live-Datenbankbefund](live-database.md) und [Schemasnapshot](live-schema.json) erfasst. Keine Produktivdaten geändert.

## Wichtigste Erkenntnisse

- COM1, 57.600 Baud, 8N1, Big-Endian-Words, eigene Byte-Maskierung und XOR-Prüfsumme.
- Messwerte (`30`) und Parameter (`55`) haben unterschiedliche Metadaten. Historienwerte sind bereits skaliert.
- Menüstruktur wird entdeckt; manche Darstellungen und Zeitprogrammzuordnungen sind in p4d fest codiert.
- Normaler Parameterschreibpfad: frische Abfragen → `39` → zwei Antworten → `55` nachlesen. Die fachliche Bedeutung der beiden Antworten muss durch echte Mitschnitte belegt werden.
- Zeitprogramme verwenden `42`/`43`/`50`, vier Intervalle und Zehn-Minuten-Schritte. Alter Handler kann nach Fehlern trotzdem DB und Erfolgsmeldung aktualisieren.
- DATETIME wird als lokale Hostzeit gespeichert; genaue Hostzeitzone nicht allein aus der SQL-Systemabkürzung ableiten.
- Live-Schema weicht vom Referenzdictionary ab: `peaks.timemin/timemax` fehlen, `valuefacts.parameter` fehlt, `valuefacts.invert` und Tabelle `scripts` sind zusätzlich vorhanden. Ein Start des aktuellen p4d gegen die Alt-DB könnte sie verändern und ist nicht Teil der Freigabe.

## Zugriff, private Dateien und Grenzen

- `live-db.con` wurde vom Benutzer lokal angelegt und enthält DB-Zugangsdaten. Sie ist ignoriert; nicht ausgeben oder committen. Die Nur-Lesen-Beschränkung gilt auch in zukünftigen Sessions.
- `.local/live-db-inspection.json` enthält den privaten Rohbericht einschließlich begrenzter Beispielzeilen; er ist ignoriert und nicht Teil der Git-Sicherung.
- `.venv` enthält für die Untersuchung PyMySQL 1.1.2. Das ist ein lokales Hilfsmittel, keine getroffene Entscheidung zum Datenbanktreiber der Anwendung.
- Kein SSH-Zugriff auf den Originalrechner vereinbart. DB-Zugang ersetzt keine Freigabe für Heizungsschreiben, Service-Neustarts oder Änderungen am Originalrechner.
- Keine realen seriellen Mitschnitte vorhanden. Heizungsmodell, genaue Firmware, installierte p4d-Version/Commit und Host-Locale sind noch unbekannt.

## Prüfungen

- `python3 docs/tools/verify_protocol_examples.py`: acht synthetische Frames, 65.536 16-Bit-Muster mit beiden Vorzeicheninterpretationen und ungültige/abgeschnittene Escapes erfolgreich geprüft.
- 154 unveränderliche Quellverweise aus der ersten Bestandsaufnahme geprüft; zusätzliche relative Links bei Repository-Einrichtung geprüft.
- Referenzcheckout sauber. Live-Schemasnapshot enthält ausschließlich Strukturinformationen, keine Verbindungsdaten oder Datenzeilen.
- Sicherungsprüfung für jedes Arbeitspaket: lokalen Commit und Remote-Commit auf `origin/main` vergleichen. Den tatsächlichen Sicherungsstand über Git prüfen, nicht aus dieser Datei ableiten.

## Nächster sinnvoller Schritt

1. Installierte p4d-Version und Hardware/Firmware ermitteln; dafür zunächst den Benutzer nach vorhandenen Informationen oder lesendem Hostzugriff fragen. Nicht aus dem DB-Schema eine genaue Versionsnummer behaupten.
2. Relevante Unterschiede gezielt gegen ältere p4d-Historie prüfen und den DB-Kompatibilitätsumfang konkret festlegen. Schema und Anwendungsversion getrennt behandeln.
3. Vorhandene echte Protokolllogs beschaffen, besonders eine vollständige Parameteränderung mit beiden Antworten und anschließendem Nachlesen. Noch keinen Schreibtest auslösen.
4. Danach den ersten Python-Protokollbaustein samt Simulator und Testfällen gemeinsam planen. API-/UI-Framework, Installation und Authentifizierung sind noch offen.

Die ausführliche Reihenfolge und die Befundliste stehen in [findings-and-next-steps.md](findings-and-next-steps.md). Entscheidungen werden in [decisions.md](decisions.md) fortgeführt.
