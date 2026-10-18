# Entscheidungsprotokoll

Hier stehen dauerhafte Vereinbarungen, keine ungeprüften Annahmen. Neuere Entscheidungen ergänzen oder ersetzen ältere ausdrücklich.

## 16.10.2026 — Richtung und erster Arbeitsumfang

- Eigenständiger Python-Nachbau mit Schwerpunkt Heizung lesen, Parameter schreiben, dokumentierte API und modernes Servicemenü.
- Zuerst Bestandsanalyse und Dokumentation; noch kein Python-Heizungsprototyp.
- Bestehende MariaDB samt Historie weiterführen; Original-p4d als Rückfalloption erhalten. Dauerhafter Parallelbetrieb zweier Logger ist nicht das Standardziel.
- Charts, Dashboards und weitere Integrationen zunächst nachrangig.
- Protokollverhalten aus Originalcode ableiten, Annahmen und unbekannte Felder ausdrücklich kennzeichnen. Tatsächliche Hardwarekompatibilität erst mit echten Belegen bestätigen.

## 16.10.2026 — Name, Herkunft und Sicherung

- Name und Remote: `froeling-bridge`, `git@github.com:vgarcia007/froeling-bridge.git`, zunächst privat.
- Benutzer beauftragt Einrichtung, Commit und Push; zusammenhängende Arbeitsstände sollen im Remote gesichert werden.
- p4d als unverändertes, gepinntes Git-Submodul einbinden; Referenzcommit `4d1176c4a9081893e4c2cc27a535bb2bc4737d0a`.
- README würdigt Jörg Wendel (horchi), die Mitwirkenden und p4d als Grundlage. Keine offizielle Verbindung zum Originalprojekt oder Hersteller behaupten.
- `AGENTS.md`, `project-context.md` und dieses Protokoll dienen der Fortsetzung in neuen Sessions.
- Zugangsdaten, Rohberichte, Datenbankdumps und lokale Mitschnitte nicht ins Repository aufnehmen; für deren Sicherung wird keine Git-Backup-Zusage gemacht.

## 16.10.2026 — Zugang zur laufenden Datenbank

- Benutzer stellt `live-db.con` bereit, ausdrücklich nur zum lesenden Umsehen.
- Keine Änderungen an Live-Daten, Schema, Rechten oder Server; keinen p4d-Daemon dagegen starten.
- Struktur- und eng begrenzte Metadatenabfragen zulässig. Verbindung zusätzlich über eine Read-only-Transaktion absichern.
- Nur bereinigte Schema-/Kompatibilitätsbefunde tracken. Private Rohdaten lokal ignorieren.
- Die DB-Zugriffserlaubnis enthält keine Freigabe für Heizungs-Schreibversuche oder Hoständerungen.

## 16.10.2026 — Lesender SSH-Zugang und installierter Zielstand

- Benutzer stellt `live-server-ssh.con` für die angebotene lesende Bestandsaufnahme bereit. Keine Änderungen am Live-Host, Dienst oder Port.
- Benutzer bestätigt den RS232-USB-Adapter auf dem Live-Server unter `/dev/ttyUSB0`; kein paralleles Öffnen zu p4d.
- Als vorhandener Zielstand ist nun p4d 0.10.2 / Commit `1bc324dc46296a6bd1f8bbeffe2527efe3da2446` belegt (Quellcheckout und Versionskennung der Dienstpfad-Binärdatei). Beleggrenzen stehen in `live-server.md`.
- Der jüngere Referenz-Submodul-Pin bleibt erhalten. Für DB-Kompatibilität das tatsächliche 0.10.2-Schema verwenden, keine automatische Migration auf den jüngeren Stand.
- Existierende Logausschnitte nur offline analysieren. Kein neuer Schreibtest und keine Änderung der Logstufe.

## 16.10.2026 — Autonome Umsetzung des Offline-Kerns

- Benutzer beauftragt nach dem Versions-/Schemaabgleich die Umsetzung des Offline-Protokollkerns und Simulators, möglichst ohne weitere Interaktion. Die frühere Beschränkung auf reine Dokumentation ist für diesen Baustein aufgehoben.
- Python >=3.9 mit Standardbibliothek und setuptools-Paketierung; keine externen Laufzeitabhängigkeiten und keine Vorentscheidung zu HTTP-/DB-Frameworks.
- Exklusive vollständige Transaktionen mit Gesamtdeadline. Nach Protokoll-/Transportfehlern Sitzung sperren; keine automatische Wiederholung oder blindes Leeren des Streams.
- Änderungserfolg nur nach passend interpretiertem Nachlesen. Nach begonnenem Schreibversuch ohne vollständige Bestätigung `WriteOutcomeUnknown`; abweichendes gültiges Nachlesen separat als `WriteVerificationError`.
- Zeitprogramme mit nullbasiertem Index 0..3, frischem Einlesen aller vier Intervalle und expliziten Zehn-Minuten-Schritten; keine implizite Rundung.
- Antwortcodes des Simulators sind eine unbestätigte Echo-Konvention und austauschbar. Kein physischer TTY-Transport; alle Demo-/Testdaten synthetisch. Keine Änderung der Live-Zugriffsgrenzen.

