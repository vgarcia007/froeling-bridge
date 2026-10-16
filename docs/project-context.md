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
- In Version 0.2.0: lokale HTTP-API (Flask 3.1/Waitress 3), DB-Adapter (PyMySQL 1.1), kontinuierlicher Sammler und Test-DB-Initialisierung ergänzt. Optionales Extra `.[service]`; Protokollkern weiterhin ohne Zusatzabhängigkeiten. In 0.3.0 sind auch Linux-TTY-Transport und modernes Browsermenü implementiert; siehe Ergänzung unten. Der reale Hardwaretest steht aus. Dieser Implementierungsschritt hat Live-Server, Live-DB und Port nicht kontaktiert.
- Live-Datenbank am 16.10.2026 mit ausdrücklicher Nur-Lesen-Erlaubnis untersucht: Transaktion `READ ONLY`, ausschließlich SELECT/SHOW, abschließend ROLLBACK und Verbindung geschlossen.
- Lesender SSH-Abgleich durchgeführt: Quellcheckout `1bc324dc46296a6bd1f8bbeffe2527efe3da2446` / `0.10.2`, keine getrackten Änderungen; Binärdatei am Dienstpfad enthält `0.10.2-GIT1bc324d`. Prozessabbild und Prozess-Locale waren nicht direkt lesbar. Details: [Live-Server](live-server.md).
- Bereinigte Live-Schemastruktur und Unterschiede in [Live-Datenbankbefund](live-database.md) und [Schemasnapshot](live-schema.json) erfasst. Keine Produktivdaten geändert.

## Wichtigste Erkenntnisse

- COM1, 57.600 Baud, 8N1, Big-Endian-Words, eigene Byte-Maskierung und XOR-Prüfsumme.
- Messwerte (`30`) und Parameter (`55`) haben unterschiedliche Metadaten. Historienwerte sind bereits skaliert.
- Menüstruktur wird entdeckt; manche Darstellungen und Zeitprogrammzuordnungen sind in p4d fest codiert.
- Normaler Parameterschreibpfad: frische Abfragen → `39` → zwei Antworten → `55` nachlesen. Die fachliche Bedeutung der beiden Antworten ist offen; spätere Mitschnitte können sie zusätzlich belegen, sind aber keine Voraussetzung für die Implementierung.
- Zeitprogramme verwenden `42`/`43`/`50`, vier Intervalle und Zehn-Minuten-Schritte. Alter Handler kann nach Fehlern trotzdem DB und Erfolgsmeldung aktualisieren.
- DATETIME wird als lokale Hostzeit gespeichert; genaue Hostzeitzone nicht allein aus der SQL-Systemabkürzung ableiten.
- Live-Schema stimmt bei Namen, SQL-Typen und Primärschlüsselkennungen vollständig mit dem installierten 0.10.2-Dictionary überein. Es weicht vom jüngeren Referenzdictionary ab: `peaks.timemin/timemax` fehlen, `valuefacts.parameter` fehlt, `valuefacts.invert` und Tabelle `scripts` sind zusätzlich vorhanden. Ein Start des aktuellen p4d gegen die Alt-DB könnte sie verändern und ist nicht Teil der Freigabe.

## Zugriff, private Dateien und Grenzen

- `live-db.con` wurde vom Benutzer lokal angelegt und enthält DB-Zugangsdaten. Sie ist ignoriert; nicht ausgeben oder committen. Die Nur-Lesen-Beschränkung gilt auch in zukünftigen Sessions.
- `.local/live-db-inspection.json` enthält den privaten Rohbericht einschließlich begrenzter Beispielzeilen; er ist ignoriert und nicht Teil der Git-Sicherung.
- `.venv` enthält für die Untersuchung PyMySQL 1.1.2. Das ist ein lokales Hilfsmittel, keine getroffene Entscheidung zum Datenbanktreiber der Anwendung.
- `live-server-ssh.con` enthält den bereitgestellten SSH-Zugang und bleibt ignoriert. Die ursprüngliche reine SSH-Bestandsaufnahme ist inzwischen um den ausdrücklich beauftragten, vorbereiteten 15-Minuten-Lesetest erweitert: privates Paket bereitstellen, einmalige Einrichtung durch den Benutzer, danach feste Helferaktionen. Keine Heizungsparameter ändern und keine Originaldatenbank schreiben. Private Berichte und SSH-Hostschlüssel liegen unter `.local/`.
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

