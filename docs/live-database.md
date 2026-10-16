# Lesender Abgleich mit der bestehenden Datenbank

Untersucht am 16.10.2026 mit ausdrücklicher Nur-Lesen-Erlaubnis des Benutzers. Grundlage sind das tatsächlich ausgelesene Schema und ein Vergleich mit dem [Referenzdictionary](database-compatibility.md).

## Durchführung und Grenzen

Die Verbindung lief mit `START TRANSACTION READ ONLY`. Ausgeführt wurden nur `SELECT` und `SHOW`; danach `ROLLBACK` und Schließen der Verbindung. Es wurden Metadaten aus `information_schema`, DDL und Indizes der Kern-Tabellen, wenige benannte Konfigurationswerte und begrenzte Sensor-/Menümetadaten gelesen. Die letzten fünf Messpunkte wurden ausschließlich über einen vorhandenen Zeitindex abgefragt. Keine Aggregation, kein vollständiger Historienscan und kein Start von p4d.

Die lokale Verbindungskonfiguration und der Rohbericht sind ignoriert. Der [bereinigte Schemasnapshot](live-schema.json) enthält Tabellennamen, Spalten, Typen, Schlüssel und strukturelle Indexdefinitionen. Er enthält keine Host-/Zugangsdaten, Messwerte, Benutzerdaten, individuellen Titel, Konfigurationswerte, Tabellenfüllstände oder Auto-Increment-Zähler.

Eine Read-only-Transaktion verhindert unsere Datenänderungen; der laufende p4d kann während der Beobachtung weiter schreiben. Die Bestandsaufnahme ist kein eingefrorenes Backup. Sie belegt weder eine genaue p4d-Version noch die Firmware der Heizung.

## Belegte Strukturunterschiede

| Bereich | Live-Bestand | Aktuelle Referenz | Folgerung |
| --- | --- | --- | --- |
| `samples` | Spaltennamen, SQL-Typen und zusammengesetzter Primärschlüssel entsprechen dem Dictionary | `(address,type,aggregate,time)`, `value FLOAT(14,2)` | gute Grundlage für Weiterführung; Werte- und Zeitsemantik weiterhin separat prüfen |
| `valuefacts.parameter` | fehlt | vorhanden | nicht voraussetzen und keine automatische Schemaerweiterung auslösen |
| `valuefacts.invert` | zusätzlich, `VARCHAR(1)` | nicht im aktiven Dictionary | Bedeutung anhand der Altversion untersuchen; erhalten |
| `peaks.timemin`, `peaks.timemax` | fehlen | vorhanden | vorhandene Extremwerte erhalten; zugehörige Zeitpunkte sind in diesen Spalten nicht verfügbar |
| `scripts` | zusätzliche Tabelle mit Metadaten eines älteren Funktionsbereichs | im Dictionary nur auskommentiert | erhalten; für die Kernkommunikation zunächst nicht verwenden |
| `menu`, `timeranges` | Spaltennamen, SQL-Typen und Primärschlüssel entsprechen dem Dictionary | Discovery-/Parametercache bzw. vier Intervalle | Struktur kompatibel; keine Aussage über Aktualität oder Firmwarezuordnungen |

Es fehlen gegenüber den aktiven Anwendungstabellen des Referenzdictionary keine Tabellen. Der Strukturvergleich wurde auf Namen, Typen und Primärschlüssel der Kern-Tabellen begrenzt; eine vollständige Gleichheit sämtlicher Default-, Constraint- oder Engineeigenschaften wird nicht behauptet. Die zusätzlichen Spalten und fehlenden Felder stehen explizit im Snapshot.

Die Live-Datenbank läuft in der MariaDB-10.11-Reihe. Für die Kern-Tabellen wurde InnoDB beobachtet. Der Datenbankzeichensatz ist `utf8mb3`; SQL-Session und globaler Zeitmodus stehen auf `SYSTEM`. Die gemeldete Systemzeitabkürzung bestätigt keine vollständige IANA-Zeitzone und ersetzt nicht den späteren Hostabgleich.

Die begrenzte Sensorstichprobe enthält mehrere Faktoren, auch andere als Zehnerpotenzen, und mehrere Datentypkennungen. Daher weder Faktor aus `digits` ableiten noch Vorzeichen pauschal annehmen. Die Menüstichprobe enthält außerdem Typen, die die aktuelle Referenz nicht benennt. Solche Einträge zunächst erhalten und als unbekannt behandeln.

## Konsequenzen für den nächsten Plan

- Ein schemaabhängiger Kompatibilitätsadapter ist erforderlich; keine automatische Migration auf den neuesten p4d-Stand.
- Die vorhandene `samples`-Struktur kann als konkretes Ziel für erste Tests auf einer separaten Kopie dienen.
- Vor Arbeiten an Metadaten, Peaks oder Alt-Skripten die tatsächlich installierte Version ermitteln.
- Die Bedeutung fehlender/zusätzlicher Spalten nicht allein aus ihrem Namen erschließen.
- Noch keine Tests mit Schreibzugriffen oder ein neuer Daemon gegen diese Live-Datenbank. Eine Datenbankkopie ist bisher nicht angelegt.