## Noch nicht entschieden

Produktionsauthentifizierung, endgültiger Deploymentweg und Lizenz für neue Projektteile. Framework, DB-Treiber und API-Vertrag für den lokalen Prototyp wurden inzwischen wie unten beschrieben entschieden.


## 16.10.2026 — Kontinuierliche Datensammlung und lokale API

- Benutzer beauftragt Umsetzung des erweiterten Plans: kompatible DB-Anbindung, kontinuierliche Sammlung/Speicherung, HTTP-API und simuliertes Parameterschreiben; modernes Browsermenü folgt.
- Ein Schreibmitschnitt aus dem alten Webinterface ist keine Voraussetzung. Code ist die Implementierungsgrundlage; unbekannte Antwortdetails ausdrücklich kennzeichnen und später gesondert an der Hardware prüfen.
- Python >=3.9 erhalten. Flask >=3.1,<3.2, Waitress >=3,<4 und PyMySQL >=1.1,<1.2 im optionalen Service-Extra. Protokollkern bleibt unabhängig.
- Lokaler Prototyp bindet ausschließlich an 127.0.0.1; kein Debugger/Reload. Drei getrennte Modi demo/demo-db/database. Bestandsansicht ausschließlich lesend, kein vermischter Live-/Simulatorbetrieb.
- Aufzeichnungsintervall standardmäßig 60 Sekunden, keine Überlappung oder Aufholbursts. Einzelner Heizungsbesitzer mit vollständigen Transaktionen und FIFO; Datenbankarbeit getrennt davon.
- Lokales Schreiben ausschließlich auf benannte Testdatenbanken unter Loopback. Kein Produktivwriter, keine automatische Migration und keine Initialisierung beim Dienststart. Testwerkzeug erzeugt bekannten Schemaausschnitt und synthetische Fixtures ausdrücklich separat.
- samples und peaks transaktional; Sensoridentität, bereits skalierte Werte, S-Kennung, lokale Europe/Berlin-Zeit und Unix-Metafelder erhalten. Schlüsselkonflikte aktualisieren Werte und updsp, erhalten inssp. Kein Daten-Nachlieferungspuffer; unklare Commit-Ergebnisse nicht wiederholen.
- Unterstützte Sammlung: VA, DO/DI/AO, UD 1–3; weitere Typen sichtbar überspringen. Aggregation/Bereinigung vor vollständiger Ablösung gesondert implementieren. Bestehende Historie/Metadaten und Fremdintegrationen nicht verändern.
- /api/v1 mit dokumentiertem OpenAPI-Vertrag. Jobs queued/running/completed/failed, Schreibbestätigung weiterhin ausschließlich durch Nachlesen. FIFO 64, maximal 1.000 flüchtige Jobresultate; keine Wiederholung nach Neustarts.
- Kein Zugriff auf Live-DB/-Server und kein Portzugriff im Implementierungspaket. Keine neue Freigabe für produktive Schreibtests oder Dienstaktionen abgeleitet.


## 16.10.2026 — Webmenü und begrenzter Hardwaretest

- Benutzer bestätigt Umsetzung des Plans und wählt ersten Hardwarewechsel ausschließlich lesend mit separater Test-Aufzeichnung. Einmalige administrative Einrichtung durch ihn, danach feste root-Helferaktionen statt weiterer allgemeiner sudo-Freigabe.
- Webmenü direkt aus Flask mit HTML/CSS/JavaScript; keine externe UI-Plattform, kein Node-Build. Explizite Quellen/Fähigkeiten und frische Werte, bestätigte Simulator-Schreibabläufe, keine Wiederholung nach Verbindungsabbruch.
- Linux-TTY-Adapter aus Standardbibliothek: 57600 Baud/8N1, keine Flusskontrolle, flock/TIOCEXCL, Deadline/Teilübertragungen, kein stilles Flush. Original-p4d muss vorher vollständig beendet und Portfreigabe festgestellt sein.
- hardware-read verbietet Schreibjobs und Client-Schreibmethoden; ein zusätzlicher Transportfilter prüft vollständige Frames und Read-Payload-Längen vor dem ersten physischen Byte. Echtes Schreiben bleibt gesondertes späteres Arbeitspaket.
- Original-DB nur Metadaten lesend, Messpunkte in jeweils neue Test-DB auf separatem lokalen MariaDB-Container. Keine produktive Historienfortschreibung in diesem Test, keine Zusammenführung danach.
- Installation als versioniertes Release unter /opt, geschützte Konfiguration, neuer Dienstbenutzer. Standardports 8000 (Simulator) und 8001 (Hardwaretest), ausschließlich Loopback und SSH-Tunnel.
- Testfenster 15 Minuten. Rückkehrtimer vor p4d-Stop scharfstellen; OnFailure und RuntimeMaxSec ergänzen ihn. Protokoll-/DB-Fehler und Sammlerdeadline 120 Sekunden brechen früher ab. Original-Autostart bleibt enabled, Hardwaretest ohne Boot-Aktivierung.
- Rückkehr: Testdienst vollständig stoppen, exklusiven Port freigeben, Originaldienst starten, neue Messpunkte ausschließlich lesend nachweisen. Keine pauschale Garantie bei Host-/Hardwareausfall oder fremdem Portbesitzer; Fehler sichtbar melden.
- Benutzerautorisiert sind jetzt auch das Bereitstellen des privaten Pakets auf dem Host und später der konkrete Helferablauf nach erfolgreicher Einrichtung. Der fehlende administrative Zugriff wird nicht umgangen. Tatsächlicher Heizungs-/Original-DB-Schreibzugriff bleibt ausgeschlossen.

