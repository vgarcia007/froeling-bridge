# Befunde und nächste Schritte

## Was diese Bestandsaufnahme bereits beantwortet

- Die Kernkommunikation erfolgt über COM1, 57.600 Baud, 8N1. Telegrammaufbau, Maskierung und Prüfsumme sind aus konkreten Funktionen abgeleitet und offline geprüft.
- Sensorliste und Menüstruktur werden aus der Heizung gelesen; Messwertmetadaten und Parametermetadaten sind unterschiedliche Datenquellen.
- Normale Parameterschreibvorgänge bestehen aus Vorabfragen, `39`, zwei Antworten und erneutem `55`. Zeitprogramme haben einen separaten Vier-Intervall-Schreibpfad.
- Die vorhandene Datenbank kann als Kompatibilitätsziel beschrieben werden. Ein erster realer Schemaabgleich liegt inzwischen vor; die genaue Altversion und die vollständige fachliche Kompatibilität müssen noch abgeglichen werden.
- Fork und Original-`master` zeigten am 16.10.2026 auf denselben Commit. Es gibt an diesen Branchspitzen keine spezifischen Fork-Anpassungen zu berücksichtigen.

Belege und Details stehen in [Protokoll](protocol.md), [Menü](parameter-menu.md), [Datenbank](database-compatibility.md) und [Referenz](README.md#referenz-und-aussagekraft).

## Priorisierte Quellcodebefunde

Dies sind statische Befunde. Sie sind weder an der realen Anlage reproduziert noch eine Erklärung für deren konkretes Webinterfaceproblem.

| Priorität | Befund | Bedeutung für den Nachbau / noch zu prüfen |
| --- | --- | --- |
| hoch | Zeitprogrammhandler läuft nach Fehlern weiter und kann DB-Update plus Erfolgsmeldung ausführen | vor DB-Änderung auf bestätigten Erfolg bestehen; Fehlerzweige im späteren Simulator prüfen |
| hoch | Zeitprogrammhandler prüft `range` nicht vollständig auf 1..4 | vollständige Grenzenprüfung vor Arrayzugriff und Senden |
| hoch | Normales Schreiben liest nach, vergleicht den nachgelesenen Wert aber nicht explizit mit dem Ziel | Transporterfolg von bestätigter Änderung trennen |
| hoch | Die beiden Antworten auf `39` werden gelesen, ihre Bedeutung ist nicht erklärt | echte vollständige Schreibmitschnitte samt Vorher-/Nachherwerten erforderlich |
| hoch | `performParStore` ignoriert die erste fehlgeschlagene Metadatenabfrage vor Konvertierung | bei fehlenden aktuellen Metadaten vor dem Schreiben abbrechen |
| hoch | Die meisten Antwortpfade konsumieren die Prüfsumme ohne Prüfung; Headercommand und Adresszuordnung werden nicht konsequent geprüft | zentralen Frame- und Transaktionsvalidator planen; echte Antwortcodes bestätigen |
| mittel | Zeitprogramm-Teiländerungen senden auch drei weitere, aus der DB geladene Intervalle | aktuelle Gesamtgruppe vor Änderung einlesen; fremde Änderungen nicht überschreiben |
| mittel | Menü-Discovery löscht vorher den alten Bestand; Abbruch kann trotzdem als Erfolg enden | neue Discovery vollständig sammeln und erst nach Erfolg als gültig übernehmen |
| mittel | `getTimeRanges` überschreibt Fehlerstatus in der Vierer-Schleife und beim CRC-Lesen | jeder Lesefehler muss die Antwort ungültig machen |
| mittel | Parameterwert wird durch Faktor geteilt, Grenzen/Default nicht | zunächst exakt dokumentiert; mit realen Dezimal-/Negativparametern validieren |
| mittel | VA-Messwertfaktor kann im Polling ungeprüft 0 sein | fehlende/ungültige Metadaten nicht in scheinbar gültige Messwerte umsetzen |
| mittel | Zeitprogramme runden Minuten implizit nach unten | UI und API müssen die Zehn-Minuten-Auflösung sichtbar behandeln |
| mittel | DATETIME repräsentiert lokale Hostzeit, nicht UTC | Altzeitzone und Sommerzeitfälle vor DB-Anbindung klären |
| mittel | `storeSamples` prüft nicht sämtliche Einzel-DB-Ergebnisse; `store` meldet nach seinem Speicheraufruf Erfolg | späteren Persistenzpfad auf DB-Ausfälle prüfen; keine erfolgreiche Speicherung nur aus dem Funktionsnamen ableiten |
| mittel | Die Hauptschleife ruft `storeSamples` zweimal direkt nacheinander auf | zweiten Aufruf nicht als gewünschte Semantik übernehmen; Auswirkungen auf DB-/Zeitstempelverhalten auf Kopie prüfen |
| nachrangig | Menüsuchfunktion leer; spezielle Zeitgruppen/Adressen fest codiert | moderne Suche und firmwareabhängige Menüheuristiken später ausdrücklich planen |
| nachrangig | Dezimaleingabe hängt von Browserkonvertierung und Prozess-Locale ab | künftige API localeunabhängig; alter DB-Anzeigetext separat |
| nachrangig | Uhrschreiben addiert 1 zur Sekunde ohne lokalen Übertrag | Zeitsynchronisation separat untersuchen, nicht für erstes Lesen aktivieren |

Quellen: [specific.c:1870](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/specific.c#L1870) [specific.c:1798](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/specific.c#L1798) [specific.c:894](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/specific.c#L894) [specific.c:1972](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/specific.c#L1972) [p4io.c:689](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/p4io.c#L689) [p4io.c:616](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/p4io.c#L616) [p4io.c:742](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/p4io.c#L742) [p4io.c:223](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/p4io.c#L223) [p4io.c:566](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/p4io.c#L566) [service.h:549](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/service.h#L549) [specific.c:402](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/specific.c#L402) [daemon.c:2112](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/daemon.c#L2112) [daemon.c:2151](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/daemon.c#L2151) [daemon.c:1981](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/daemon.c#L1981).

Die Hauptschleife führt Polling, Verarbeitung, Speicherung und nachgelagerte Aufgaben seriell aus und enthält selbst einen Warntext über ein langsames oder nicht reagierendes Webinterface bei zu langen Durchläufen. Das ist ein belegter Kopplungspunkt, **keine Diagnose** der laufenden Anlage. Empfehlung für den Nachbau: HTTP-Anfragen dürfen nicht auf einen kompletten Pollingdurchlauf warten; serielle Jobs laufen dennoch über einen gemeinsamen Besitzer. Quelle: [daemon.c:1981](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/daemon.c#L1981).

## Noch benötigte Angaben zur realen Installation

| Benötigt | Warum / mögliche lesende Quelle |
| --- | --- |
| Installierter Stand / laufendes Prozessabbild | Quellcheckout und Dienstpfad-Binärdatei inzwischen als 0.10.2 eingegrenzt; direktes Prozessabbild noch nicht abgeglichen, siehe Live-Server-Abgleich |
| Heizungsmodell, S3200-Ausführung, Firmware | Typenschild/Steuerungsanzeige, vorhandene Versionslogs oder bekannte Daten; keine neue Direktverbindung parallel zu p4d |
| Betriebssystem, Architektur, Python-Verfügbarkeit | Paket-/Hostinformationen; Grundlage für späteren einfachen Installationsweg |
| Anschluss und Gerätepfad | vorhandene Konfiguration/Serviceinformationen, USB-Seriell-Adaptertyp |
| Tatsächliches Schema der Kern-Tabellen | `SHOW CREATE TABLE`, Indexdefinitionen, Serverversion, SQL-Modus, Zeichensätze |
| Host- und DB-Zeitzone sowie Locale | `timedatectl`, `locale`, SQL-Sessionvariablen |
| Vorhandene Discovery-Metadaten | ausgewählte `valuefacts`-/`menu`-/`timeranges`-Zeilen, besonders negative/dezimale Parameter und Zeitgruppen |
| Tatsächliche Telegramme | bereits vorhandene Debuglogs mit Sende-/Empfangsbytes, Reihenfolge und Zeitabständen; Adressen, Typen, Werte und Grenzen erhalten |
| Laufende DB-Nutzer/Integrationen | prüfen, welche anderen Tools von bestehenden Tabellen oder Auswahlflags abhängen |

Inzwischen hat der Benutzer lokale DB-Zugangsdaten und ausdrücklich ausschließlich lesenden Zugriff bereitgestellt; ein erster [Live-Schemaabgleich](live-database.md) ist erfolgt. Anschließend wurde lesender SSH-Zugriff bereitgestellt und [der installierte Stand abgeglichen](live-server.md). Für die nächste Stufe genügen zunächst lokal erzeugte, bereinigte Bestandsinformationen; Passwörter, Token und ein kompletter `config`-/`users`-Dump werden nicht benötigt.

### Vorlage für lesende Datenbankabfragen

Erst auf dem Bestandsrechner oder einer Kopie ausführen, nicht automatisch durch dieses Projekt. Das Schema `p4` ist lediglich der Referenzdefault; die tatsächliche Datenbank über den Client auswählen. Keine Zugangsdaten in Befehlszeilen oder Dokumentation ablegen.

```sql
SELECT VERSION(), DATABASE(), @@sql_mode,
       @@session.time_zone, @@global.time_zone, @@system_time_zone,
       @@character_set_database, @@collation_database;
SHOW CREATE TABLE valuefacts;
SHOW CREATE TABLE samples;
SHOW CREATE TABLE peaks;
SHOW CREATE TABLE menu;
SHOW CREATE TABLE timeranges;
SHOW CREATE TABLE config;
SHOW CREATE TABLE errors;
SHOW CREATE TABLE valuetypes;
SHOW CREATE TABLE groups;

SELECT table_name, column_name, column_type, is_nullable, column_default,
       character_set_name, collation_name
FROM information_schema.columns
WHERE table_schema = DATABASE()
ORDER BY table_name, ordinal_position;

SELECT owner, name, value FROM config
WHERE name IN ('ttyDevice', 'interval', 'stateCheckInterval',
               'aggregateHistory', 'aggregateInterval', 'tsync', 'maxTimeLeak');
```

Die Abfragen lesen Schema und wenige benannte Konfigurationswerte, keine Zugangsdaten. Zusammen mit dem Schema können anschließend gezielt kleine Beispielzeilen ausgewählt werden. Zunächst keine vollständige Historie exportieren und keine teuren Volltabellenanalysen auf der laufenden Anlage ausführen.

### Telegrammmitschnitte

`P4Request::show` protokolliert `->` und `<-` als Hexbytes auf Debugstufe 2 (`0x08`). Vorhandene Mitschnitte lassen sich ohne neuen Zugriff auf COM1 untersuchen. Quellen: [p4io.h:114](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/p4io.h#L114) [lib/common.h:104](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/lib/common.h#L104).

Ein Schreibmitschnitt muss alle Vorabfragen, beide Antworten, das Nachlesen und den angezeigten Zielwert enthalten. Reine letzte Antwortzeilen reichen nicht. Es wird in dieser Phase kein Schreibexperiment vorgeschlagen oder ausgeführt. Wenn später ein bewusst gewählter Parameterschreibtest vereinbart wird, gehören Auswahl des Parameters und erwartetes Vorher-/Nachherverhalten in diesen gesonderten Testplan.

## Fortschritt nach SSH-Abgleich

Quellcheckout und Dienstpfad-Binärdatei passen zu 0.10.2; das zugehörige Dictionary stimmt im geprüften Strukturumfang mit der Live-DB überein. Die Kernprotokollquellen sind identisch mit der jüngeren Referenz. Vorhandene Logs liefern einzelne reale Empfangsframes, jedoch keinen vollständigen Parameterschreibvorgang. Damit kann als Nächstes der Offline-Protokollkern geplant werden; Heizungsmodell, Firmware und Schreibsemantik bleiben offen. Siehe [Live-Server-Abgleich](live-server.md).

## Fortschritt nach Offline-Implementierung

Der [Python-Protokollkern mit Simulator](python-core.md) ist inzwischen implementiert und durch 72 Tests geprüft. Framing, typisierte Antworten, vollständige Transaktionen sowie bestätigtes Parameterschreiben und Zeitprogrammänderungen sind offline verfügbar. Der nächste unabhängige Baustein ist die Datenbankkompatibilität gegen lokale Fixtures; reale Antwortzuordnungen und Hardware-Schreibsemantik bleiben offen. Die folgende ursprüngliche Reihenfolge beschreibt weiterhin die späteren Integrationsschritte, nicht ausschließlich unerledigte Arbeit.

## Empfohlene Reihenfolge der nächsten Arbeitsphasen

1. **Bestandsabgleich:** installierte Version und reales Schema ermitteln, Unterschiede zu dieser Referenz dokumentieren, vorhandene echte Telegramme zuordnen. Abschluss: eine benannte Hardware-/Firmware-/Schema-Kombination als Implementierungsziel.
2. **Offline-Protokollplan:** auf Basis echter Beispiele die Parser, Transaktionsabläufe und einen simulierten Heizungsgegner spezifizieren. Antwortcodes, Schreibbestätigung, Listenabbruch und Wiederanlauf müssen geklärt oder als explizit ununterstützt begrenzt sein.
3. **Python-Lesekern planen und bauen:** ein Besitzer für COM1, Discovery, Status und Messwerte; offline gegen Mitschnitte testen. Noch keine DB- oder Heizungsänderungen beim ersten Vergleich mit Bestandsdaten. Ein späterer Hardwaretest braucht exklusiven Portzugriff.
4. **DB-Adapter planen und auf Kopie prüfen:** bestehende Sensoridentitäten/Skalierung/Zeitsemantik erhalten, keine automatischen Schemaänderungen. Historie lesen und synthetische Aufzeichnungen rückwärtskompatibel prüfen.
5. **Schreibkern planen und verifizieren:** frische Metadaten, Typ-/Grenzenkontrolle, gesamte Transaktion, bestätigtes Nachlesen, unklarer Ausgang nach Timeout; zuerst Simulator, danach gesonderter Hardwaretest. Zeitprogramme separat behandeln.
6. **API und modernes Menü gemeinsam festlegen:** dokumentierte HTTP-API für Discovery, Werte, Menü und Änderungen; Browser als API-Client. Authentifizierung, Installation und Dienstbetrieb konkret entscheiden. Charts, Pelletverwaltung und übrige Integrationen zunächst auslassen.
7. **Umstieg und Rückkehr erproben:** Datenbanksicherung und Schemavergleich, alten Dienst stoppen, neuen Dienst exklusiv starten, Messreihen und Änderungen prüfen, Rückkehr auf p4d testen. Aggregationszuständigkeit dabei ausdrücklich bestimmen.

Diese Reihenfolge ist eine Empfehlung, kein bereits vollständig spezifizierter Implementierungsplan. Noch offen sind Python-Framework, Datenbanktreiber, Verpackung, Authentifizierung und UI-Technik. Sie werden nicht aus der heutigen C++-Struktur vorentschieden.

## Prüfstand und Grenzen dieser Lieferung

Ausgeführt wurden die Original-Encoder-/Decoderprüfungen aus [README](README.md#reproduzierbare-prüfung), der Commitvergleich, die Quellstellenprüfung und eine Prüfung der lokalen Dokumentationsverweise. Der Referenzcheckout ist unverändert. Im ursprünglichen Offline-Arbeitspaket wurde keine produktive DB-Verbindung hergestellt. Im anschließenden, gesondert autorisierten Live-Abgleich wurde ausschließlich lesend auf die DB zugegriffen. Es wurden kein Daemon gebaut oder installiert und keine Heizungsbefehle gesendet.

Die Prüfung beweist Bytecodierung und den dokumentierten Quellbezug. Sie beweist noch nicht die gesamte reale Antwortsemantik, Hardwareverträglichkeit oder Kompatibilität mit der unbekannten installierten Version. Insbesondere ist keine Aussage darüber möglich, warum das Webinterface der laufenden Anlage derzeit ausfällt.
