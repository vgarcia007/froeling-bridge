# API und kontinuierlicher Datensammler (0.2.0)

Der Dienst sammelt regelmäßig Werte vom **Simulator** und bietet eine lokale HTTP-API. Mit einer separaten Test-MariaDB werden diese Werte im bekannten p4d-0.10.2-Schema gespeichert. Die Bestandsansicht kann eine bestehende Datenbank ausschließlich lesen. Es gibt noch keinen USB-/TTY-Transport, keine produktive Heizungsanbindung und kein Browsermenü.

## Installation und Start

Python >=3.9. Der Protokollkern bleibt ohne externe Laufzeitabhängigkeiten; der Dienst verwendet Flask 3.1, Waitress 3 und PyMySQL 1.1 als optionales Extra. Flask 3.1 unterstützt Python >=3.9 ([Installation](https://flask.palletsprojects.com/en/stable/installation/)). DB-Verbindungen verwenden begrenzte Verbindungs-/Lese-/Schreibzeitlimits ([PyMySQL](https://pymysql.readthedocs.io/en/latest/modules/connections.html)).

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install '.[service]'
.venv/bin/froeling-bridge serve
```

Der Dienst läuft unter `http://127.0.0.1:8000`, ohne Debugger/Reload. Das Aufzeichnungsintervall beträgt 60 Sekunden; `--interval 5` und `--port 8001` ändern die lokalen Demo-Einstellungen. SIGINT/SIGTERM beenden den Dienst. Es gibt absichtlich keine Bindung an öffentliche Interfaces, kein Produktions-Authentifizierungsverfahren und keinen Zugriff auf `/dev/ttyUSB0`.

| Modus | Datenquelle | Aufzeichnung | Heizungsjobs |
| --- | --- | --- | --- |
| `demo` (Default) | fiktive Simulator-Metadaten | flüchtiger Speicher, höchstens 10.000 Messpunkte | Simulator |
| `demo-db --config DATEI` | separate lokale Test-MariaDB | `samples` und `peaks` der Test-DB | Simulator |
| `database --config DATEI` | bestehende p4d-MariaDB | keine; ausschließlich lesend | keine |

Die Modi vermischen keine Bestandsmenüadressen mit simulierten Heizungswerten. Verbindungsdateien werden niemals automatisch entdeckt. Die vorhandenen `live-*.con` werden weder eingelesen noch konvertiert.

## Separate Testdatenbank

Für einen reproduzierbaren Teststand, unabhängig von bestehenden DB-Containern:

```bash
docker run -d --rm --name froeling-bridge-test-db \
  -e MARIADB_ALLOW_EMPTY_ROOT_PASSWORD=1 \
  -p 127.0.0.1:33079:3306 mariadb:10.11
mkdir -p .local
```

Nach dem Start eine **lokale**, ignorierte Datei `.local/test-database.json` mit diesen fiktiven Testeinstellungen anlegen:

```json
{
  "host": "127.0.0.1",
  "port": 33079,
  "database": "froeling_bridge_test_demo",
  "user": "root",
  "password": ""
}
```

```bash
.venv/bin/froeling-bridge init-test-db --config .local/test-database.json
.venv/bin/froeling-bridge serve --mode demo-db \
  --config .local/test-database.json --interval 5
```

`init-test-db` legt ausdrücklich eine neue Testdatenbank mit `valuefacts`, `menu`, `samples`, `peaks` und rein synthetischen Metadaten an. Es lehnt vorhandene Tabellen ab. DDL ist in MariaDB nicht transaktional: Scheitert eine Initialisierung, kann eine unvollständige Testdatenbank verbleiben; der Dienst repariert sie nicht automatisch.

Schreiber und Initialisierung akzeptieren nur Loopback-Hosts und Namen `froeling_bridge_test_<name>` mit Kleinbuchstaben/Ziffern/Unterstrichen. Diese Begrenzung ist für den lokalen Prototyp bestimmt. Keine Produktivdaten unter einem solchen Testnamen bereitstellen. Es gibt keine automatische Migration, Discovery-Speicherung, Aggregation oder Löschung bestehender Historie.

Die Bestandsansicht verwendet dieselben JSON-Felder, darf aber einen anderen Host/DB-Namen lesen:

```bash
.venv/bin/froeling-bridge serve --mode database --config .local/database-view.json
```

Jede Leseoperation verwendet eine eigene `READ ONLY`-Transaktion mit abschließendem Rollback und serverseitigem Statement-Zeitlimit. Zugangsdaten und DB-Fehlermeldungen werden nicht ausgegeben. `health.database_available` ist bis zur ersten DB-Operation unbekannt (`null`), danach der zuletzt beobachtete Zustand; keine laufende Verbindungsprüfung.

## Datensammlung und Kompatibilität

Der Sammler startet sofort, danach mit monotoner Zeitplanung. Lange Durchläufe überspringen verpasste Intervalle; es gibt keine Überlappung oder Aufholbursts. Sensoren mit `state='A' OR record='A'` werden gelesen, nur `record='A'` wird gespeichert. Metadaten werden pro Durchlauf neu gelesen; Titel und Auswahlflags werden nicht geändert.

Unterstützt: `VA` mit Faktor und `res1`-Vorzeicheninterpretation; `DO`/`DI` als 0/1; `AO` als numerischer Zustand; `UD` 1 (Zustand), 2 (Betriebsart), 3 (Heizungszeit als Unix-Sekunden, lokale Steuerungszeit als Europe/Berlin interpretiert). Andere Typen, einschließlich `SD`-Zustandsdauern und Fremdintegrationen, werden sichtbar übersprungen. Die Reihenfolge von Lesen und Schreiben liegt bei einem gemeinsamen Heizungsworker. Benutzerjobs können zwischen zwei Sensorabfragen laufen, nicht innerhalb einer Parameteränderung.

Nur in diesem Durchlauf erfolgreich gelesene Werte werden gespeichert, auch unveränderte Werte. Fehler erzeugen Lücken; alte Cachewerte werden nicht erneut aufgezeichnet. Pro Durchlauf gilt ein gemeinsamer lokaler Speicherzeitpunkt mit Sekundenauflösung. `samples` verwendet `(address,type,'S',time)`, bereits skalierte Werte, `samples=1` und Unix-Sekunden in `inssp/updsp`. Historie wird beim Lesen nicht erneut skaliert. Die alte `FLOAT(14,2)`-Spalte behält ihre begrenzte Genauigkeit.

Schlüsselkonflikte aktualisieren Wert/Text/Anzahl und `updsp`; `inssp` bleibt erhalten. Damit bleibt auch die alte Einschränkung bei einer wiederholten lokalen Uhrzeit zur Sommerzeitumstellung bestehen: der zweite Messpunkt ersetzt denselben Schlüssel. Keine stillschweigende UTC-Umstellung. `peaks.minv/maxv` werden zusammen mit den Messpunkten transaktional gepflegt; die im Altbestand fehlenden Zeitspalten werden nicht benötigt.

DB-Fehler führen zu Rollback und sichtbarem Fehlerzustand. Es gibt keinen Nachlieferungspuffer und keine automatische Wiederholung eines möglicherweise bereits bestätigten Commits. Nachfolgende Sammelzyklen lesen neue Werte. Protokollfehler sperren die vorhandene Sitzung; der Dienst meldet dann weitere Fehler, statt einen unbelegten Hardware-Wiederanlauf zu erfinden.

## API und Beispiele

[OpenAPI-Vertrag](../src/froeling_bridge/openapi.json), zur Laufzeit unter `/api/v1/openapi.json`.

| Endpunkt | Inhalt |
| --- | --- |
| `GET /api/v1/health` | Modus, Worker, zuletzt beobachtete DB-Verfügbarkeit, Hardwareprüfung immer false |
| `GET /api/v1/collector` | Intervall, letzter Zyklus, letzte erfolgreiche Speicherung, Fehler und übersprungene Sensoren |
| `GET /api/v1/menu?parent=1` | Menüebene, lokale Zeilen-ID, Parent/Child, Typ, Adresse und Bearbeitbarkeit |
| `GET /api/v1/sensors` | Sensormetadaten, einschließlich Auswahlflags |
| `GET /api/v1/values` | letzte erfolgreich gelesene Simulatorwerte mit Quelle, Beobachtungszeit, Alter und `stale` |
| `GET /api/v1/history` | Historie für Adresse **und** Typ, Zeitbereich und Aggregat; maximal 1.000 Punkte |
| `POST /api/v1/jobs` | Auftrag annehmen, HTTP 202 und `Location` zum Abfragen |
| `GET /api/v1/jobs/{id}` | queued/running/completed/failed und Ergebnis oder strukturierter Fehler |

Bestandsansicht: `/values` und Heizungsjobs liefern HTTP 409. Gespeicherte Werte sind dort über `/history` verfügbar. Menüanzeigewerte sind ausdrücklich ein Cache, keine aktuellen Heizungswerte. Unbekannte Menütypen bleiben sichtbar, ohne Schreibfunktion. Die lokale Menü-ID ist keine stabile Heizungsadresse.

```bash
curl -s http://127.0.0.1:8000/api/v1/collector
curl -s 'http://127.0.0.1:8000/api/v1/menu?parent=10'
curl -s 'http://127.0.0.1:8000/api/v1/history?address=43&type=VA&start=2020-01-01T00:00:00&end=2030-01-01T00:00:00&aggregate=S&limit=100'
curl -s -H 'Content-Type: application/json' \
  -d '{"operation":"write_parameter","menu_id":2,"value":"67.5"}' \
  http://127.0.0.1:8000/api/v1/jobs
```

Die zurückgegebene URL anschließend per GET abfragen. Dezimalwerte werden als Dezimalzeichenketten transportiert; Boolesche Parameter als JSON-Booleans; Uhrzeiten als `HH:MM`. Für Zeitprogramme sind `index=0..3`, Zehn-Minuten-Schritte und entweder beide Endpunkte gesetzt oder beide `null` erforderlich. Die Parameterart wird serverseitig aus dem Menü bestimmt; frische Grenzen und Faktor werden unmittelbar vor dem Schreiben gelesen.

Joboperationen: `status`, `firmware`, `discover_menu`, `measurement`, `read_parameter`, `write_parameter`, `time_ranges`, `write_time_range`. `discover_menu` liefert eine vollständige Liste, ersetzt aber keine DB-Tabelle. Die genauen Eingabefelder stehen im OpenAPI-Vertrag. Fehlerhafte Eingaben liefern HTTP 400; Fehler erst während der Ausführung stehen im Job. Volle Warteschlange: HTTP 503.

Erfolgreiche Schreibresultate heißen `confirmed` oder `unchanged`. Fehler unterscheiden `verification_failed` mit tatsächlichem Nachlesewert und `outcome_unknown` mit Phase. Polling des Jobs führt keinen erneuten Schreibversuch aus. Eine erneute POST-Anfrage ist ein neuer Auftrag, keine idempotente Wiederholung.

Die Warteschlange fasst 64 Aufträge; maximal 1.000 Jobresultate bleiben im Speicher. Bei Platzbedarf werden abgeschlossene Resultate entfernt (danach HTTP 404). Neustarts verlieren diese Daten und führen keine Aufträge erneut aus. Authentifizierung, dauerhaftes Auftragsjournal und produktiver Betrieb folgen vor Freigabe einer realen Schreibanbindung.

Ein ausführbares Beispiel für alle wesentlichen API-Abläufe:

```bash
python3 docs/tools/exercise_api.py
```

## Prüfungen

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
FROELING_TEST_DB_CONFIG=.local/test-database.json \
  PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
python3 docs/tools/verify_protocol_examples.py
```

Ohne Service-Extra werden die HTTP-Tests übersprungen. Ohne ausdrücklich gesetzte Testkonfiguration werden die MariaDB-Integrationstests übersprungen. Diese legen eine weitere Testdatenbank mit zufälligem Namenssuffix im angegebenen lokalen Testserver an. Sie prüfen Schema, Aufzeichnung, Sensoridentität, Zeitkollisionen, Peaks, Rollback und serverseitigen Read-only-Schutz. Den eigens gestarteten Testcontainer nach dem Test entfernen:

```bash
docker stop froeling-bridge-test-db
```

Reale Schreibmitschnitte sind zusätzliche spätere Validierung. Der Quellcode von p4d reicht als Grundlage für diese Implementierung; die kaputte alte Weboberfläche blockiert sie nicht. USB-Transport, kontrollierter Livewechsel, Aggregation/Aufbewahrung und das moderne Browsermenü bleiben die nächsten Arbeitspakete.