## 16.10.2026 — Einrichtung nach Abbruch fortsetzen

- Fehlgeschlagene Einrichtung ist kein fertiges Release. Identischer Release-Marker erlaubt kontrolliertes Fortsetzen; fremde oder abweichende Ressourcen bleiben geschützt. Ein Upgrade wird daraus nicht abgeleitet.
- Fehlende venv-Unterstützung vor dauerhaften Installationsschritten erkennen. Wiederholung erhält Passwörter, Testvolume und vorhandene Testzeilen. Keine automatische Bereinigung als Reparatur.
- Installationshilfen liegen im privaten Bundle, ohne Änderung des Anwendungswheels. Der vorhandene 0.3.0-Teilstand kann dadurch mit unverändertem Release-Marker fortgesetzt werden.

## 16.10.2026 — Direkter LAN-Zugriff

- Benutzer verlangt direkten Zugriff über die Server-IP. Webmenü/API standardmäßig 0.0.0.0, Vorschau 8000, Hardwaretest 8001; SSH-Tunnel ist optional. CLI --host erlaubt abweichende Bindung. Testdatenbank bleibt Loopback.
- Administrative Arbeiten erfordern vorhandene Autorisierung und passende Rechte; die konkrete Zugriffslage bleibt privat. Notwendige Einrichtungsschritte als prüfbare Aktion vorbereiten.

## 16.10.2026 — Prozessprüfung vor Abschalten

- Reale Prozessinspektion muss bereits vor p4d-Stop funktionieren. Fuser-Aufruf ohne nicht unterstütztes „--“ bei festem absolutem Pfad.
- Regression prüft echten fuser-Prozess mit gehaltenem/freiem temporärem Objekt. Simulierte Koordinator-/Ersatzdiensttests allein belegen nicht die Kompatibilität externer Kommandos auf dem Zielhost.
- Nach fehlgeschlagener Rückkehr Originalbetrieb zuerst wiederherstellen und Aufzeichnung bestätigen; kein weiterer Hardwaretest vor Anwendung der Korrektur.

## 16.10.2026 — Bewährten p4d-Leseablauf übernehmen

- Benutzer unterstreicht den zuverlässigen bisherigen p4d-Lesebetrieb und verlangt keine unnötige Zusatzkomplexität. Lesesequenzen und Datenübernahme am Original ausrichten; Abweichungen ausdrücklich begründen.
- Zeitprogramme: ursprünglicher Check, First/Next und Speicherung nach Adresse; wiederholte Adresse ersetzt wie beim Original den vorherigen Eintrag. Auf dem Zielhost beobachtetes Antwortprofil 43 -> 42 ausdrücklich konfigurieren, statt alle Antwortcodes pauschal zu akzeptieren.
- Frame-/CRC-Prüfung, Schreibsperren und begrenzte Laufzeit beibehalten. Noch nicht beobachtete Firmwareeigenschaften nicht als gesichert ausgeben.

## 16.10.2026 — Vollständige Menüzuordnung und Cache als Funktionsumfang

- Benutzer fordert verbindlichen p4d-Funktionsabgleich und will vorhandene Originalfunktionen nicht wiederholt einfordern müssen. Namen, Menüpfade, Zeitadressen/Tage und Cachebedienung sind Teil des Nachbaus; moderne Darstellung ersetzt diese Zuordnung nicht.
- Zeitprogramme über Originalmenü benennen und nur konfigurierte erreichbare Geräte anzeigen. Rohgruppen bleiben in der API vollständig. Geräte-Zeiten aus dem Menü führen zur entsprechenden Woche.
- Gemeinsamer Cache mit automatischem Erstlesen, bewusstem Aktualisieren und Lesezeitpunkt; im lesenden Testbetrieb private persistente Datei statt Änderungen der Original-DB. Fehler behalten den letzten vollständigen Stand. Kein zusätzlicher manueller Erstleseschritt.
- Tatsächliches 15-Minuten-Lesefenster mit 195 Testmesspunkten und automatischer bestätigter Rückkehr erfolgreich. Hardware-Schreiben weiterhin getrennt und nicht freigegeben.