## Vorbereiteter manueller Logvergleich

Der Benutzer hat angeboten, über die alte Installation selbst einen Parameter zu ändern, kann den Versuch aktuell aber wegen der gestörten alten Weboberfläche nicht durchführen. Der Schreibversuch ist daher vorerst ausgesetzt. Ein lesender Ausgangsstand des aktiven Dateilogs liegt lokal unter `.local/write-capture-before.json` (Dateigröße, Inode und begrenzter Logauszug). Es wurde kein Schreibbefehl durch Fröling Bridge gesendet und keine Logstufe geändert. Der Versuch ist noch nicht als durchgeführt oder erfolgreich belegt.

Nach Rückmeldung des Benutzers die seit dieser Baseline angehängten Logbytes begrenzt lesen und gegebenenfalls Rotation berücksichtigen. Die Baseline vorher nicht überschreiben. Für die Zuordnung werden Parametername/Adresse, alter und neuer Wert sowie Zeitpunkt und die Anzeige der alten Installation benötigt. Ob die vorhandene Logstufe eine vollständige Telegrammfolge liefert, ist offen. Rohdaten und konkrete Betriebswerte bleiben lokal; nur bereinigte Protokollbefunde tracken. Das manuelle Testangebot erteilt keine Freigabe für eigene Schreibbefehle, Portzugriffe oder Änderungen am Live-Dienst.

## Lesende Prüfung der alten Weboberfläche

Die HTML-Seite und alle 42 lokal eingebundenen JS-/CSS-Dateien liefern am Server HTTP 200. Ein WebSocket-Upgrade mit Subprotokoll `p4d` ergibt HTTP 101; es wurden keine Anwendungsnachrichten, Anmeldung oder Heizungsbefehle gesendet. Die zentralen Dateien `main.js`, `menu.js`, `websocket.js`, `const.js`, `setup.js` stimmen mit 0.10.2 überein und bestehen eine lokale JavaScript-Syntaxprüfung. Im begrenzten neuen Logbereich wurden keine passenden Rechte-, Anmelde-, SQL-, Statuskommunikations- oder langen Loop-Fehler gefunden.

Das belegt keinen funktionierenden Browserablauf oder WebSocket-Nachrichtenaustausch. Der Benutzer hat das Fehlerbild inzwischen geliefert: wiederholtes Öffnen und Reconnects beim Navigieren, teilweise erfolgreiche Systemdaten-Antworten, Verschärfung nach `initmenu`, Verbindungsabbruch vor vollständig aufgebauter Verbindung und eine nicht näher bezeichnete Exception an `websocket.js:44`. Keine Server-/DB-Konfiguration geändert; Rohberichte `.local/live-web-inspection.json` und `.local/web-followup.json` bleiben lokal. Die gespeicherte Logauswahl heißt `Debug,`; daraus keinen vollständigen Debug2-Telegrammmitschnitt zusagen.

