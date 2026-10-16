# Datenbankkompatibilität

## Gewünschte Kompatibilität und Referenz

Die neue Anwendung soll die bestehende MariaDB samt Historie weiterführen; p4d bleibt als Rückfalloption erhalten. Dauerhafter Parallelbetrieb zweier Heizungslogger ist nicht das vereinbarte Ziel. Kompatibilität bedeutet nicht nur gleiche Tabellennamen, sondern gleiche Sensoridentität, Skalierung, Zeitsemantik und Aggregatkennungen. Änderungen am produktiven Schema wurden nicht durchgeführt.

Das Schema ist in `configs/database.dat` als eigenes Dictionary beschrieben, nicht als fertiger SQL-Dump. `lib/dbdict` übersetzt es in SQL, `lib/db` kann Tabellen erstellen und Strukturen ändern. Deshalb ist das **tatsächliche DDL der laufenden Installation** vor einer Implementierung zu vergleichen. Quellen: [configs/database.dat:20](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/configs/database.dat#L20) [lib/dbdict.c:52](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/lib/dbdict.c#L52)] [lib/dbdict.h:178](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/lib/dbdict.h#L178) [lib/db.c:878](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/lib/db.c#L878).

## Tabellen und Zuständigkeiten

| Tabelle | Identität laut Dictionary | Inhalt und relevanter Schreibpfad |
| --- | --- | --- |
| `valuefacts` | `(address, type)` | Sensormetadaten, Faktor, Einheit, Name, Titel, Auswahl, Datentyp. `P4d::initValueFacts` / `Daemon::addValueFact` und IO-Setup |
| `valuetypes` | `type` | Bezeichnung der Sensortypen; `addValueFact` ergänzt fehlende Typen |
| `samples` | `(address, type, aggregate, time)` | Messwerthistorie; `storeSamples` / `store` und Aggregation |
| `peaks` | `(address, type)` | Min/Max und zugehörige Zeitpunkte; `Daemon::store` |
| `menu` | `id` auto increment | Heizungsmenü, Parameterdarstellung, Grenzen, Faktor, unbekannte Felder; `initMenu`, `updateParameter`, `performParStore` |
| `timeranges` | `address` | vier von/bis-Paare als Zeichenketten; `updateTimeRangeData`, `performTimeParStore` |
| `config` | `(owner, name)` | Anwendungskonfiguration; allgemeine Konfigurationsfunktionen |
| `errors` | `id` auto increment | Fehlernummer, Zustand, Texte, gekommen/gegangen/quittiert; `updateErrors` sucht fachlich nach Nummer + Anfangszeit |
| `groups` | `id` auto increment | Sensorgruppennamen; vorhandene Zuordnungen erhalten |
| `states` | `(address, type)` | gespeicherte Zustände auch anderer Integrationen; nicht ungeprüft als aktueller Heizungswert interpretieren |
| `users` | `user` | alte Anmeldung, Token und Rechtebits; keine automatische Übernahme als neues Authentifizierungsverfahren |
| `dashboards`, `dashboardwidgets`, `schemaconf` | ID bzw. zusammengesetzte Schlüssel | bestehende UI-Konfiguration, erhalten, für das erste Servicemenü nicht nachbauen |
| `sensoralert` | `id` auto increment | Alarmregeln, für den Kernumfang nicht erforderlich |
| `homematic`, `deconzs`, `deconzl` | address bzw. ID | andere Integrationen, erhalten, nicht vom neuen Heizungslogger schreiben |
| `pellets` | `id` auto increment | manuelle Liefer-/Verbrauchsdaten, erhalten |
| `information_schema.TABLES` | keine Primary-Deklaration | Dictionary-Zugriff für DB-Statistik; keine eigene Anwendungstabelle anlegen |

Vollständige Dictionary-Definition: [configs/database.dat:6](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/configs/database.dat#L6). Kernpfade: [specific.c:2154](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/specific.c#L2154) [daemon.c:3015](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/daemon.c#L3015) [daemon.c:2151](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/daemon.c#L2151) [specific.c:894](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/specific.c#L894) [specific.c:1163](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/specific.c#L1163).

## Sensoridentität und Auswahl

Die Adresse allein genügt nicht: `VA:0x0001`, `DO:0x0001` und `UD:0x0001` sind unterschiedliche Reihen. Für Heizungsdaten verwendet p4d `VA` (Messwert), `DO`/`DI` (Digitalausgang/-eingang), `AO` (Analogausgang), `UD` (abgeleitete Zustands-/Zeitwerte) und `SD` (Zustandsdauer). `UD` enthält Adresse 1 für Zustand, 2 für Betriebsart und 3 für Heizungszeit. Quellen: [specific.c:402](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/specific.c#L402) [service.h:134](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/service.h#L134) [specific.c:2154](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/specific.c#L2154).

`valuefacts.state='A'` bedeutet aktiv, `record='A'` Aufzeichnung ausgewählt. Die aktive Auswahl liest `state='A' OR record='A'`; gespeichert werden nur Sensoren mit Aufzeichnungsflag. Ein neuer Metadateneintrag startet in `addValueFact` mit `state='D'`. Benutzerdefinierte Titel, Gruppenzuordnungen, Auswahl und sonstige Settings dürfen bei einer Übernahme nicht aus einer erneuten Discovery ungeprüft zurückgesetzt werden. Quellen: [daemon.c:1241](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/daemon.c#L1241) [daemon.c:610](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/daemon.c#L610) [daemon.c:3015](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/daemon.c#L3015).

Wichtig: Dictionaryname `SUBTYPE` wird physisch in Spalte **`res1`** gespeichert; `SETTINGS` in **`calibration`**. In `peaks` heißen `MIN` und `MAX` physisch `minv` und `maxv`. In Dashboards gibt es ebenfalls abweichende Namen. Python darf C++-Dictionarynamen nicht direkt als SQL-Spaltennamen behandeln. Quelle: [configs/database.dat:20](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/configs/database.dat#L20).

## Historie: Werte, Typen und Zeit

`samples` enthält `address` INT unsigned, `type` VARCHAR(8), `aggregate` VARCHAR(1), `time` DATETIME als Primärschlüsselbestandteile. Hinzu kommen `inssp`, `updsp` (Integer-Zeitstempel), `value` (Dictionary `Float 122`, nach dessen Formatierung `FLOAT(14,2)`, also 14 Gesamtstellen und 2 Dezimalstellen), `text` VARCHAR(50), `samples` INT. Die reale Serverdarstellung, Nullbarkeit, Defaults und Indizes müssen per DDL geprüft werden. Quellen: [configs/database.dat:48](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/configs/database.dat#L48) [lib/dbdict.h:178](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/lib/dbdict.h#L178).

**Skalierung:** `VA` wird bereits beim Auslesen durch den Faktor geteilt. Bei `res1=1` wird das 16-Bit-Muster unsigned interpretiert, sonst signed. `samples.value` ist somit der fachliche Wert, kein Rohregister. Ein erneutes Teilen beim Lesen alter Historie wäre falsch. `DO`/`DI` speichern ihren Zustand, `AO` seinen numerischen Wert; Text kann zusätzlich zum Zahlenwert vorhanden sein. Quellen: [specific.c:402](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/specific.c#L402) [daemon.c:2151](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/daemon.c#L2151).

**Zeit:** `samples.time` ist der gemeinsame Host-Speicherzeitpunkt eines Aufzeichnungsdurchlaufs, nicht automatisch die Heizungszeit oder der genaue Abfragezeitpunkt jedes Sensors. `cDbValue` wandelt `time_t` per `localtime_r` in SQL-DATETIME um und zurück per `mktime`, ohne gespeicherte Zeitzone. `inssp` und `updsp` sind dagegen Unix-Sekunden; die DB-Helfer setzen beide beim Insert und nur `updsp` beim Update. Quellen: [daemon.c:2112](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/daemon.c#L2112) [daemon.c:2151](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/daemon.c#L2151) [lib/db.h:210](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/lib/db.h#L210) [lib/db.h:374](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/lib/db.h#L374) [lib/db.c:1567](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/lib/db.c#L1567) [lib/db.c:1601](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/lib/db.c#L1601).

Die Zeitzone des Alt-Rechners und der SQL-Session ist noch unbekannt. Eine Umstellung der bestehenden DATETIME-Spalte auf UTC darf nicht still erfolgen. Bei Sommerzeitumstellung kann dieselbe lokale Uhrzeit zweimal vorkommen, während der Primärschlüssel nur Sekundenauflösung enthält. Der Bestand verwendet beim Speichern eine Find/Update/Insert-Logik; das Kollisionsverhalten muss auf einer Datenbankkopie geprüft werden. Quelle: [lib/db.c:1542](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/lib/db.c#L1542).

**Aktualität:** `store` überspringt deaktivierte Sensoren, NaN, fehlenden Datenzeitstempel und Daten, deren letzter erfolgreicher Updatezeitpunkt nicht nach `lastStore` liegt. Ein unveränderter, aber erfolgreich neu gelesener Messwert darf trotzdem gespeichert werden. Bereits vorhandene Lücken werden nicht durch erfundene Ersatzwerte gefüllt. Quelle: [daemon.c:2151](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/daemon.c#L2151).

**Zeichensatz:** Der Daemon fordert für die DB-Verbindung `utf8` an; Heizungsbytes werden zuvor aus ISO-8859-1 umgesetzt. Tatsächliche Tabellenkollationen sind damit nicht belegt. Quellen: [daemon.c:289](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/daemon.c#L289) [lib/common.c:1753](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/lib/common.c#L1753).

## Aggregation

Rohmesspunkte verwenden `aggregate='S'`, `samples=1`. Die Bestandsaggregation erzeugt `aggregate='A'`, Mittelwert `round(sum(value)/count(*),2)` und Anzahl `count(*)`; die Zeit wird auf das **Ende** des jeweiligen Intervalls gesetzt. Sie gruppiert nach Intervall, Adresse und Typ. Nach erfolgreicher Aggregaterzeugung löscht sie alte Nicht-`A`-Zeilen. `text` ist in der SQL-Auswahl nicht eindeutig aggregiert; unter strengen GROUP-BY-Einstellungen kann dies relevant sein. Quelle: [daemon.c:2880](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/daemon.c#L2880).

Die UI-Konfigurationsdefinition nennt 365 Tage Historie und 15 Minuten Aggregatintervall; andere Codeinitialisierungen enthalten abweichende Defaults. Verbindlich ist der tatsächliche gespeicherte Konfigurationswert. Quellen: [specific.c:27](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/specific.c#L27) [daemon.h:678](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/daemon.h#L678).

**Empfehlung:** Bestehende `S`- und `A`-Reihen unverändert lesen und erhalten. Eine neue Aggregationsroutine ist kein notwendiger erster Implementierungsschritt; vor Ablösung muss jedoch entschieden werden, wer künftig die Bereinigung übernimmt. Keine zwei gleichzeitig laufenden Aggregationswriter.

## Menü und Zeitprogramme in der DB

`menu.value` ist VARCHAR(100), also eine Anzeigezeichenkette, beispielsweise `ja`, `65,0` oder `HH:MM`. `digits`, `min`, `max`, `def`, `factor`, `pub1`–`pub3`, `puw1` ergänzen die Metadaten; `unknown1`/`unknown2` stammen aus Discovery. `menu.state='D'` bei Discovery ist nicht automatisch ein Verbot, den Parameter zu bearbeiten. `menu` ist Cache und Menüstruktur, keine garantierte Live-Wahrheit. Quellen: [configs/database.dat:335](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/configs/database.dat#L335) [specific.c:970](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/specific.c#L970) [specific.c:1977](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/specific.c#L1977).

`timeranges` hat `address` als Schlüssel sowie `from1`/`to1` bis `from4`/`to4` als VARCHAR(5). Unbelegte Intervalle erscheinen als `nn:nn`. Das Protokoll benutzt dafür `FF`-Bytes; Datenbankzeichenketten dürfen nicht direkt als Bytes interpretiert werden. Quellen: [configs/database.dat:367](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/configs/database.dat#L367) [service.h:505](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/service.h#L505).

## Konfiguration

Die Verbindungsdaten stammen aus `daemon.conf`; die laufende Anwendungskonfiguration steht überwiegend in `config`. Der normale Owner ist `myName()` = `TARGET` = `p4d`, nicht automatisch der Datenbankname `p4`. `getConfigItem` kann fehlende Defaults in die Datenbank zurückschreiben; deshalb ist ein Start des alten Daemons kein rein lesender Bestandsabgleich. Quellen: [configs/daemon.conf:5](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/configs/daemon.conf#L5) [daemon.c:4013](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/daemon.c#L4013) [daemon.h:146](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/daemon.h#L146) [Make.config:8](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/Make.config#L8).

## Kompatibilitätsnachweis vor dem Umstieg

Der erste Live-Schemaabgleich ist erfolgt. Folgende Schritte gelten für den weiteren Nachweis; Tests mit Schreibzugriff ausschließlich auf einer separaten Kopie:

1. DDL, Tabellenkollationen, SQL-Modus, Zeitzonen und relevante Konfigurationswerte erfassen. Kein Start des alten Daemons mit fremdem Dictionary gegen die produktive DB, weil er Strukturen ändern kann.
2. Auf einer separaten Datenbankkopie dieselben Metadaten und Historienwerte mit der neuen Leseanbindung auslesen: negative Werte, unsigned-Werte >32767, Dezimalwerte, Text, `S`-/`A`-Daten und Zeitumstellungen.
3. Einen synthetischen Aufzeichnungsdurchlauf ausschließlich in die Kopie schreiben und durch einen zur Altversion passenden Reader prüfen: Identität, Skalierung, Spalten, lokale Zeit und Metastempel.
4. Unverwandte Tabellen und Benutzerkonfiguration vergleichen; keine ungeplante Veränderung. Erst danach einen exklusiven Wechsel des Heizungsdienstes mit getesteter Rückkehr zu p4d planen.

Ein erster lesender Abgleich liegt inzwischen vor: [Live-Datenbankbefund](live-database.md) und [Schemasnapshot](live-schema.json). Er zeigt konkrete Unterschiede zum Referenzdictionary. Das genaue Schema der laufenden Instanz ist die letzte Autorität für den Kompatibilitätsadapter. Eine Migration oder produktive Schreibanbindung ist noch nicht implementiert.