## 16.10.2026 — Produktive Aufzeichnung freigegeben

- Benutzer bestätigt ausdrücklich die Messwertaufzeichnung in der bestehenden p4d-Datenbank und dauerhaften Betrieb. Dies ersetzt die frühere Nur-Lesen-/Testfenstergrenze für genau diesen Aufzeichnungspfad.
- Eigener Modus hardware-live und eigenes Release 0.4.0. Gemeinsamer getesteter samples/peaks-Writer, explizite Aktivierung, Schema-/Schlüssel-/InnoDB-Prüfung ohne Migration. Metadaten lesen unverändert read-only. Keine Lösch-/Aggregationsroutine hinzufügen.
- Dauerbetrieb auf LAN-Port 8000 ersetzt dort die Simulator-Vorschau. Eigener Autostart statt p4d, keine RuntimeMaxSec. Originalinstallation und bisheriges Release erhalten.
- Aktivierung mit unabhängigem Fünf-Minuten-Rückkehrtimer; nach zwei Sammelzyklen und nachgewiesenem neuen Originalmesspunkt abschalten. Laufzeitfehler lösen echte Rückkehr zu p4d samt Autostart aus. Keine konkurrierenden seriellen Dienste.
- Die damalige Freigabe bezog sich ausschließlich auf Datenbank-Messwerte, nicht auf Heizungsparameter. Administrative Einrichtung getrennt vorbereiten; persönliche Berechtigungsdetails bleiben privat.


## 17.10.2026 — Eigenständiger Ersatz statt Abhängigkeit vom Altbestand

- Benutzer priorisiert aktuelle Werte und bedienbares Menü für die Versorgung zweier Gebäude. Eigenständiger Erststart auf neuem Rechner mit Discovery ist notwendig; Historie ist nachrangig. Linux-Installationsskript ohne Docker und Weiterbetrieb bei MariaDB-Ausfall sind ausdrücklich gewählt.
- SQLite als private dauerhafte Arbeitsgrundlage, kein Ersatz für die MariaDB-Historie. Beschädigten Katalog erhalten und neu entdecken; unbekannte zukünftige Version nicht überschreiben. Alte Werte behalten ihren Lesezeitpunkt und gelten nach Neustart als gespeichert/veraltet.
- Bestehende Sensor-/Menüadressen beibehalten. Erreichbare unterstützte Messwert-/IO-Zeilen und UD 1–3 sind Erstinstallations-Auswahl, zunächst keine Aufzeichnung; Bestandsauswahl/individuelle Namen übernehmen. Keine selbst gepflegten fachlichen Sensoraliases.
- Optionale MariaDB: automatisch fehlende/leere DB und sechs benötigte kompatible Tabellen erstellen; fremde Teilbestände nicht reparieren, bestehenden Bestand nicht migrieren. Metadaten und Flag-Synchronisation getrennt vom seriellen Worker. DB-Ausfall erzeugt sichtbare Historienlücke, keine Unterbrechung der Live-Bedienung.
- Record-/Abfrageflags lokal sofort gültig, in MariaDB nachholen; keine Änderung weiterer individueller Einstellungen. Verdichtung im Hintergrund um 01:00, begrenzte Tagestransaktionen und Fortschritt, vorhandene Aggregate nicht überschreiben. Angefangene Intervalle nicht verdichten, Text deterministisch vom letzten Wert.
- Hardware-Schreiben nur nach unabhängigem Nachweis für Gerät/Firmware/Operation, Änderungs-/Rückstelltool ohne automatische Wiederholung nach unklarem Ausgang. Installation erzeugt keine Schreibfreigabe. Echte Werte/Testauswahl bleiben gesondert abzustimmen.
- systemd auf neuem Host: Bridge neu starten. Auf bestehendem p4d-Host: Restart=no und unmittelbare OnFailure-Rückkehr, weil reale systemd-Prüfung gezeigt hat, dass automatische Restarts OnFailure verzögern können.
- Noch keine neue Hardware-/24h-Abnahme oder Rootinstallation aus erfolgreichen lokalen Tests ableiten.

## 17.10.2026 — Monitoring hat Vorrang vor Abnahme

- Ein 24-Stunden-Nachweis beobachtet bereits funktionierenden Betrieb; er rechtfertigt keine Unterbrechung des Heizungsmonitorings. Wenn die Bridge keine aktuellen Messwerte liefert, zuerst p4d wiederherstellen. Keine weiteren Umschaltungen vor Fehlerkorrektur.
- Die erste reale 0.5.0-Discovery bleibt bei Sensoren hängen; noch keine erfolgreichen Messzyklen. Simulator-/Installationstests waren kein Beleg für diese Hardwaresequenz. Die genaue Ursache ist noch offen.
- Aktivierung darf Notrückkehr und Status nicht durch ihre eigene lang gehaltene Prozesssperre blockieren. Status liest ohne exklusive Sperre; Rückkehr signalisiert zunächst Abbruch und wartet begrenzt auf die Sperre. Aktivierung prüft den Abbruch und stellt p4d wieder her. Regression prüft echte konkurrierende Dateisperren und Wiederherstellung.