Der installierte Browser-Watchdog erzwingt nach vier Sekunden ohne Anwendungs-Ping einen Reconnect. Diese Pings entstehen in derselben Daemon-Schleife, die Clientanfragen und `initmenu` synchron ausführt. Verzögerte Pings bei langen seriellen Aufrufen sind daher eine konkrete, zum Verlauf passende Erklärung; keine abschließende Diagnose aller Abbrüche. Der direkte JS-Sendepfad prüft außerdem keinen `readyState`. Details und alte Quellstellen: [Live-Server-Abgleich](live-server.md#ergänzung-browserbefund-und-reconnect-schleife).

Der Benutzer hat klargestellt: Ein realer Schreibmitschnitt ist zusätzliche spätere Validierung, keine Voraussetzung für die quellenbasierte Implementierung. Die alte Weboberfläche blockiert die Entwicklung nicht.

Der Benutzer unterstreicht, dass dieses Verhalten ein Grund für den Neubau ist. Kein weiteres Debug-/Reparaturprojekt am alten Webinterface daraus machen. Für den Neubau festhalten: unabhängige API/Verbindungsüberwachung, Cache mit Aktualitätsangabe, lange Aufgaben als Jobs, ein kontrollierter Reconnectpfad und keine automatische Wiederholung von Schreibaufträgen.

## Nächster sinnvoller Schritt

1. DB-Adapter, lokale API und kontinuierliche Simulator-Aufzeichnung sind umgesetzt; Bedienung und Betriebsarten stehen in [service.md](service.md). Webmenü und exklusiver TTY-Transport sind ebenfalls implementiert. Nächster Schritt: einmalige administrative Hosteinrichtung und tatsächlicher 15-Minuten-Lesetest mit Rückkehr. Vor vollständiger Ablösung Aggregation/Aufbewahrung und Rückkehr zu p4d klären.
2. Der Offline-Protokollkern ist vorhanden. Sein Default-Antwortprofil (Requestcode = Antwortcode, zwei 0x39-Antworten) ist ausdrücklich nur Simulation; echte Zuordnungen weiter anhand von Mitschnitten belegen.
3. Heizungsmodell/Firmware und eine vollständige reale Schreibfolge noch gesondert ermitteln. Dafür keinen Schreibversuch, keine Änderung der Logkonfiguration und kein paralleles Öffnen von COM1 eigenständig auslösen.
4. Flask 3.1/Waitress 3 und PyMySQL 1.1 sind für den lokalen API-Prototyp gewählt. Webmenü verwendet paketiertes HTML/CSS/JavaScript. Produktionsinstallation, Authentifizierung und Lizenz für neue Projektteile sind weiter offen. Der Standardbibliotheks-Kern trifft diese Entscheidungen nicht vorweg.

Die ausführliche Reihenfolge und die Befundliste stehen in [findings-and-next-steps.md](findings-and-next-steps.md). Entscheidungen werden in [decisions.md](decisions.md) fortgeführt.


## Fortschritt: Datensammler und API 0.2.0

- Benutzer hat den erweiterten Plan ausdrücklich zur Umsetzung freigegeben, einschließlich kontinuierlichem Einsammeln und kompatiblem Speichern. Live-Zugriffsgrenzen bleiben bestehen.
- Betriebsarten: `demo` (Simulator/flüchtiger Speicher), `demo-db` (Simulator/separate lokale Test-MariaDB), `database` (Bestandsansicht, ausschließlich lesend). Keine automatische Verwendung der lokalen `live-*.con`.
- CLI `serve` startet Waitress auf 127.0.0.1:8000. Standardintervall 60 Sekunden, Sammler startet sofort. Einzelner Heizungsworker, begrenzte FIFO, separate Sammler-/DB-Arbeit; API bleibt während langer Vorgänge erreichbar.
- Aufzeichnung unterstützt VA, DO/DI/AO und UD 1–3. Auswahl aus valuefacts; nur erfolgreich frisch gelesene record=A-Werte speichern, inklusive unveränderter Werte. samples und peaks gemeinsam transaktional, bestehende Schlüssel, Skalierung und lokale Zeit erhalten. Keine Aggregation oder historische Löschung.
- Schreiber/Initialisierung ausschließlich für Loopback und `froeling_bridge_test_<name>`. Bestandsansicht nutzt Read-only-Transaktionen, Rollback und begrenzte Abfragen. Synthetischer Schemaausschnitt paketiert; keine Startup-Migration.
- Versionierte API für Health, Sammlerstatus, Menü, Sensoren, Cachewerte, Historie und asynchrone Heizungsjobs. Auftragsergebnisse flüchtig, keine automatische Wiederholung von Schreibaufträgen. OpenAPI liegt im Paket; Beispiele in der Dienstanleitung und `docs/tools/exercise_api.py`.
- Integrationsprüfung gegen einen ausschließlich für dieses Arbeitspaket gestarteten lokalen MariaDB-10.11-Dockercontainer. Zugangsdaten und Testberichte bleiben in .local; keine produktiven Verbindungen.
- Geprüft: 109 Tests einschließlich HTTP und sechs realer MariaDB-Integrationstests sowie weiterhin Original-C++-Vektoren. Zusätzlich: Wheel mit Service-Extra in frischer Umgebung installiert, Tests gegen das installierte Paket bestanden (sechs DB-Tests dort bewusst übersprungen); echtes HTTP samt Beispiel-Schreibjobs, OpenAPI und fortlaufender Test-DB-Speicherung außerhalb des Checkouts geprüft. SIGTERM beendet den Dienst sauber. Testcontainer anschließend entfernt. Git-Sicherungsstand bei Sessionbeginn stets separat prüfen.


## Fortschritt: Webmenü und vorbereiteter Hosttest 0.3.0

- Benutzer beauftragt erweiterten Plan zur Umsetzung. Er wählt für den ersten Wechsel ausschließlich Lesen/Aufzeichnen in separater Test-DB und einmalige administrative Einrichtung durch ihn. Keine neue Freigabe für Heizungs-Schreiben oder Original-DB-Schreiben.
- Webmenü unter `/`: responsive Navigation/Breadcrumbs, globale Suche, frische Parameterwerte, bestätigte Demo-Änderungen, Bool/Zahlen/Uhrzeit, vier Zeitintervalle, Messwerte und Sammlerstatus. Keine separaten Frontend-Abhängigkeiten.
- Hardware-read nutzt explizit Linux-TTY mit 57600/8N1, flock/TIOCEXCL, Deadlines und Wiederherstellung beim Schließen. Kein automatisches Leeren. Mehrfache Schreibsperre: API/Dienst, Client, vollständige Frameprüfung vor physischer Übertragung einschließlich Payload-Längen.
- Hardwaretest liest Originalmetadaten ausschließlich über ReadOnlyDatabase und schreibt samples/peaks in jeweils frische separate Test-DB. Status/Firmware zuerst, Protokoll-/DB-Fehler oder Zyklus über 120 Sekunden beenden den Prozess. API meldet Fähigkeiten und Quellen; Hardware-Schreiben bleibt gesperrt.
- Hostvorprüfung nur lesend: Python 3.12, Docker vorhanden, p4d active/enabled, USB-Gerät vorhanden, Port 8000 frei. Konkrete Zugriffsrechte bleiben privat; die Einrichtung/Testdurchführung erfordert passende administrative Rechte.
- Geprüfte Einrichtung unter deploy: eigene Umgebung/Benutzer/Test-MariaDB, root-eigener Helfer mit festen Aktionen, Simulator-Port 8000 und Test-Port 8001 auf Loopback. Rückkehrtimer vor p4d-Stop; eigener Testdienst mit OnFailure/RuntimeMaxSec, kein Hardware-Autostart. Originaldateien und Autostart bleiben erhalten.
- Root-Helferstatus privat; Rückkehr stoppt Testdienst vor p4d-Start und prüft neue Originalmesspunkte bis 90 Sekunden. Bei fremdem Portbesitzer kein paralleler Start. Testberichte und begrenzte Rohspuren bleiben privat. Symlinks in unprivilegierten Berichten werden nicht verfolgt.
- Lokal geprüft: 133 Tests einschließlich separater MariaDB, Browserabläufe in Chromium mit mobiler Darstellung, Pseudo-Terminal-Gesamttest mit tatsächlichen seriellen Bytes/HTTP/DB und absichtlichem Antwortausfall; unabhängige Rückkehr und SIGKILL-Fall mit echten systemd-Ersatzdiensten. Original-C++-Prüfvektoren weiterhin erfolgreich.
- Reproduzierbare Anleitung: host-test.md; Vorbereitung/Staging über docs/tools/prepare_host_test.py, lokaler opt-in Ersatzdiensttest über docs/tools/verify_host_rollback.py.
- Tatsächlicher Hosttest noch nicht durchgeführt. Ein geprüftes privates Einrichtungspaket wird nach Commit der Quellen bereitgestellt; administrativer Schritt bleibt ausstehend. Sicherungs-/Übertragungsstand anschließend separat prüfen.
