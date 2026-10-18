# Anlagenübersicht ab 0.6.0

Die eigene Seite `/anlage` stellt zusammengehörige Temperaturen, Betriebszustände, Pumpen und Einstellungen dar. Sie ergänzt das Servicemenü und verwendet dieselbe API und denselben seriellen Besitzer. Die Ansicht ist eine **Funktionsübersicht aus dem Menü**, kein Rohrleitungsplan. Das frühere p4d-Schemabild wird nicht übernommen.

## Was die Seite zeigt

- Gruppen für Kessel, Puffer, Boiler und Heizkreise mit den Namen und Menüpfaden der Steuerung.
- Isttemperaturen mit passendem Sollwert in kleiner Schrift direkt darunter, außerdem Ladezustände und andere zugeordnete Messwerte mit Lesezeitpunkt. Die Paarung bleibt innerhalb derselben Geräteinstanz: Vorlauf Ist/Soll, Abgas Ist/Soll, Boiler oben/gewünschte Boilertemperatur. Beim Kessel hat der berechnete Sollwert Vorrang vor der festen Kessel-Solltemperatur. Ohne eindeutiges Gegenstück wird kein Sollwert erfunden; Mindest-/Maximalwerte, Frostschutz und Pufferschwellen dienen nicht als Ersatz. Veraltete Sollwerte werden gekennzeichnet.
- Pumpen- und Mischerausgänge als angesteuert/nicht angesteuert; bei Prozentwerten zusätzlich eine Anzeige der Ansteuerung. Das ist keine gemessene Fördermenge oder bestätigte mechanische Drehzahl.
- Aufklappbare Sollwerte und Schaltbedingungen. Beim Öffnen werden fehlende oder mehr als zehn Minuten alte Parameter automatisch lesend aktualisiert. Ein eigener Knopf erlaubt bewusstes erneutes Lesen. Fehlende/veraltete Einstellungen, die als kleiner Sollwert direkt am Messwert gebraucht werden, werden auch ohne Öffnen des Detailbereichs über denselben geteilten Leseauftrag aktualisiert.
- Nicht eindeutig zugeordnete Pumpen und Mischer in einem separaten Abschnitt. Fehlende/veraltete Werte und mehrdeutige Zuordnungen zeigen einen unbekannten Zustand statt einer laufenden Pumpe.

Die Seite aktualisiert ihren API-Stand alle vier Sekunden. Bei einem Verbindungsabbruch bleiben die letzten Werte sichtbar, Animationen enden und Pumpenzustände werden unbekannt. Die Animation steht für eine frische positive Ansteuerung. Sie bildet keinen Wasserstrom ab. Schwellen allein erklären die Regelung nicht vollständig; Betriebsart, Zeitprogramme und weitere Freigaben können ebenfalls wirken. Die erste Version führt keine Parameteränderungen aus; dafür bleibt das Servicemenü zuständig.

## Wie die Zuordnung entsteht

Die Bridge verfolgt die erreichbare Menüstruktur. Sie erkennt Hauptgruppen und Geräteinstanzen anhand ihrer p4d-Typen `0x01` und `0x21` und der Gerätenamen. Gleichnamige Sensoren verschiedener Boiler bleiben durch ihre jeweiligen Gerätepfade getrennt. Instanzspezifische Untermenüs kommen aus der Steuerung; es gibt keine Liste fest angenommener Sensoradressen. Untermenüs für Display-Bedienrechte werden nicht als weitere Kessel ausgegeben.

Messwert-/I/O-Menüeinträge werden mit den vorhandenen Metadaten über Typ und Adresse verbunden. Mehrfachzuordnungen werden ausdrücklich als mehrdeutig markiert; gemeinsam verwendete Außentemperaturen dürfen in mehreren Gruppen erscheinen. Der globale Kesselstatus wird nur bei genau einer erkannten Kesselgruppe dieser Gruppe zugeordnet. Die Zuordnung beweist weder tatsächlichen Einbau noch die Verrohrung. Insbesondere werden allgemeine Pumpenausgänge nicht anhand ähnlich klingender Namen einem Heizkreis zugewiesen.

## Zusätzlich benötigte Messwerte

Die Seite zeigt, wie viele ihrer eindeutig zugeordneten und unterstützten Messwerte bislang nicht zur Abfrage ausgewählt sind. **„Zusätzliche Messwerte abfragen“** aktiviert diese über denselben Konfigurationspfad wie die Sensorübersicht. Die Historienauswahl bleibt unverändert. Bereits zur Aufzeichnung ausgewählte Werte werden ohnehin gelesen und benötigen keine zusätzliche Aktivierung.

Ein Seitenaufruf oder ein GET ändert keine Flags. Die Aktivierung ist eine ausdrückliche POST-Aktion. Sie ist wiederholbar; bei einem Teilfehler kann sie erneut ausgeführt werden. Die Einstellungen bleiben lokal erhalten und werden über den vorhandenen Historienworker mit `valuefacts` synchronisiert. Neue Werte erscheinen mit dem nächsten normalen Sammeldurchlauf; Standard sind 60 Sekunden. Nach einer späteren Änderung des Katalogs können weitere Messwerte zur Aktivierung angeboten werden.

## API

### Übersicht lesen

```http
GET /api/v1/plant
```

Die Antwort enthält `components`, `unassigned`, `enabled`, `activation_available` und `additional_sensors`. Jede Komponente enthält `id`, `kind`, `title`, `path`, `metrics`, `settings` und einen gegebenenfalls laufenden `refresh_job_id`.