## 17.10.2026 — Discovery-Korrektur 0.5.1

- CHECK und das Überspringen kurzer nicht abschließender Listeneinträge anhand des vollständigen p4d-Aufrufpfades übernehmen. Prüfsummen, fremde Antwortfamilien, Gesamtfristen und Antwortlimit bleiben geprüft. Eine Antwort erhält höchstens zwei Sekunden innerhalb der gesamten Listenfrist; bei Fragmenten nicht neu starten.
- Konkrete Phase/Fehlerklasse und sichere Protokolldetails sichtbar machen; keine beliebigen OS-/DB-Exceptiontexte ausgeben. Bei erstem gemeldeten Startfehler sofortige Rückkehr zum Original, statt weitere Minuten erfolglos neu zu versuchen.
- 0.5.1 ist ein eigenes Release, überschreibt das vorhandene 0.5.0-Verzeichnis nicht. Privates Installationspaket samt kurzem Root-Skript vorbereitet und auf Ziel-Python unprivilegiert geprüft. Reale Discovery bleibt ausstehend; p4d während der Entwicklung aktiv lassen.

## 17.10.2026 — Reale Discovery und fortlaufendes Monitoring

- Tatsächliche administrative Zugriffslage vor freigegebenen Arbeiten prüfen; persönliche Berechtigungsdetails ausschließlich privat dokumentieren.
- Doppelte Sensoradressen entsprechend `initValueFacts` → `addValueFact` als Aktualisierung desselben Sensors behandeln; spätere Metadaten gewinnen, Benutzerflags bleiben erhalten. 161 Wiederholungen auf echter Hardware bestätigt; vollständige Erkennung mit 0.5.2 erfolgreich.
- Unabhängige systemd-Überwachung liest nur HTTP-Cache. Aktueller Status darf ausgebliebene Messwertabfragen nicht verdecken. Bei anhaltendem Live-Ausfall vorhandenes p4d wiederherstellen, auf neuem Host Bridge neu starten; reine Historienstörung löst keine Umschaltung aus. Keine künstliche Störung an der Live-Heizung für diesen Test.
- 24h-Beobachtung erst jetzt bei funktionierenden echten Messwerten im Hintergrund gestartet. Erfolgreicher Dienstneustart ist kein Beleg für vollständigen Hostneustart oder abgeschlossene 24h-Abnahme.

## 17.10.2026 — Schreibumfang aus dem tatsächlichen p4d-Menü ableiten

- Verbindliche Grundlage ist die serverseitige Typauswahl in `performMenuByParent` einschließlich Filter, frischer Editor-Metadaten und `urFullControl`, nicht die allgemeine Liste aller theoretischen Handbetriebsfunktionen. Messwerte und I/O sind im untersuchten Menü nicht bearbeitbar.
- Die sechs normalen Parametertypen sind bereits in Browser und API übernommen; anhand der gepinnten Originalquelle gegen beide Implementierungen prüfen. Menü-ID und daraus gelesene Adresse bleiben gekoppelt. Zeitintervalle sind ein separater Schreibweg.
- p4d-Bearbeitbarkeit ist eine Aussage über den unterstützten Menüpfad, keine eigenständige Zusicherung ungefährlicher Einstellungen. Tatsächliche Hardwarefreigabe und vereinbarter Testwert bleiben vom vorhandenen Codeumfang getrennt. Keine zusätzliche pauschale Funktionssperre aus dem allgemeinen Risikohinweis ableiten.

## 17.10.2026 — Schreibbedienung wie im p4d-Heizungsmenü

- Benutzer bestätigt die Umsetzung ausdrücklich nach Originalvorlage. Derselbe Typumfang und dieselbe automatische Menüzuordnung; keine zusätzlichen pro Parameter selbst zu pflegenden Freigabelisten. Editor mit frischen Metadaten, nativen Zahlengrenzen/Schrittweiten für Typ 07 und direktem Speichern. Zusätzliche Bestätigungsdialoge entfallen.
- Erfolgreiches Nachlesen und kein automatisches Wiederholen nach unklarem Ergebnis bleiben beibehaltene Verbesserungen. Frisches Neuöffnen des Editors ermöglicht nach einer Unklarheit wieder eine bewusste Änderung, wenn die Operation freigegeben ist.
- 0.5.3 zunächst neben laufender 0.5.2 vollständig vorbereitet und geprüft, danach mit Katalog-/Konfigurationsbackup und Rückkehrtimer auf dem Host aktiviert. Reale Parameter bleiben gesperrt, keine Teständerung an der Heizung.

## 17.10.2026 — Reales Parameterschreiben bestätigt und aktiviert

