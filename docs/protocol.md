# Heizungsprotokoll: COM1 / S3200

Diese Beschreibung wurde aus dem [Referenzstand](README.md#referenz-und-aussagekraft) abgeleitet. Die ursprüngliche Analyse erfolgte ohne echte Telegrammmitschnitte. Inzwischen sind einzelne vorhandene Empfangsframes offline geprüft; ein vollständiger Parameterschreibmitschnitt fehlt weiter. Siehe [Live-Server-Abgleich](live-server.md). Die COM2-Konstanten in `service.h` beschreiben einen anderen Pfad und sind nicht Grundlage des untersuchten Servicemenüs.

## Transport und Synchronisation

**Belegt:** `P4d` öffnet standardmäßig `/dev/ttyUSB0` mit 57.600 Baud. Der normale termios-Pfad setzt 8 Datenbits, keine Parität, ein Stoppbit, `CLOCAL`, `CREAD`, `IGNPAR`; weder Hardware- noch Software-Flusssteuerung wird aktiviert. Das Gerät wird nichtblockierend geöffnet. Die konkrete Gerätebezeichnung kommt aus der Konfiguration. Quellen: [specific.c:118](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/specific.c#L118) [specific.c:345](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/specific.c#L345) [lib/serial.c:41](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/lib/serial.c#L41).

Ein `P4Request`-Mutex schützt Befehle. Hinzu kommt im Heizungsdienst eine System-V-Semaphore mit Schlüssel `0x3da00001`. Sie wird von vielen, aber nicht allen übergeordneten Abläufen verwendet. Der Mutex benutzt einen Fehlerprüfmodus und einen eigenen Verschachtelungszähler, keine normale rekursive pthread-Konfiguration. Ein Python-Worker muss die gesamten zusammengehörenden Telegrammfolgen serialisieren; zwei Prozesse dürfen nicht unabhängig am selben Port lesen. Quellen: [lib/common.c:1924](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/lib/common.c#L1924) [lib/common.h:618](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/lib/common.h#L618) [specific.c:402](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/specific.c#L402) [p4io.c:689](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/p4io.c#L689).

**Belegt:** `readHeader` wartet standardmäßig bis zu 2.000 ms pro Byte-Leseoperation; nachfolgende `readByte`-Aufrufe standardmäßig 1.000 ms, auch für Escape-Folgebytes. Das ist kein Gesamtdeadline für ein Telegramm. `RequestClean` liest bei Funktionsende weitere Bytes bis zu einer 10-ms-Lesepause aus und protokolliert unerwartete Daten. `readHeader` erwartet die Startkennung unmittelbar; es sucht nicht selbst nach dem nächsten Frame im Datenstrom. Quellen: [p4io.h:151](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/p4io.h#L151) [p4io.h:193](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/p4io.h#L193) [p4io.h:34](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/p4io.h#L34) [p4io.c:223](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/p4io.c#L223).

Der Dienst öffnet bei fehlgeschlagener Verbindungsprüfung den Port neu. Ein Sensorfehler wird protokolliert und der nächste Sensor abgefragt; ein alter Wert erhält dabei keinen neuen Aktualisierungszeitpunkt. Der grundlegende serielle Writer behandelt einen Teil-Write als Fehler statt den Rest nachzusenden. Quellen: [specific.c:402](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/specific.c#L402) [specific.c:599](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/specific.c#L599) [lib/serial.c:243](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/lib/serial.c#L243).

## Telegrammaufbau

Alle Offsets in den folgenden Tabellen beziehen sich auf **demaskierte** Bytes.

| Offset | Größe | Bedeutung |
| --- | --- | --- |
| 0 | 2 | Startkennung `02 FD`, unmaskiert |
| 2 | 2 | Länge, unsigned, Big Endian: Nutzdaten + ein Prüfsummenbyte |
| 4 | 1 | Befehl |
| 5 | variabel | Nutzdaten |
| Ende | 1 | Prüfsumme |

Die Länge zählt weder die Startkennung noch Länge/Befehl und auch keine zusätzlichen Escape-Bytes. Leere Nutzdaten ergeben Länge 1 und insgesamt 6 demaskierte Bytes. Der deklarierte maximale Nutzdatenumfang beträgt 254 Bytes; die Decoder prüfen dies nicht durchgängig. Adressen und Words sind Big Endian. `Value` und numerische Parameter enthalten signed 16-Bit-Werte; bei Messwerten hängt die endgültige Vorzeicheninterpretation von Metadaten ab. Quellen: [service.h:56](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/service.h#L56) [service.h:82](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/service.h#L82) [p4io.c:23](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/p4io.c#L23) [p4io.c:166](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/p4io.c#L166) [p4io.c:183](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/p4io.c#L183).

Nach Aufbau und Prüfsummenbildung werden **alle Bytes ab Offset 2**, einschließlich Länge, Befehl und Prüfsumme, maskiert:

| Logisches Byte | Bytes auf der Leitung |
| --- | --- |
| `02` | `02 00` |
| `2B` | `2B 00` |
| `FE` | `FE 00` |
| `11` | `FE 12` |
| `13` | `FE 14` |
| alle anderen | unverändert |

Der Decoder erwartet die exakten Folgebytes und lehnt andere Kombinationen ab. Quellen: [p4io.c:23](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/p4io.c#L23) [p4io.c:104](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/p4io.c#L104).

### Prüfsumme

`crc` ist der Funktionsname des Bestands. Der Algorithmus ist ein XOR über `b XOR ((b * 2) AND 255)` für jedes **demaskierte** Byte von der Startkennung bis zum letzten Nutzdatenbyte, mit Startwert 0; das Prüfsummenbyte selbst ist ausgeschlossen. Es gibt im Code keinen üblichen CRC-Polynomalgorithmus. Quelle: [lib/common.c:1804](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/lib/common.c#L1804).

Nur `getValue` vergleicht im untersuchten Heizungslesepfad die empfangene Prüfsumme mit einer berechneten. Viele andere Befehle lesen das Byte lediglich ein. `getValue` rekonstruiert dafür Header und Wert in Host-Reihenfolge. Weil dieser XOR-Algorithmus nicht von der Byte-Reihenfolge abhängt, ist deren Umkehrung allein kein Prüfsummenfehler. Quelle: [p4io.c:866](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/p4io.c#L866).

**Empfehlung:** Jeder zukünftige Frame wird zentral auf Start, Größe und Prüfsumme geprüft; Antwortbefehl und gegebenenfalls Antwortadresse werden zusätzlich zur laufenden Transaktion zugeordnet. Der Bestand prüft diese Zuordnung nicht durchgängig. Tatsächlich verwendete Antwortcodes müssen durch Mitschnitte bestätigt werden.

## Befehlsübersicht

Die Befehlscodes sind in [service.h:90](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/service.h#L90) definiert. Die Antwortlayouts stammen aus den jeweiligen Lesefunktionen, nicht aus einer Herstellerbeschreibung. `u16` bezeichnet unsigned Big Endian, `s16` signed Big Endian. Prüfsummen sind in der Spalte Nutzdaten nicht mit aufgelistet.

| Code | Zweck | Request-Nutzdaten | Vom Bestand gelesene Antwort-Nutzdaten / Ende |
| --- | --- | --- | --- |
| `22` | Verbindung prüfen | Text `Tescht ;-)` | Text; dessen Inhalt wird nicht auf Gleichheit geprüft |
| `30` | Messwert | Adresse u16 | Wert s16 |
| `31` / `32` | Messwertdefinitionen: erster / nächster | leer | more u8, Faktor u16, Datentyp u16, Einheit 2 Bytes, Adresse u16, Beschreibung, Terminator; more=0 beendet |
| `37` / `38` | Menü: erster / nächster | leer | more und Menüstruktur, siehe unten; more=0 beendet |
| `39` | Parameter schreiben | Adresse u16, neuer Rohwert als 16-Bit-Muster | zwei Antworten mit jeweils Adresse u16 + Wert s16; danach separat `55` |
| `41` | Version und Heizungszeit | leer | vier Versionsbytes, Zeit/Datum 7 Bytes, danach verbleibende Bytes begrenzt auslesen |
| `42` / `43` | Zeitprogramme: erstes / nächstes | leer | unbekannt u16, Adresse u8, vier Paare from/to u8; Adresse `DF` ist letzter Datensatz |
| `44` / `45` / `46` | Digitalausgang / Analogausgang / Digitaleingang | Adresse u16 | mode u8, state u8 |
| `47` / `48` | Fehlerliste: erster / nächster | leer | more u8, Nummer u16, info u8, state u8, Zeit/Datum 6 Bytes, Text; more=0 beendet |
| `50` | Zeitprogramm schreiben | Adresse u16, vier Paare from/to u8 | unbekannt u8, Adresse u16, vier Paare from/to u8 |
| `51` | Betriebsart / Zustand | leer | mode u8, state u8, Text `Betriebsart;Zustand` |
| `54` | Heizungsuhr schreiben | s, min, h, Tag, Monat, Wochentag, Jahr seit 2000 | Statusbyte (0 als Erfolg), danach Prüfsumme |
| `55` | Parameter lesen | Adresse u16 | Parameterstruktur, siehe unten |

Quellen: [p4io.c:442](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/p4io.c#L442) [p4io.c:1060](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/p4io.c#L1060) [p4io.c:1157](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/p4io.c#L1157) [p4io.c:474](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/p4io.c#L474) [p4io.c:915](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/p4io.c#L915) [p4io.c:1005](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/p4io.c#L1005) [p4io.c:742](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/p4io.c#L742) [p4io.c:803](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/p4io.c#L803) [p4io.c:566](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/p4io.c#L566).

Weitere Codes wie `40` (Basiskonfiguration), `58`–`5A` (I/O manipulieren), `5E`/`7E` (Force) und `35`/`36` sind deklariert. Ihre Deklaration belegt keine vollständige nutzbare Implementierung für den geplanten Parametermenüumfang. Insbesondere ist I/O-Forcing nicht mit normalem Parameterschreiben gleichzusetzen.

### Parameterantwort `55`

| Nutzdatenoffset | Feld | Typ / Länge |
| --- | --- | --- |
| 0 | ub1 | u8, Bedeutung unbekannt |
| 1 | Adresse | u16 |
| 3 | Einheit | 1 Byte Text |
| 4 | Nachkommastellen | u8 |
| 5 | ub2 | u8, unbekannt |
| 6 | Faktor | u8 |
| 7 | aktueller Rohwert | s16 |
| 9 | Minimum | s16 |
| 11 | Maximum | s16 |
| 13 | Default | s16 |
| 15 | uw1 | s16, unbekannt |
| 17 | ub3 | u8, unbekannt |

Damit erwartet der normale Pfad 18 Nutzdatenbytes plus Prüfsumme. Der Bestand prüft vorab allerdings nur `header.size < 4`, nicht diese vollständige Länge. Er setzt Faktor 0 auf 1 und berechnet **aktuellen Wert / Faktor**. Minimum, Maximum und Default werden ausdrücklich **nicht** durch den Faktor geteilt. Diese Asymmetrie ist belegt, ihre Gültigkeit für alle Firmware-/Parametertypen offen. Quelle: [p4io.c:616](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/p4io.c#L616).

### Menüantwort `37` / `38`

Nach `more` folgen: Typ u8, unknown1 u8, parent u16, child u16, 18 ignorierte Bytes, Adresse u16, unknown2 u16, Beschreibung mit variabler Länge, ein Terminatorbyte, Prüfsumme. Der Parser überspringt kurze Einträge bei weniger als 30 verbleibenden Bytes nach `more`. Die ignorierten Bytes könnten zusätzliche Metadaten enthalten; Bedeutung und möglicher Bezug zu Zugriffsrechten sind **offen**. Quelle: [p4io.c:1157](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/p4io.c#L1157).

### Text und Zeit

`readText` entfernt NUL und die Bytes `01`, `02`, `03` und konvertiert standardmäßig ISO-8859-1 nach UTF-8. Der Rohtext muss deshalb von seiner aufbereiteten Darstellung unterschieden werden. `°` wird an mehreren Stellen zu `°C` erweitert. Quellen: [p4io.c:395](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/p4io.c#L395) [lib/common.c:1753](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/lib/common.c#L1753) [p4io.c:616](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/p4io.c#L616).

Uhrzeit wird als Sekunden, Minuten, Stunden gelesen; Datum als Tag, Monat, Jahr seit 2000, in der erweiterten Form mit Wochentag vor dem Jahr. Der Bestand setzt lokale Zeit mittels `mktime` zusammen. Beim Uhrschreiben wird zur aktuellen Sekunde 1 addiert, ohne hier einen Übertrag bei Sekunde 59 zu normalisieren. Zeitprogramme verwenden dagegen `Stunde * 10 + Minute / 10` (Ganzzahldivision), `FF` für ungesetzt und vier Intervalle pro Adresse. Quellen: [p4io.c:267](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/p4io.c#L267) [p4io.c:319](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/p4io.c#L319) [p4io.c:566](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/p4io.c#L566) [service.h:505](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/service.h#L505).

## Lesen vom Polling bis zur Datenbank

1. `initValueFacts` ermittelt Messwertdefinitionen über `31`/`32` und legt Typ `VA`, Faktor und Datentyp in `valuefacts` ab. I/O-Definitionen entstehen zusätzlich aus den Menüeinträgen.
2. `doLoop` / `updateState` lesen über `51` und `41` Status, Version und Zeit; das konfigurierbare Statusintervall hat im Referenzcode Default 10 Sekunden.
3. `updateSensors` prüft die Verbindung und fragt die ausgewählten Sensoren seriell einzeln ab. Bei `VA` gilt: Datentyp 1 → unsigned 16 Bit, sonst signed 16 Bit; geteilt durch den Metadatenfaktor. I/O-Typen verwenden `44`/`45`/`46`.
4. `Daemon::storeSamples` speichert zur Aufzeichnungszeit die seit dem letzten Speichern aktualisierten und zur Aufzeichnung ausgewählten Werte; Defaultintervall 60 Sekunden. Historienwerte sind bereits skaliert.

Quellen: [specific.c:2154](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/specific.c#L2154) [specific.c:599](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/specific.c#L599) [specific.c:402](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/specific.c#L402) [daemon.c:2112](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/daemon.c#L2112) [daemon.c:2151](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/daemon.c#L2151) [specific.c:27](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/specific.c#L27).

Faktor 0 wird bei `VA` im gezeigten Pollingpfad nicht abgefangen. Statuswerte `UD` und Zustandsdauer `SD` sind abgeleitete p4d-Werte, keine normalen `30`-Messwertadressen. Datenbankdetails stehen in [Datenbankkompatibilität](database-compatibility.md).

## Verifizierte synthetische Beispiele

Die Adressen und Zahlen sind erfunden. Keines dieser Beispiele wurde an eine Heizung gesendet. Vollständige Vektoren: [protocol-vectors.json](protocol-vectors.json); Prüfung: [Werkzeug](tools/verify_protocol_examples.py).

| Fall | Demaskierte Nutzdaten | Telegramm auf der Leitung |
| --- | --- | --- |
| `30`, Messwert Adresse `002B` lesen | `00 2B` | `02 FD 00 03 30 00 2B 00 29` |
| `55`, Parameter Adresse `1234` lesen | `12 34` | `02 FD 00 03 55 12 34 91` |
| `39`, Rohwert 650 an fiktive Adresse `1234` | `12 34 02 8A` | `02 FD 00 05 39 12 34 02 00 8A B7` |
| `37`, Menü beginnen | leer | `02 FD 00 01 37 5B` |
| synthetische `30`-Antwort −12 | `FF F4` | `02 FD 00 03 30 FF F4 49` |

Die synthetische Parameterantwort in der JSON-Datei enthält Faktor 10, Nachkommastellen 1 und Rohwert 650: der aktuelle Anzeigewert ergibt 65,0; Minimum 20, Maximum 90 und Default 60 bleiben nach Bestandslogik ungeteilt. Ihre Längenangabe `00 13` wird auf der Leitung `00 FE 14`. Der Zeitprogrammvektor enthält Adresse `0038` und 06:00–08:00 (`3C 50`), danach drei ungesetzte Intervalle. Der letzte Vektor deckt alle fünf Sonderbytes ab.

## Fehlerzustände und noch fehlende Belege

`FroelingService::Error` unterscheidet unverändert, außerhalb des Bereichs, Listenende, leeren/übersprungenen Eintrag, Timeout, Requestfehler, falsche Adresse und Übertragungsfehler. Einige übergeordnete Funktionen reduzieren dies auf einen allgemeinen Fehler oder melden trotz abgebrochener Initialisierung Erfolg. Quelle: [service.h:42](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/service.h#L42); konkrete Befunde in [Befunde](findings-and-next-steps.md).

Noch zu bestätigen sind echte Antwortcodes und -längen, die Bedeutung der beiden Schreibantworten, Verhalten nach Schreibtimeout, Metadaten bei negativen/dezimalen Parametern, Firmwarevarianten sowie Verhalten bei abgebrochenen First/Next-Listen. Ein Timeout nach einem gesendeten Schreibbefehl beweist nicht, dass die Heizung unverändert geblieben ist. **Empfehlung:** Zustand erneut lesen, bevor ein erneuter Schreibversuch erwogen wird; keine automatische blinde Wiederholung.

## Ergänzung: erster erfolgreicher Hardware-Lesepfad

Beim korrigierten Hosttest waren mit unverändertem Python-Antwortprofil Status (`51`), Firmware (`41`), Messwerterfassung (`30`) und die Abfrage eines Zahlenparameters (`55`) erfolgreich. Zwei Sammeldurchläufe speicherten jeweils 13 Messpunkte in der separaten Testdatenbank. Das belegt diese konkret ausgeführten Lesepfade unter den aktiven Frame-/CRC-/Adressprüfungen, keine allgemeine Gültigkeit für alle Menüadressen oder Schreibbefehle.

Eine spätere unerwartete Antwort führte zum kontrollierten Abbruch. Die automatische Rückkehr zu p4d samt erneuter Originalaufzeichnung ist bestätigt. Die genaue Abweichung muss noch am privaten Mitschnitt identifiziert werden; weder Antwortprüfung lockern noch Daten still verwerfen. Für die Offlineauswertung: `PYTHONPATH=src .venv/bin/python docs/tools/analyze_serial_trace.py PRIVATE_TRACE`. Das Werkzeug gibt nur Protokollidentitäten und Auffälligkeiten aus.

### Belegte Abweichung bei Zeitprogrammen

Der private Mitschnitt des ersten echten Lesetests zeigt gültige Antworten `42` sowohl auf die erste Anfrage `42` als auch auf die Folgeanfrage `43`. Beide gelieferten Zeitgruppen sind identisch und tragen Adresse `00`. Der alte Simulationsstandard Requestcode = Antwortcode war hier falsch. Das Zielhostprofil unter `deploy/heating-reply-profile.json` legt daher `43 -> 42` fest; vollständige Zeitlisten und andere Firmwarevarianten sind noch nicht damit validiert.

Der Originalpfad `P4d::updateTimeRangeData` führt zuerst `check()` mit dem Text `Tescht ;-)` aus. Anschließend fragt er First/Next bis Adresse `DF` ab und speichert nach Adresse, sodass ein weiterer Eintrag derselben Adresse den vorherigen ersetzt. `P4Request::getTimeRanges` prüft dabei den Antwortcommand nicht. Der Python-Lesepfad übernimmt nun Check und Ersetzen nach Adresse, zusätzlich mit vorhandener Gesamtdeadline und begrenzter Antwortzahl. Das ist keine Freigabe für echte Zeitprogrammänderungen.

### Zeitdaten lesen und Eingaben prüfen

Der nächste Hardwaretest bestätigte, dass die korrigierte Befehlsfolge den vorherigen Antwortcodefehler überwindet. Er wurde anschließend durch die bisher zu strenge Uhrzeitdekodierung abgebrochen; automatische Rückkehr und Originalaufzeichnung sind erneut bestätigt.

p4d liest die Zeitbytes unverändert und formatiert sie mit Ganzzahldivision durch 10 und Rest mal 10. Nur das Paar `FF FF` gilt als unbelegt. Deshalb muss Lesen auch Werte außerhalb des Python-Uhrzeitbereichs erhalten, ohne sie zu korrigieren oder die Messwerterfassung deswegen abzubrechen. Der Python-Lesepfad übernimmt dies nun verlustfrei; `RawTimeRange` erhält bei Bedarf Originalbytes und Darstellung. Beispielsweise bleibt `F0` als `24:00` erhalten; das ist ein Testbeispiel, kein belegter konkreter Anlagenwert. Die Prüfung neuer Benutzereingaben bleibt davon getrennt und unverändert streng.

### Sensor- und Menü-Discovery: Abgleich 0.5.1

Referenz `specific.c:894` (`initMenu`) und `specific.c:2154` (`initValueFacts`) führen vor First/Next jeweils `request->check()` aus; `p4io.c:442` sendet dabei `Tescht ;-)`. Dies fehlte im bisherigen Python-Sensor-/Menüpfad und ist ergänzt. `p4io.c:1060` überspringt zu kurze nicht abschließende Sensoreinträge (`wrnEmpty`), `p4io.c:1157` entsprechende Menüeinträge (`wrnSkip`). Aus Headergröße einschließlich CRC und bereits gelesenem more-Byte ergeben sich mindestens 11 beziehungsweise 30 Payloadbytes für einen verwertbaren Eintrag. Python überspringt dieselben kurzen Einträge innerhalb der Liste; CRC-/Framefehler bleiben Fehler, keine unvollständige Discovery wird übernommen.

Die frühere Gesamtfrist von 300 Sekunden durfte pro fehlender Listenantwort vollständig aufgebraucht werden. Nun ist jede einzelne Listenanfrage/Antwort auf zwei Sekunden begrenzt, zusätzlich zur Gesamtfrist. Original `p4io.h:151` verwendet zwei Sekunden für den Header und separate Fristen beim Lesen der Nutzbytes. Der Python-Ablauf begrenzt die gesamte einzelne Anfrage/Antwort und setzt die Frist bei Teilstücken nicht zurück. Der reale Hänger der ersten 0.5.0-Discovery ist damit noch nicht ursächlich bewiesen: das damalige Journal enthielt keine konkrete Exception. 0.5.1 ergänzt diese Diagnose.
