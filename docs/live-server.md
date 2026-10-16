# Lesende Bestandsaufnahme des p4d-Servers

Untersucht am 16.10.2026 über den vom Benutzer bereitgestellten SSH-Zugang. Es wurden ausschließlich Dateien, Quellcode, Prozess-/Dienstmetadaten und begrenzte vorhandene Logbereiche gelesen. Kein Dienststart/-neustart, keine Konfigurationsänderung, keine Installation und kein Öffnen des seriellen Ports.

## Version und Beleggrenzen

| Beleg | Ergebnis |
| --- | --- |
| Quellcheckout | Commit `1bc324dc46296a6bd1f8bbeffe2527efe3da2446`, keine getrackten lokalen Änderungen |
| Versionsdefinition im Checkout | p4d `0.10.2`; `VERSION_DATE` = `03.10.2024` |
| Binärdatei am `ExecStart`-Pfad | enthält die Versionskennung `0.10.2-GIT1bc324d`, offline aus Strings gelesen |
| Laufender Dienst | `p4d` ist aktiv/running |
| Abgleich ausgewählter Quellen | 21 gelesene Quelldateien entsprechen bytegenau den Git-Objekten des genannten Commits |
| Paketmetadaten | kein Paket namens `p4d` über `dpkg-query` registriert |