- Benutzer bestätigt den ausgewählten LED-Helligkeitstest: ein Prozentpunkt Änderung, unmittelbar bestätigte Rückstellung. Mit bestehendem Validierungswerkzeug durchgeführt; jeweils zwei `39`-Antworten und frisches `55`-Nachlesen erfolgreich, keine Wiederholung/Protokolländerung nötig.
- Danach normales p4d-Parametermenü über geschützten Geräte-/Firmware-Nachweis für `write_parameter` freigeschaltet. `write_time_range` bleibt gesperrt. Keine beliebigen weiteren Teständerungen aus dieser Freigabe ableiten.
- Exklusiver Portzugriff, privates Zustandsbackup und unabhängiger Rückkehrtimer; nach kurzer Pause wieder Bridge-Monitoring, Historie und Gesundheitsüberwachung aktiv. Langzeitbeobachtung enthält die geplante API-Unterbrechung und ist kein lückenloser 24h-Nachweis.
- Bootet regulär mit Bridge und Gesundheits-Timer; p4d als Rückfall erhalten, regulärer Autostart deaktiviert. Wirksames Host-Drop-in `Restart=no` und OnFailure-Rückkehr lesend bestätigt. Benutzer sagt ausdrücklich, den Rechner jetzt nicht neu zu starten.

## 17.10.2026 — Heizungsfehlerspeicher und vorhandene SQL-Clients

- Benutzer meldet einen unabhängigen SQL-Client und erklärt den Fehlerspeicher für essentiell. Bestehendes Status-Recordflag erhalten, seine genaue SQL-Abfrage separat klären. Korrektur nach Benutzerhinweis: p4d überschreibt das interne Recordflag für UD 1–3 in `applyConfigurationSpecials` immer mit true. Diese Originalregel war zuvor übersehen worden; die sichtbare gespeicherte Auswahl ist dafür unerheblich.
- Fehlerspeicher wie `P4d::afterUpdate` → `updateErrors` regelmäßig lesen und p4d-Zuordnung/Zustandsübergänge übernehmen. Nur vollständige Listen ersetzen den persistenten Cache; GET ist rein lesend. Steuerungseinträge und Dienstfehler klar unterscheiden.
- MariaDB-`errors` separat vom seriellen Worker transaktional abgleichen. ID, Mailzähler, frühere Quittierungen und ältere DB-Historie erhalten. Keine Quittierbefehle an die Heizung, keine künstlichen Fehler erzeugen. Fehler dieses Abgleichs sichtbar machen, ohne Messwerterfassung zu beenden.
- Neue leere Datenbank enthält ab 0.5.4 sieben kompatible Kerntabellen einschließlich `errors`. Vorhandene DB nicht migrieren. Reale Übernahme erst nach separater MariaDB-/Browser-/Installationsprüfung und mit Zustandsbackup/Rückkehrtimer.

## 17.10.2026 — Übersehene Originalregel für UD 1–3 korrigieren

- Benutzerbeobachtung bestätigt: `applyConfigurationSpecials` wird nach Einlesen der Sensorflags aufgerufen und aktiviert intern Status, Betriebsart und Heizungszeit immer. In Referenz-Pin und altem installierten Quellstand 1bc324d nachgewiesen. Frühere gegenteilige Erklärungen und Dokumentation berichtigt.
- Ab 0.5.5 im Standalonebetrieb dieselben drei Werte immer abfragen und als Messpunkte aufzeichnen. Keine gespeicherten Sensorflags dafür ändern, keine Umgehung durch eine neue Status-Tabelle. API/UI zeigen effektive und konfigurierte Aufzeichnung getrennt; automatische Historie kann nicht irreführend abgeschaltet werden.
- Regression vergleicht die Regel mit dem Originalquellcode und prüft erfolgreiche Aufzeichnung bei allen drei ausgeschalteten Flags, ohne deren Änderung. Keine Heizungs-Schreibtests und kein Hostneustart.

## 17.10.2026 — Fehlerspeicher für Mobil und Desktop lesbar darstellen

- Benutzer meldet unlesbare Fehlerliste auf Mobilgerät. Tatsächliche Browserprüfung bestätigt dieselbe Ursache auch am Desktop: kompletter Fehlerinhalt stand in der Symbolspalte des Menü-Rasters.
- Eigenes Layout für Fehlereinträge: volle Titelbreite, beschrifteter Zustand, semantische Datumsliste; mobile Zeitpunkte untereinander, Desktop nebeneinander. Sehr schmale Kopfzeilen umbrechen lassen. Keine Änderung der Fehlerdaten oder Hardwareabfragen.
- Browserregression bei 320/390/768/1440 Pixel mit langen fiktiven Meldungen und allen drei Zuständen. Seitenüberlauf gegen tatsächlich eingestellte Breite prüfen, da mobile Auto-Skalierung eine bloße Prüfung gegen innerWidth verfälschen kann. Darstellung und automatische UD-Aufzeichnung gemeinsam als 0.5.5 ausrollen.