Ein Messwert enthält den vollständigen Sensor einschließlich `latest`, eine Rolle wie `pump` oder `temperature` und die belegte Zuordnung. Für Parameter gelten eigene Lesezeitpunkte, Alter, `stale` und `error`. `presence=menu-catalogue` bedeutet im Menü gefunden, nicht physisch eingebaut. Komponentenkennungen immer aus dieser Antwort übernehmen und nach erneuter Discovery neu auflösen.

Der GET löst **weder Heizungsabfragen noch Aktivierung** aus. Die Freshness-Regeln der Sensoren entsprechen `/sensors`. Ein in SQLite gespeicherter Wert nach Neustart bleibt bis zum frischen Lesen veraltet.

### Zusätzliche Messwerte aktivieren

```http
POST /api/v1/plant/activate
Content-Type: application/json

{}
```

Die Antwort nennt die tatsächlich aktivierten Sensoren und `history_selection_changed=false`. Verfügbar nur mit einem konfigurierbaren lokalen Katalog. Eine leere/unvollständige Erkennung wird abgewiesen; ältere Bestandsansichten und die lesende Vorschau dürfen nicht aktiviert werden.

### Einstellungen einer Komponente lesen

```http
POST /api/v1/jobs
Content-Type: application/json

{"operation":"refresh_component","component_id":"KENNUNG-AUS-PLANT"}
```

HTTP 202 und `Location` funktionieren wie bei vorhandenen Jobs. Das Ergebnis enthält `component_id`, `read` und `errors`; einzelne Lesefehler stehen ausdrücklich in `result.errors`, auch wenn der Sammelauftrag abgeschlossen wurde. Danach `/plant` erneut lesen. Alte erfolgreiche Werte behalten bei einem Fehler ihren ursprünglichen Zeitstempel.

Parallele Aktualisierungen derselben Komponente teilen einen Auftrag; maximal vier Komponenten werden gleichzeitig aktualisiert. Die Orchestrierung läuft außerhalb des seriellen Workers und reicht jede Parameterabfrage einzeln ein, damit reguläre Messungen dazwischen ausgeführt werden. Ein Stapel hat 90 Sekunden Zeitbudget. Bei Protokollfehler, voller Warteschlange oder Dienstende endet dieser Stapel; keine Heizungs-Schreibbefehle und keine automatischen Wiederholungen. Die Oberfläche wartet nach einem fehlgeschlagenen automatischen Versuch mindestens 60 Sekunden auf einen weiteren Versuch.

Erfolgreiche Parameterbeobachtungen liegen mit Zeitstempel im SQLite-Metadatenbereich, ohne neue Tabellen oder MariaDB-Migration. Erfolgreiches Lesen beziehungsweise verifiziertes Schreiben im Servicemenü aktualisiert auch den zugehörigen Übersichtscache.

Vollständiger Vertrag: [OpenAPI](../src/froeling_bridge/openapi.json).

## Separate Vorschau

Die produktive Bridge muss für diese Vorschau nicht beendet oder ersetzt werden. Aus dem Checkout mit installiertem Service-Extra:

```bash
PYTHONPATH=src .venv/bin/python docs/tools/preview_plant.py --simulate-only
```

Die Vorschau liegt unter `http://VORSCHAU-RECHNER:8001/anlage`. Sie enthält ausschließlich fiktive Geräte und Werte. Parameterlesevorgänge lassen sich simuliert prüfen; die Fixture öffnet keinen echten Adapter und verwendet keine MariaDB. Der erste simulierte Messdurchlauf wird beim Start erfasst; die Werte altern danach sichtbar. Beenden mit Strg+C beendet nur diesen Vorschauprozess.

Für eine strikt lesende Vorschau mit vorhandenen API-Daten:

```bash
PYTHONPATH=src .venv/bin/python docs/tools/preview_plant.py \
  --source-snapshot /geschuetzt/katalog-snapshot.json \
  --source-url http://HEIZUNGSRECHNER:8000
```

Der private JSON-Snapshot enthält `menu` als vollständige Menüliste und `sensors.items` als Sensorliste; beide dürfen alternativ unter `out` eines erfolgreichen Inspektionsberichts liegen. Der Snapshot muss aus dem eigenen, zuvor lesend geprüften Katalog stammen. Er wird ausschließlich in einen temporären Vorschaukatalog kopiert und bleibt außerhalb des Repositorys.

`--source-url` liest ausschließlich `GET /api/v1/sensors` der laufenden Bridge, mit gemeinsamem kurzem HTTP-Cache. POST/PATCH/DELETE werden in der Vorschau abgewiesen. Sie öffnet keinen seriellen Adapter, ruft keine Heizungsjobs ab und ändert keine Auswahlflags. Schwellwerte, die die alte API noch nicht im Übersichtscache bereitstellt, bleiben dort unbekannt. Ohne `--source-url` zeigt die Vorschau nur den Snapshot und kennzeichnet dessen Werte als gespeichert/veraltet. Produktive Aktivierung und zusätzliche Abfragen sind ein eigener Rollout.

## Prüfungen

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_plant tests.test_api -v
PYTHONPATH=src .venv/bin/python docs/tools/verify_plant_browser.py --simulate-only
```

Die Browserprüfung verwendet ausschließlich fiktive Hardware. Sie prüft direkte URL und Navigation, vier Displaybreiten, automatische Parameterlesevorgänge, aktive/veraltete Pumpen, sichere Textdarstellung und eine strikt lesende API-Vorschau. Parameter- und Zeitprogramm-Schreibzähler müssen null bleiben.