Quellbeleg für die Version: [HISTORY.h im installierten Stand](https://github.com/vgarcia007/linux-p4d/blob/1bc324dc46296a6bd1f8bbeffe2527efe3da2446/HISTORY.h#L8). Der Commit liegt bereits in der Historie unseres unverändert gepinnten Referenz-Submoduls; er ist lokal mit `git show 1bc324dc46296a6bd1f8bbeffe2527efe3da2446:<Pfad>` zugänglich.

**Grenze:** Das Lesen von `/proc/<PID>/exe` und der Prozessumgebung war mit dem SSH-Konto nicht erlaubt. Die Versionskennung wurde deshalb aus der Datei am Dienstpfad gelesen. Quellcheckout, Dienstpfad-Binärdatei und laufender Dienst ergeben einen konsistenten Stand; ein bytegenauer Abgleich mit dem tatsächlich geladenen Prozessabbild wurde nicht durchgeführt. Die Binärdatei wurde nicht ausgeführt, auch nicht mit einem Versionsflag.

## Betriebssystem, Zeit und Anschluss

- Die Bestandsaufnahme erfolgte auf einem Linux-Host. Konkrete Betriebssystemversion und Hostinventar bleiben im lokalen Betreiberkontext erhalten.
- Hostzeitzone `Europe/Berlin`, über `timedatectl` ermittelt. Das ergänzt die zuvor nur als Abkürzung bekannte SQL-Systemzeitzone.
- Die Locale einer SSH-Befehlsumgebung belegt nicht die Locale des laufenden p4d-Prozesses. Persönliche Umgebungseinstellungen werden nicht veröffentlicht.
- Laut Benutzer ist der RS232-USB-Adapter unter `/dev/ttyUSB0` angeschlossen. Die Existenz des Gerätepfads wurde per `stat` bestätigt. Weder Portinhalt noch termios-Einstellungen wurden abgefragt oder geändert.

Heizungsmodell und Steuerungsfirmware sind weiterhin nicht belegt. Die Softwareversion `0.10.2` bezeichnet p4d, nicht die Firmware der Heizung.

## Vergleich mit unserer jüngeren Quellreferenz

Die ursprüngliche Bestandsanalyse verwendet weiterhin `4d1176c4a9081893e4c2cc27a535bb2bc4737d0a` / p4d `0.11.7`. Dieser Pin wurde nicht verändert. Für tatsächliche Installationskompatibilität ist nun zusätzlich der ältere Stand `0.10.2` maßgeblich.

- `p4io.c`, `p4io.h`, `service.c`, `service.h` und `htdocs/menu.js` sind zwischen beiden Commits bytegleich. Die zentrale Telegrammlogik und die bisher beschriebenen Menütypen stammen also auch aus dem installierten Quellstand.
- Die Funktion `crc` in `lib/common.c` ist identisch, obwohl die umgebende Datei Änderungen enthält.
- In `specific.c` sind `initMenu`, `updateParameter`, `performMenuByParent`, `performParStore` und `performTimeParStore` identisch. Die zuvor dokumentierten Schreibabläufe und statischen Befunde gelten damit ebenfalls für den installierten Quellstand.
- Serielle Infrastruktur und Pollingumgebung haben sich geändert. Im alten Stand besitzt `Serial` bereits den Default `B57600`, während der neuere P4d-Konstruktor die Baudrate explizit übergibt. Der alte serielle Pfad speichert/restauriert termios und verwendet `tcflush`; die jüngere Referenz leert durch Lesen und hat zusätzliche Konfigurationspfade. Diese Unterschiede beim späteren Transportplan berücksichtigen.

Quellen: [alter serieller Transport](https://github.com/vgarcia007/linux-p4d/blob/1bc324dc46296a6bd1f8bbeffe2527efe3da2446/lib/serial.c), [alter Serial-Header](https://github.com/vgarcia007/linux-p4d/blob/1bc324dc46296a6bd1f8bbeffe2527efe3da2446/lib/serial.h), [alte Heizungsfunktionen](https://github.com/vgarcia007/linux-p4d/blob/1bc324dc46296a6bd1f8bbeffe2527efe3da2446/specific.c).

## Datenbankabgleich mit der richtigen Version

Das aktive Dictionary des installierten Commits wurde mit dem bereits gelesenen Live-Schemasnapshot verglichen. Für **alle Anwendungstabellen und deren Spaltennamen, SQL-Typen und Primärschlüsselkennungen** wurden keine Abweichungen gefunden. Nullbarkeit, Defaults, Fremdschlüssel und alle Indexeigenschaften sind dadurch nicht vollständig verglichen.

Die zuvor beobachteten Unterschiede zum neueren Dictionary sind damit erklärt: `invert`, fehlendes `parameter`, fehlende Peak-Zeitspalten und die aktive Tabelle `scripts` gehören zum älteren Stand. Zusätzlich heißt das interne Dictionaryfeld für die physische Spalte `calibration` im alten Stand `CALIBRATION`, im jüngeren `SETTINGS`; der physische Name allein belegt keine identische fachliche Verwendung.

Quellen: [Dictionary 0.10.2](https://github.com/vgarcia007/linux-p4d/blob/1bc324dc46296a6bd1f8bbeffe2527efe3da2446/configs/database.dat), [bereinigtes Live-Schema](live-schema.json), [ursprünglicher Schemaabgleich](live-database.md). Die neue Anwendung soll das vorhandene Schema unterstützen; eine Angleichung der Live-DB an 0.11.7 ist nicht erforderlich und nicht autorisiert.

## Vorhandene Protokolllogs

Die letzte Journalstichprobe enthielt keine Hex-Telegramme. Drei vorhandene Dateilogs, einschließlich zweier gzip-Rotationen, waren dagegen lesbar. Gelesen wurden bei der aktuellen Datei der Anfang (höchstens 64 KiB) und das Ende (höchstens 1 MiB), bei jeder gzip-Datei höchstens die ersten 4 MiB nach Dekompression. Überlappungen und wiederholte Logeinträge können in diesen Ausschnitten vorkommen; aus Stichprobenzahlen wird keine Ereignishäufigkeit abgeleitet.

**Beobachtung:** Die Ausschnitte enthalten empfangene `0x39`-Frames mit demaskierter Länge 5, also vier Nutzdatenbytes und Prüfsumme. Frame-Länge, Maskierung und Prüfsumme stimmen bei der Offlineprüfung. Dieses Layout entspricht den von `setParameter` gelesenen Antwortfeldern Adresse + Wert. Die umgebenden Zeilen melden fehlgeschlagene Statusabfragen und teilweise unerwartete weitere Bytes. Es gibt außerdem prüfsummengültige `0x47`-Frames.

**Nicht belegt:** Ein vollständiger Zusammenhang mit einem gesendeten Parameterschreibbefehl. Die geprüften Ausschnitte enthalten keine vollständige Folge aus Vorabfragen, Request, beiden Schreibantworten und Nachlesen. Die einzelnen Frames beweisen weder die genaue Bedeutung der zwei Antworten noch, welcher Teilnehmer den zugehörigen Vorgang ausgelöst hat. Verspätete Antworten oder konkurrierender Zugriff sind mögliche Erklärungen, bislang keine Diagnose.

**Folgerung für den Entwurf:** Startkennung und Prüfsumme allein reichen nicht aus, um eine Antwort einer Statusabfrage zuzuordnen. Der spätere Worker muss unerwartete Antwortbefehle, veraltete Daten und mehrteilige Transaktionen explizit behandeln. Wie der Bestand `0x39`-Antworten liest, ist in [parameter-menu.md](parameter-menu.md) dokumentiert.

Die Rohlogs, deren Kontext und eventuell enthaltene Betriebswerte bleiben lokal unter `.local/` und werden nicht eingecheckt. In dieser Bestandsaufnahme wurde keine neue Heizungsinteraktion für Mitschnitte ausgelöst.

## Ergänzung: alte Weboberfläche

Der angebotene manuelle Schreibversuch ist vorerst ausgesetzt, weil die alte Weboberfläche laut Benutzer nicht richtig funktioniert. Ein anschließender lesender Servercheck ergab:

- HTML-Einstieg und alle 42 lokal eingebundenen JS-/CSS-Dateien liefern HTTP 200.
- Der WebSocket-Upgrade mit Subprotokoll `p4d` liefert HTTP 101. Es wurden keine Anwendungsnachrichten oder Logins gesendet; damit ist nur der Verbindungsaufbau geprüft.
- Die zentralen Dateien `main.js`, `menu.js`, `websocket.js`, `const.js` und `setup.js` stimmen mit 0.10.2 überein und bestehen eine lokale Syntaxprüfung mit Node.
- Im begrenzt gelesenen neuen Logbereich wurden keine passenden Anmelde-/Rechte-, SQL-, Statuskommunikations- oder langen Loop-Fehler gefunden.

Eine Browserlaufzeitstörung, ein Zugriffs-/Proxyproblem auf dem Weg vom Browser zum Server oder ein Fehler der Anwendungsnachrichten sind damit weder bestätigt noch ausgeschlossen. Das konkrete Fehlerbild im Browser fehlt noch. Der Check hat weder Konfiguration noch Logstufe geändert und den seriellen Port nicht geöffnet. Er liefert noch keinen realen Parameterschreibmitschnitt.

## Ergänzung: Browserbefund und Reconnect-Schleife

Der Benutzer hat inzwischen den Browserablauf beschrieben: Der Socket öffnet sich wiederholt, zwischendurch kommen Systemdaten an. Beim Wechsel ins Menü und nach `initmenu` erscheinen fortlaufend Reconnect-Warnungen und teilweise „closed before the connection is established“. Außerdem ist eine nicht näher ausgeführte Exception an `websocket.js:44` protokolliert. Der rohe Browserdump mit Betriebsdaten wird nicht ins Repository übernommen.

Belegter Codepfad im installierten 0.10.2-Stand:

- [main.js:139](https://github.com/vgarcia007/linux-p4d/blob/1bc324dc46296a6bd1f8bbeffe2527efe3da2446/htdocs/main.js#L139): `updateSocketState` erzwingt nach vier Sekunden ohne empfangenes Anwendungs-Ping `socket.reopen()`. Das ist zusätzlich zum automatischen Reconnect des WebSocket-Wrappers aktiv.
- [main.js:325](https://github.com/vgarcia007/linux-p4d/blob/1bc324dc46296a6bd1f8bbeffe2527efe3da2446/htdocs/main.js#L325): Erst das empfangene Ereignis `ping` aktualisiert den betreffenden Zeitstempel regulär. Ein erfolgreicher WebSocket-Handshake allein beweist diesen Nachrichtenfluss nicht.
- [daemon.c:1760](https://github.com/vgarcia007/linux-p4d/blob/1bc324dc46296a6bd1f8bbeffe2527efe3da2446/daemon.c#L1760): `meanwhile` erzeugt die Anwendungs-Pings und dispatcht anschließend die Clientanfragen synchron.
- [specific.c:1593](https://github.com/vgarcia007/linux-p4d/blob/1bc324dc46296a6bd1f8bbeffe2527efe3da2446/specific.c#L1593): Der Befehl `initmenu` führt `initMenu()` synchron aus; die Funktion liest die Menüeinträge seriell und schreibt sie in die DB. Während dieses Aufrufs wird nicht erneut in die äußere Ping-Schleife zurückgekehrt.
- [websocket.js:40](https://github.com/vgarcia007/linux-p4d/blob/1bc324dc46296a6bd1f8bbeffe2527efe3da2446/htdocs/websocket.js#L40): `send` prüft in seinem direkten Sendepfad nicht den `readyState`. `reopen` ersetzt die Verbindung; der Queuezustand wird dabei nicht explizit neu aufgebaut. Das erlaubt einen Sendefehler während eines Verbindungswechsels, erklärt aber die konkrete Exception ohne deren Typ nicht abschließend.

**Einordnung:** Ein langer Heizungs-/Menüaufruf kann die Anwendungs-Pings verzögern und dadurch den Vier-Sekunden-Watchdog auslösen. Die Browserfolge passt zu dieser Kopplung und zu nachgelagerten Verbindungswechseln. Eine vollständige Ursachendiagnose jedes Abbruchs liegt weiterhin nicht vor; Netzwerk-/Proxyeinflüsse und weitere Fehler sind damit nicht ausgeschlossen. Aus dem Browserdump ist kein Parameterschreibvorgang belegt; `initmenu` ist eine Menüinitialisierung.

**Anforderungen an Fröling Bridge:** API und Verbindungsüberwachung müssen unabhängig von langen seriellen Aufgaben reagieren. Menü und Messwerte aus einem Cache mit expliziter Aktualität bereitstellen; lange Discovery als verfolgbaren Auftrag ausführen. Der Browser benötigt einen eindeutigen Verbindungszustand, kontrollierten Reconnect mit begrenztem Backoff und abgebrochene/veraltete Requests dürfen nicht als aktuelle Ergebnisse erscheinen. Schreibaufträge dürfen nach einem Verbindungsabbruch nicht automatisch erneut gesendet werden. Konkrete HTTP-Endpunkte und die Umsetzung der Jobverwaltung werden im API-Arbeitspaket festgelegt.

Es wird daraus keine Reparatur des alten Systems abgeleitet. Der manuelle Schreibtest bleibt ausgesetzt; der neue Offline-Kern und der folgende DB-/API-Aufbau können unabhängig davon weiterentwickelt werden.

## Nächster Schritt

Die Version und das passende Schema waren ausreichend eingegrenzt, um den inzwischen [implementierten Offline-Python-Protokollkern](python-core.md) zu planen. Für dessen Tests benötigen wir zunächst Framing, Prüfsumme, signed/unsigned-Werte, fragmentierte Eingaben und die Ablehnung unpassender Antworten. Die Schreibzustandsmaschine bleibt vorerst auf Codebefunde und Simulation begrenzt. Ein realer vollständiger Schreibmitschnitt und Modell/Firmware fehlen weiterhin; dafür einen gesonderten, mit dem Benutzer abgestimmten nächsten Schritt wählen, statt selbst einen Parameter zu ändern.