## 17.10.2026 — Fehlerhistorie statt ausschließlich Steuerungsspeicher anzeigen

- Benutzer bemerkt zu Recht die kleinere Fehlerliste. Lesender Vergleich: 86 MariaDB-Zeilen gegenüber 16 Steuerungsvorkommnissen. Original `performErrors` liest `selectAllErrors` aus MariaDB (`time1 desc`); die bisherige Route/GUIdarstellung bildete nur den aktuellen Controllercache ab.
- Ab 0.5.6 `/errors` mit Default `source=auto`: bei konfigurierter DB vollständige gespeicherte Historie in Seiten, sonst Steuerungscache. `source=history` verlangt MariaDB (503 bei Ausfall), `source=controller` wählt ausdrücklich den bisherigen Cache. Alle GETs ohne zusätzliche Heizungsabfrage.
- Quelle, Gesamtzahl und Seitendaten sind Teil des Vertrags. Default 100, maximal 1000 pro Seite; Sortierung `time1 desc,id desc`. GUI zeigt Quelle/Gesamtzahl und Seitennavigation. Keine Bestandsdaten ändern oder löschen.
- Automatischer DB-Ausfall-Rückfall muss ausdrücklich als unvollständige Steuerungsansicht markiert sein (`fallback`, `history_available`, `history_error`). Steuerungs-Lesezeit und SQL-Lesezeit auseinanderhalten, bisherigen Abgleichstatus separat ausweisen.

## 17.10.2026 — Fehlerzustände aktualisieren und alte unvollständige Einträge einmalig entfernen

- Drei alte unvollständige DB-Vorkommnisse aus 2025 sind im begrenzten Steuerungsspeicher nicht mehr enthalten. Gespeicherter Zustand „gekommen“ allein darf nicht als aktuell bestätigte Störung erscheinen. API/UI ergänzen Aktivität mit true/false/null und Beleggrund, ohne End-/Quittierzeitpunkte zu erfinden.
- Benutzer autorisiert anschließend ausdrücklich die einmalige Löschung genau dieser drei alten Einträge. Vorher private vollständige Sicherung, enge Prüfung der betroffenen IDs/Zeiten/Zustände gegen frischen Steuerungscache, parametrisierte transaktionale Löschung; 83 Einträge verbleiben. Keine allgemeine automatische Bereinigung einbauen, keine anderen Fehler löschen.
- Benutzer betont neue Statusmeldungen: bestätigte Übergänge müssen denselben Datensatz aktualisieren. Bisherige Guard-Regel konnte fehlende Zeitpunkte bei bereits übereinstimmendem Zustandsnamen nicht ergänzen. Zeitfelder aus echten Meldungen unabhängig davon aktualisieren; bestehende IDs/Mailzähler und bereits bestätigte Quittierung erhalten. Regression für jeden Übergang, Reparatur fehlender Zeitpunkte, erneutes Lesen und Abgrenzung neuer Vorkommnisse.


## 18.10.2026 — Verbindlicher API-Dauerbetrieb, keine automatische p4d-Übernahme

- Benutzer beauftragt Entfernung aller p4d-Cronjobs und erklärt die API zum dauerhaften Produktionsdienst. Einziger aktiver Root-Neustart nach privater Vollsicherung entfernt, andere Jobs erhalten. Bridge anschließend wieder exklusiv aktiviert, aktuelle Messwerte und DB-Aufzeichnung geprüft.
- Vorhandensein einer p4d-Installation und automatische Rückkehr werden getrennt: optionales Installerfeld `automatic_p4d_fallback`, ohne Feld bisheriges Verhalten. Produktiver Host setzt false, manueller Rückfall bleibt erhalten. Health-Guard und systemd stellen künftig Bridge wieder her; Rescue darf auch während Aktivierung kein Abbruchsignal mehr setzen. Startfehler schalten bei dieser Richtlinie nicht auf p4d um.
- Verwaltungsdateien ohne Neustart des laufenden API-Prozesses aktualisiert, Installer erhält Richtlinie; keine Änderungen an Heizungsparametern, Sensorflags oder Hardware-Schreibfreigabe. Kein Hostneustart/Live-Ausfalltest. Keine geplanten Unterbrechungen ohne neuen Auftrag; automatische Wiederherstellung ist keine Zusicherung hundertprozentiger Verfügbarkeit.


## 18.10.2026 — Eigene Funktionsübersicht statt falschem Hydraulikschema

- Benutzer erklärt das bisherige p4d-Schema für falsch und beauftragt eine eigene Seite mit zusammengehörigen Pumpen, Temperaturen, Schwellwerten und Gerätegruppen. Zugehörigkeit aus erreichbaren Geräte-Menüpfaden ableiten; physische Verrohrung und vollständige Regelungsursachen nicht erfinden. Allgemeine Pumpenausgänge ohne klare Zuordnung separat und Mehrdeutigkeiten unbekannt darstellen.
- Benutzer wählt zusätzliche gezielte regelmäßige Messwertabfragen. Dafür ausdrückliche lokale Aktivierung über bestehenden Sensor-Konfigurationspfad; kein GET-Nebeneffekt und keine automatische Änderung von Recordflags. Ungeprüfte Katalogpräsenz bleibt sichtbar von tatsächlichem Einbau getrennt.
- API um Komponenten-Snapshot, Aktivierung und lesenden Komponentenjob ergänzen. Persistenter Zeitstempelcache, pro Komponente geteilte Aktualisierung, begrenzte Parallelität und Einzelabfragen über bestehenden seriellen Worker. Seite zunächst ausschließlich zur Übersicht; Schreiben im bestehenden Servicemenü.
- 0.6.0 im Checkout implementieren, isoliert testen und als getrennte strikt lesende API-Vorschau bereitstellen. Laufende 0.5.7 nicht für diese Umsetzung unterbrechen oder ausrollen; tatsächliche produktive Aktivierung bleibt eigener Auftrag. Zusatzfreigabe erweitert den bisherigen Ausschluss einer solchen fachlichen Übersicht, nicht den Umfang historischer Charts oder anderer p4d-Nebenfunktionen.


## 18.10.2026 — Produktiver Rollout der Anlagenübersicht

- Benutzer autorisiert nach Erklärung des kurzen Neustarts ausdrücklich das Live-Schalten. 0.6.0 kontrolliert nach Sicherung aktiviert, 38 zusätzliche Abfragesensoren ohne Änderung von Historienflags ergänzt und 112 Schwell-/Einstellungswerte rein lesend initialisiert. Neue Seite am bisherigen API-Host unter `/anlage` verfügbar.
- Fehlgeschlagener Upgrade-Start hätte zur bisherigen Bridge-Version zurückgeführt; keine automatische p4d-Übernahme. Vorhandene Dauerbetriebspolitik und Schreibfreigaben erhalten. Kein Hostneustart oder Heizungs-Schreibtest.
- Benutzer verlangt weniger Aufwand bei Routineupdates. Wiederverwendbare Paketvorbereitung und kurze gezielte Betriebsprüfung bevorzugen; neue Einzelskripte und wiederholte Vollabnahmen ohne Anlass vermeiden. Einen öffentlichen Updatehelfer als eigene Verbesserung behandeln, nicht ungefragt an diesen fertigen Rollout anhängen.


## 18.10.2026 — Sollwerte direkt an gemessenen Werten

- Benutzer möchte Sollwerte klein bei den Istwerten und beauftragt direktes Live-Schalten. Reine Frontend-Zuordnung innerhalb derselben Geräteinstanz; dynamischer/berechneter Sollwert vor festem Einsteller. Keine Min/Max-/Frostschutz-/Pufferschwellen als vermeintliche Sollwerte.
- Vorhandene API und Lesejobs verwenden; veraltete Werte kennzeichnen und benötigte Soll-Einstellungen auch bei geschlossenen Details nachladen. Zwei statische Assets ohne Dienstneustart ausrollen, keine neue Backendversion oder Vollabnahme für diese Darstellungsänderung.

## 18.10.2026 — Pumpensignale für die Ursachenanalyse aufzeichnen

- Benutzer erklärt, dass je Gebäude Puffer und Warmwasserteil in einem gemeinsamen isolierten Zylinder sitzen, und beauftragt die Aufzeichnung aller Pumpen. Damit sind ähnliche Boiler-/Pufferanzeigen kein eigenständiger Nachweis eines Zuordnungsfehlers. Ob dieselben Fühlereingänge verwendet werden, bleibt ungeprüft.
- Alle 43 unterstützten pumpenbezogenen Katalogsignale über die bestehende Sensor-PATCH-Route auf `active=true, record=true` setzen; bisher 26 davon gelesen, keines aufgezeichnet. Allgemeine Ausgänge und mögliche nicht eingebaute Funktionen behalten ihre Originalbezeichnung. Der breite Namensfilter umfasst auch den Pumpstrom der Breitbandsonde; dieser ist keine Heizwasserpumpe und darf nicht als solche interpretiert werden.
- Bestehenden Minutentakt und Verdichtung erhalten: zusätzlich maximal 61.920 Messpunkte pro Tag, zusammen mit bisherigen 16 Werten 59 Punkte pro Durchlauf. Historie enthält Ansteuerungen beziehungsweise Schaltzustände, keinen nachgewiesenen Durchfluss und keine lückenlose Schaltchronik zwischen Abfragen. Keine neue API, automatische Auswahlregel oder Softwareversion erforderlich.
- Vorzustand privat sichern, vorhandene lokale Auswahl-/MariaDB-Synchronisierung verwenden. Umsetzung ohne Neustart oder Heizungsparameteränderung; zwei vollständige gespeicherte Sammelzyklen, bisherige Aufzeichnung und unveränderte sonstige Auswahl prüfen. Historische Pumpendaten für den früheren Vergleichszeitraum fehlen und werden nicht nachträglich erfunden.
