# Eigenständiger Betrieb (Quellstand 0.7.2)

Die Bridge kann ohne p4d und ohne MariaDB starten. Sie liest Sensorbeschreibungen, Menü und Zeitprogramme direkt aus der Steuerung. SQLite speichert den Arbeitskatalog und Einstellungen lokal; MariaDB ist ausschließlich die optionale p4d-kompatible Historie. Protokoll und Darstellung orientieren sich an linux-p4d von Jörg Wendel und Mitwirkenden.

## Neue Installation

Für die vollständige Schrittfolge einschließlich Erstpasswort und Benutzeranlage dem [README](../README.md) folgen. Die folgenden Abschnitte erklären Konfiguration und Betrieb im Detail.

Der Installer richtet Python-Umgebung, Dienstbenutzer, Adapterrechte, Heimnetzzugang und Autostart ein. Fehlende Debian/Ubuntu-venv-Unterstützung und `fuser` werden installiert. Ein eindeutig erkannter Adapter wird automatisch gewählt, bevorzugt über `/dev/serial/by-id/…`. MariaDB ist optional; ein vorhandener Zugang aus einer älteren Bridge-Einrichtung kann übernommen werden.

Für unbeaufsichtigte Einrichtung eine **private** JSON-Datei vorbereiten und übergeben:

```sh
sudo bash deploy/install-standalone.sh --config /geschuetzt/bridge-settings.json
```

Benötigt werden `device` (absoluter Gerätepfad) und `auth` mit `{"mode":"lan"}` für direkten Heimnetzzugang oder der HTTPS-Konfiguration aus der [Zugangsanleitung](authentication.md#optional-https-und-reverse-proxy). Optional: `host` (Standard `0.0.0.0`), `port` (8000), `interval` (60 Sekunden) und `history` mit `host`, `port`, `database`, `user`, `password`. Keine Zugangsdaten in Shellargumente schreiben. Der native Dienst verwendet `/var/lib/froeling-bridge`; CLI-Demos erlauben eigene Zustandsordner.

Der erste Start erstellt einen vollständigen lokalen Katalog aus der Heizung; das kann mehrere Minuten dauern. Der Installer wartet auf betriebsbereite Erfassung. Details zu gerätespezifischen Antwortprofilen und Discovery stehen in der [Protokolldokumentation](protocol.md); normalerweise musst du sie nicht konfigurieren.

## Bestehende p4d-Installation übernehmen

Bei einer vorhandenen laufenden p4d-Installation ist der Wechsel ausdrücklich zu wählen:

```sh
sudo bash deploy/install-standalone.sh --take-over-p4d
```

Aktive alte Testfenster werden abgewiesen. Das Skript prüft Port und Prozessinspektion, hält vor der Umschaltung einen unabhängigen Rückkehrtimer bereit und wartet auf abgeschlossene Discovery sowie mindestens einen erfolgreichen Sammeldurchlauf. Originaldateien und alte Releases bleiben erhalten. Ein fremdes Releaseverzeichnis wird nicht übernommen; identische abgebrochene Einrichtung kann fortgesetzt werden.

Neue Installation: `http://RECHNER-IP:8000` im Browser öffnen, Erstpasswort mit `sudo cat /var/lib/froeling-bridge-installer/initial-login.json` anzeigen und als `operator` anmelden. Benutzer und API-Schlüssel verwaltet die Konsole; [Anleitung](authentication.md). HTTPS und Reverse Proxy sind eine optionale eigene Einrichtung, keine Voraussetzung. Vorhandene HTTPS-Konfigurationen bleiben erhalten. Beim ersten Start kann der Aufbau großer Menükataloge mehrere Minuten benötigen; das geschützte `/api/v1/runtime` zeigt die aktuelle Phase. Eine unvollständige Discovery ersetzt keinen vollständigen Katalog.

## Laufender Betrieb und Fehler

Die Gesundheitsüberwachung prüft alle 30 Sekunden die vorhandenen HTTP-Ansichten, ohne selbst auf den Adapter zuzugreifen. Bei anhaltend veralteten Heizungsdaten wird die Bridge wiederhergestellt; bei ausdrücklich aktivierter p4d-Rückfallpolitik erfolgt stattdessen die Rückkehr zum Original. Ein MariaDB-Ausfall beendet funktionierendes Live-Monitoring nicht. Details zur Richtlinie: [Dauerbetrieb](#verbindlicher-api-dauerbetrieb).

`/api/v1/runtime` und das Dienstjournal zeigen Startphase und Fehler. Ein letzter Startfehler kann nach einer Erholung noch als Diagnose erhalten bleiben; aktuellen Zustand zusätzlich prüfen.

- Statusprüfung alle 10 Sekunden, Messwertdurchlauf standardmäßig alle 60 Sekunden. Zustandswechsel löst einen zusätzlichen Durchlauf aus. Abfragen und Benutzerjobs teilen einen seriellen Besitzer.
- Alle Sensoren werden katalogisiert, nicht automatisch alle abgefragt. Ohne vorhandene Einstellungen sind erreichbare unterstützte Messwert-/I/O-Menüeinträge und UD 1–3 ausgewählt; Historie zunächst aus. Vorhandene Auswahl und individuelle Titel werden aus p4d übernommen. Ein noch nicht unterstützter Sensortyp bleibt sichtbar.
- SQLite: `catalogue.sqlite3` speichert Katalog, Einstellungen, letzte Werte, ausstehende DB-Einstellungen und Schreibjournal. `time-programs-cache.json` hält vollständige Zeitprogramme. Nach Neustart werden alte Werte als gespeichert/veraltet angezeigt, bis neue Heizungsantworten vorliegen.
- Bei beschädigter SQLite-Datei wird die Datei samt zugehörigen Nebenfiles unter `.damaged-*` erhalten und ein neuer Katalog aus der Heizung aufgebaut. Individuelle Einstellungen benötigen ein Backup; sie lassen sich nicht aus der Heizung rekonstruieren. Unbekannte zukünftige SQLite-Schemaversionen werden ausdrücklich abgewiesen.
- Verbindungsfehler schließen die defekte serielle Sitzung. Spätere Leseversuche öffnen eine neue exklusive Sitzung, mit begrenztem Wiederanlaufabstand bis 30 Sekunden. Der fehlgeschlagene Auftrag selbst wird nicht wiederholt. UI/API bleiben erreichbar und kennzeichnen die Verbindung getrennt von ihrer eigenen HTTP-Erreichbarkeit.
- Auf einem neuen Host startet systemd einen beendeten Prozess neu. Bei aktivierter automatischer Rückfallpolitik gibt es auf einem ursprünglichen p4d-Host stattdessen unmittelbare OnFailure-Rückkehr zu p4d; automatische Prozessneustarts werden dort deaktiviert, damit sie den Rückfall nicht verzögern. Ein normaler serieller Wiederverbindungsversuch läuft im Prozess und löst keine konkurrierende p4d-Instanz aus.

```sh
sudo /usr/local/sbin/froeling-bridge-control status
sudo /usr/local/sbin/froeling-bridge-control rollback
sudo /usr/local/sbin/froeling-bridge-control start
journalctl -u froeling-bridge.service -n 60
```

Auf einem neuen Host ohne p4d beendet `rollback` den Dienst und nimmt ihn aus dem Autostart. Auf dem ursprünglichen Host stellt es p4d mit dessen ursprünglicher Autostarteinstellung wieder her. Diese neue Rückkehr meldet den Dienstzustand; ein tatsächlicher neuer Originalmesspunkt muss für den Abnahmenachweis zusätzlich kontrolliert werden.

## Sensoren und API

`GET /api/v1/sensors` ist der Einstieg: Originalname `title`, individueller Name `usrtitle`, Einheit, Identität aus **type + address**, `active`, `recording`, `supported` und `latest`. Sensoren können ohne Menüeintrag existieren; Menüzeilen-IDs sind keine dauerhaft garantierten Sensoradressen.

`latest=null` bedeutet: kein Wert vorhanden. Ansonsten beschreiben `observed_at`, `age_seconds`, `origin` und `stale` die tatsächliche Beobachtung. `origin=local-persisted` ist ein gespeicherter Stand nach Neustart, kein neuer Heizungswert. GET löst keine Heizungsabfrage aus. Frische Werte über die bestehenden `measurement`-/`status`-Jobs anfordern, deren Ergebnis nicht automatisch eine Historienaufzeichnung auslöst.

```http
PATCH /api/v1/sensors/VA/43
Content-Type: application/json

{"active": true, "record": false}
```

Adresse 43 ist nur ein Beispiel; aus dem eigenen Katalog übernehmen. Ausschalten löscht keine Historie. `record=true` sorgt auch bei `active=false` für die notwendige Abfrage. Änderungen werden lokal gespeichert und nach MariaDB gespiegelt; während eines DB-Ausfalls bleiben sie als ausstehend sichtbar. Späte Übernahme alter DB-Einstellungen überschreibt keine bereits lokal geänderten Sensoren.

Für die Suche nach unerwarteter Speicherabkühlung auch die Pumpensignale zur Aufzeichnung auswählen: Heizkreispumpen, Puffer-/Boilerpumpen und allgemeine Pumpenausgänge können unterschiedliche Sensortypen haben (`DO`, `VA`, `AO`). Dieselbe PATCH-Route mit `{"active": true, "record": true}` genügt; ein Dienstneustart ist nicht erforderlich. Die Auswahl muss aus dem eigenen Katalog kommen. Ein Pumpenname oder ein Nullwert beweist keinen tatsächlichen Einbau; beispielsweise bezeichnet „Breitbandsonde Pump Strom“ einen Wert der Abgassonde, keine Heizwasserpumpe. Ungeklärte allgemeine Ausgänge behalten ihre Originalbezeichnung.

Für die zeitliche Bewertung von Heizkreisen zusätzlich pro Heizkreis **Vorlauf-Isttemperatur und Vorlauf-Solltemperatur** gemeinsam aufzeichnen. Die Solltemperatur kann sich im Tagesverlauf ändern; der heutige Sollwert ersetzt deshalb nicht den damaligen. Bereits aktive Sensoren benötigen lediglich `{"record": true}` über dieselbe PATCH-Route, keine zusätzlichen Heizungsabfragen. Mischerfahrbefehle sind eigene Sensoren und werden durch die Temperaturauswahl nicht automatisch mit aufgezeichnet.

Bei 60 Sekunden Sammelintervall entsteht je ausgewähltem Signal normalerweise ein Messpunkt pro Minute, auch bei unverändertem Wert. Kurze Schaltvorgänge zwischen den Abfragen können fehlen. Ein/Aus und prozentuale Ansteuerung sind keine Messung des Wasserflusses. Für den Vergleich mit Temperaturen die historischen Zeitpunkte verwenden; nach der Verdichtung sind analoge Werte Mittelwerte und digitale Werte Anteile der eingeschalteten Messpunkte, keine vollständige Schaltchronik.

`/api/v1/runtime` zeigt Discovery, Heizungsverbindung, lokale Speicherprobleme, Historienverbindung, tatsächlich gespeicherte Punkte, ausgelassene Zyklen, ausstehende Einstellungen und Verdichtung. Der im Sammlerstatus akzeptierte Historien-Auftrag ist noch keine Commit-Bestätigung; die tatsächliche Speicherung steht im Historienstatus.

OpenAPI: `/api/v1/openapi.json`. `/values`, `/history` und die vorhandenen Jobs bleiben kompatibel. Bestandsansicht und alte Hardwaretests erlauben keine Sensoränderungen.

## Konfiguration und Speicherorte

Die zentrale Datei einer nativen Installation ist:

```text
/etc/froeling-bridge/settings.json
```

Du kannst sie durch den Einrichtungsdialog erstellen lassen oder eine eigene private JSON-Datei übergeben:

```bash
sudo bash deploy/install-standalone.sh --config /geschuetzt/bridge-settings.json
```

Vollständiges Beispiel mit MariaDB; Gerätepfad und Zugangsdaten anpassen:

```json
{
  "device": "/dev/ttyUSB0",
  "host": "0.0.0.0",
  "port": 8000,
  "interval": 60,
  "auth": {"mode": "lan"},
  "history": {
    "host": "127.0.0.1",
    "port": 3306,
    "database": "froeling",
    "user": "froeling",
    "password": "HIER-DAS-DATENBANKPASSWORT"
  }
}
```

Die äußeren Felder `host` und `port` gehören zur **HTTP-API**. Unter `history` stehen Host, Port, Datenbankname, Benutzer und Passwort der **MariaDB**. Ein entfernter MariaDB-Server wird ebenfalls hier eingetragen. `interval` bestimmt den Messwertdurchlauf in Sekunden; Standard ist 60.

Produktive GUI und API benötigen eine Anmeldung. Eine neue Installation verwendet `"auth": {"mode": "lan"}` für direkten HTTP-Zugang im Heimnetz. Für den optionalen HTTPS-Betrieb hinter einem Reverse Proxy gilt: `auth.public_origin` ist dann die HTTPS-Adresse, `auth.trusted_proxy` die tatsächliche Proxy-IP. Der Installer hinterlegt den ersten Benutzer `operator` mit zufälligem Passwort in `/var/lib/froeling-bridge-installer/initial-login.json` (nur root lesbar). Benutzer und API-Schlüssel verwaltet `sudo froeling-bridge-users …`. API-Clients verwenden `Authorization: Bearer …`. Details, Apache-Vorlage und Schutzgrenzen stehen in der [Anmeldeanleitung](authentication.md).

| Gewünschter Betrieb | Konfiguration und Verhalten |
| --- | --- |
| Ohne MariaDB | `history` vollständig weglassen. Live-Werte, Menü, Zeitprogramme und Steuerungsfehlerspeicher funktionieren mit lokalem SQLite-Katalog. Keine Messwerthistorie in MariaDB. |
| Neue oder leere Datenbank | `history` angeben. Die Bridge legt eine fehlende Datenbank und die benötigten Tabellen automatisch an. MariaDB-Server und Benutzer müssen bereits existieren; der Benutzer benötigt passende Erstellungsrechte. |
| Bestehende p4d-Datenbank | Deren Zugangsdaten unter `history` eintragen. Das vorhandene kompatible Schema wird geprüft, nicht migriert oder neu initialisiert. Messreihen und Auswahl bleiben erhalten; Aufzeichnung und Fehlerabgleich werden fortgeführt. |

Die Bridge installiert keinen MariaDB-Server und legt keine Datenbankbenutzer an. Bei einer neuen/leeren Datenbank erstellt sie die sieben benötigten Tabellen einschließlich `samples`, `valuefacts` und `errors`; das umfasst die Heizungsfunktionen der Bridge, nicht alle p4d-Nebenfunktionen.

Konfigurationsdateien mit Passwörtern privat halten und nicht ins Repository aufnehmen. Der Installer schützt die installierte Datei für root und den Dienstbenutzer. Bestehende Einstellungen bleiben bei erneuter Einrichtung ohne `--config` erhalten. Es gibt derzeit keinen Webdialog für die Datenbankverbindung.

Für spätere Änderungen:

```bash
sudoedit /etc/froeling-bridge/settings.json
```

Vorhandene weitere Felder wie `reply_profile` und `write_validation` erhalten. Änderungen werden beim nächsten Dienststart eingelesen; einen dafür nötigen Neustart in einem bewussten Wartungsfenster durchführen. Der Installer ist kein Werkzeug zum Ändern einer laufenden Installation und weist einen bereits aktiven Bridge-Dienst ab.

### Was wird wo gespeichert?

| Speicher | Zweck |
| --- | --- |
| Arbeitsspeicher | Zuletzt abgefragte Werte für schnelle API-Antworten |
| `/var/lib/froeling-bridge/catalogue.sqlite3` | Dauerhafter Katalog, Sensoreinstellungen, letzte Werte und Schreibjournal |
| `/var/lib/froeling-bridge/time-programs-cache.json` | Zuletzt vollständig gelesene Zeitprogramme |
| Optionale MariaDB | Messwerthistorie, Min/Max-Werte, p4d-kompatible Metadaten und gespeicherte Fehlerhistorie |

Statusabfragen erfolgen alle **10 Sekunden**, ausgewählte Messwerte standardmäßig alle **60 Sekunden** und zusätzlich bei erkanntem Zustandswechsel. Sensorübersicht und API zeigen, ob ein Wert vorhanden, aktuell oder veraltet ist. Ein GET auf die Live-API liest den zuletzt erfassten Stand und sendet keine zusätzliche Anfrage an die Heizung. Menü-Leseaufträge und ausdrückliche Aktualisierungen laufen über denselben seriellen Worker.

In der Sensorübersicht kannst du Abfrage und Historienaufzeichnung auswählen. Normale Sensoren erzeugen nur bei aktivierter Aufzeichnung Messpunkte. Status, Betriebsart und Heizungszeit (**UD 1–3**) werden wie beim Original bei konfigurierter MariaDB unabhängig vom sichtbaren Recordflag aufgezeichnet. Ältere Einzelmesspunkte werden nach den übernommenen p4d-Einstellungen verdichtet; Standard sind 91 Tage Einzelwerte und anschließend 30-Minuten-Intervalle.

Ein MariaDB-Ausfall beendet das Live-Monitoring nicht, erzeugt aber sichtbare Aufzeichnungslücken. SQLite ist kein vollständiges Backup der MariaDB-Historie. Details zu Speicherung, Verdichtung und Sicherung: [Eigenständiger Betrieb](standalone.md).


## MariaDB ohne manuelle Tabellenarbeit

Der Historien-Worker verbindet sich unabhängig vom Heizungsworker. Bei nicht vorhandener/leerer DB legt er sieben benötigte p4d-0.10.2-kompatible Tabellen und Indizes aus dem paketierten bereinigten Bestands-Snapshot an. Dies ist kein vollständiger Ersatz sämtlicher p4d-Nebenfunktionen. Erstellen erfordert entsprechende Datenbankberechtigungen; Fehler werden sichtbar, ohne Live-Betrieb zu beenden.

Bestehende DBs werden geprüft und nicht migriert oder neu initialisiert. Bestehende Messreihen, Menüzeilen und individuelle Auswahl bleiben erhalten. Neue Sensordefinitionen können ergänzt werden; bestehende Auswahlflags ändern sich nur bei einer entsprechenden Benutzeränderung. Eine selbst begonnene leere Einrichtung kann anhand des lokalen Einrichtungsmarkers fortgesetzt werden; unbekannte Teilbestände werden erhalten und als unpassend gemeldet.

Im aktuellen Standalonebetrieb erzeugt `record=A` Messpunkte für normale Sensoren. UD 1–3 (Status, Betriebsart, Heizungszeit) werden ab 0.5.5 wie bei p4d intern immer aufgezeichnet, unabhängig vom gespeicherten Flag. `samples` und `peaks` werden gemeinsam transaktional geschrieben. MariaDB-Ausfälle erzeugen gemeldete Aufzeichnungslücken; kein nachträglicher Puffer und kein Wiederholen unklarer Commits. Die begrenzte Arbeitswarteschlange ist kein garantierter Ausfallspeicher.

Verdichtung übernimmt `p4d.aggregateHistory` und `p4d.aggregateInterval` (aktuell im Bestand 91 Tage/30 Minuten; Defaults ebenso). Täglich um 01:00 Europe/Berlin, höchstens sieben Tagespakete pro Lauf mit gespeichertem Fortschritt. Nur vollständige alte Intervalle: Kennung A, Intervallende, auf zwei Stellen gerundeter `sum(value)/count(*)`-Wert und ursprüngliche Anzahl. Text stammt deterministisch vom letzten Messpunkt im Intervall. Vorhandene Aggregate werden nicht überschrieben; Konfliktintervalle bleiben mit ihren Einzelwerten erhalten und werden gezählt. Einfügen und Löschen erfolgen pro Tagespaket in derselben Transaktion. Ungültige Verdichtungseinstellungen deaktivieren die Verdichtung, nicht die Aufzeichnung.

## Heizungs-Schreiben und Abnahme

Normales Parameterschreiben steht ab 0.7.2 nach einer neuen Installation direkt bereit. Erforderlich ist ein Benutzer beziehungsweise API-Schlüssel mit Schreibrechten; ein zusätzlicher Abnahmelauf oder eine Freischaltdatei gehört nicht zur Einrichtung. Bearbeitbare Parametertypen folgen dem p4d-Menü. Vor dem Schreiben werden der aktuelle Wert, Grenzen und Skalierung aus der Steuerung gelesen; anschließend wird das Ergebnis nachgelesen. Unklare Übertragungen werden nicht automatisch wiederholt.

Auf der Bestandsanlage wurde normales Parameterschreiben am 17.10.2026 durch Änderung und Rückstellung der LED-Helligkeit bestätigt. Zeitprogramm-Schreiben behält seine bisherige getrennte Behandlung; ohne entsprechenden Nachweis bleiben die Zeitfelder sichtbar deaktiviert. Simulator-Modus dient zur Prüfung der Abläufe:

```sh
.venv/bin/python -m froeling_bridge serve --mode standalone-demo --state-dir .local/demo-independent
```

Für gezielte Entwicklungs-/Gerätetests steht weiterhin `python -m froeling_bridge.validate_write` bereit. Es verlangt ausdrücklich Gerätepfad, genau ausgewählten Parameter/Wert beziehungsweise Zeitadresse/Intervall und einen privaten Zustands-/Nachweispfad. Nur bei vollständig bestätigter Änderung wird automatisch der vorherige Wert zurückgestellt und nachgelesen. Bei unklarem Ausgang erfolgt keine automatische Wiederholung oder vermutete Rückstellung; dann ist manuelles Nachlesen erforderlich. `--simulate` erzeugt ausdrücklich **keinen** gültigen Hardware-Nachweis.

Eine bereits vorhandene ausdrückliche `write_validation`-Konfiguration bleibt erhalten: Sie beschränkt die Operationen weiterhin auf den gewählten Nachweis und verlangt passenden Gerätepfad/Firmware. Für eine neue Installation ist diese Datei nicht nötig. Die API liefert die tatsächlich erlaubten Operationen unter `write_operations`. Vor einem Hardwaretest den seriellen Dienst kontrolliert stoppen; niemals parallel öffnen. Dieser Test wird nicht durch Installation, Discovery oder Browseraufruf ausgelöst.

## Sicherung und Wiederherstellung

```sh
sudo /opt/froeling-bridge/0.7.2/venv/bin/python -I -m froeling_bridge.state_backup backup --archive /geschuetzt/bridge-backup.zip
sudo /opt/froeling-bridge/0.7.2/venv/bin/python -I -m froeling_bridge.state_backup restore --archive /geschuetzt/bridge-backup.zip
```

Backup verwendet die SQLite-Backupfunktion und enthält Katalog/Einstellungen, letzte Werte, Zeitcache und die geschützte Konfiguration einschließlich optionaler DB-Zugangsdaten. Datei 0600; privat aufbewahren. **MariaDB-Historie ist nicht enthalten.** Restore nur bei gestopptem Dienst in leere Zielpfade. Heizungs-Schreibfreigaben werden nicht automatisch auf einen anderen Rechner übertragen. Nach Root-Restore führt die erneute Installation die Besitzrechte für den Dienstbenutzer korrekt nach.

## Stand des Nachweises

Automatisierte Tests, separate MariaDB, echte Pseudo-TTY mit HTTP, Browser und reale systemd-Ersatzdienste prüfen die Implementierung. Eine isolierte Debian-Installation prüft Paketinstallation, Dienstbenutzer/Rechte, seriellen Erststart und Wiederholung; systemd-Aufrufe sind in diesem Container simuliert und separat gegen echte Ersatzdienste geprüft. Auf der tatsächlichen Steuerung sind vollständige Discovery, aktuelle Werte, fortlaufende Aufzeichnung und Dienstneustart mit 0.5.2 bestätigt. Die 24h-Beobachtung läuft im Hintergrund bei funktionierendem Monitoring. Noch erforderlich: deren erfolgreicher Abschluss, kontrollierter Neustart des gesamten Hosts und ein separat vereinbarter realer Zeitprogramm-Schreibtest. Normales Parameterschreiben wurde inzwischen durch den LED-Test bestätigt. Ein Hostneustart ist aktuell ausdrücklich nicht beauftragt. Bis dahin keine Zusage vollständiger Hardwarevalidierung.


Reproduzierbare Zusatzprüfungen aus dem Checkout:

```sh
PYTHONPATH=src .venv/bin/python docs/tools/verify_standalone_pty.py
sudo .venv/bin/python docs/tools/verify_standalone_lifecycle.py --run-local-spares
# Der ältere 24h-Monitor benötigt Anpassung für authentifizierte Zugriffe; kein Schritt der Installation.
```

Der Monitor fragt nur HTTP-Zustand/Cache ab, sendet keine Heizungsjobs und speichert keine Messwerte/Zugangsdaten. Standarddauer 24 Stunden; ein abgebrochener oder fehlgeschlagener Lauf wird nicht als bestanden ausgegeben. Vorhandene Berichte werden erhalten. Native Installationsprüfung: `docs/tools/verify_native_install.py --in-container` ausschließlich in einem wegwerfbaren Debian-Container mit Python, psmisc und sudo, Checkout read-only unter `/source`. Sie ersetzt nur dort systemd-Kommandos durch den Testadapter; auf dem Host wird sie ausdrücklich abgewiesen.

### Parametermenü ab 0.5.3

Die Bearbeitung folgt dem p4d-Menüumfang: unterstützte Zahlen-, Ja/Nein- und Uhrzeitparameter sowie benannte Zeitprogramme. Aktuelle Editorwerte und Grenzen kommen aus der Steuerung; einmal „Speichern“ genügt. Nachlesen, Fehlermeldung bei unklarem Ausgang und Schreibsperren bleiben erhalten. Details und Simulator-Browserprüfung in [parameter-menu.md](parameter-menu.md#bedienung-nach-originalvorlage-ab-053). Die Installation allein erweitert keine Heizungs-Schreibfreigaben. Auf dem Bestandsrechner wurde `write_parameter` anschließend nach dem vereinbarten erfolgreichen LED-Test ausdrücklich aktiviert.

### Heizungsfehlerspeicher ab 0.5.4

Die Bridge liest die vollständige First-/Next-Fehlerliste beim Start, danach im Sammelintervall (standardmäßig 60 Sekunden) und bei erkanntem Zustandswechsel. Derselbe serielle Worker verhindert Parallelzugriffe. Nur ein vollständig gelesener und auswertbarer Stand ersetzt den persistenten SQLite-Cache. Ein Lesefehler erhält alte Daten mit ihrem ursprünglichen Zeitstempel und sichtbarer Fehlermeldung.

`GET /api/v1/errors` und die Webansicht „Fehlerspeicher“ verwenden ab 0.5.6 standardmäßig die vollständige MariaDB-Fehlerhistorie, sofern eine Historien-DB konfiguriert ist, wie Original-p4d. `source=controller` liefert gezielt nur den oben beschriebenen Cache ohne Datenbankabfrage. Beide Ansichten senden keine neuen Heizungsabfragen. Ohne konfigurierte DB verwendet der Default die Steuerungsansicht.

Die Antwort nennt `source` (`p4d-database` oder `controller-error-memory`), `total`, `limit` (Default 100, maximal 1000), `offset` und `has_more`. Gespeicherte Fehler sind nach `time1 DESC,id DESC` sortiert und enthalten die stabile Datenbank-ID. Weitere Seiten mit erhöhtem Offset lesen; neu hinzukommende Einträge können während des Blätterns die Seitengrenzen verschieben. Die GUI bietet „Zurück“/„Weiter“ und zeigt die Gesamtzahl.

Bei DB-Ausfall fällt `source=auto` ausdrücklich mit `fallback=true`, `history_available=false` und `history_error` auf den Steuerungsspeicher zurück. Diese kürzere Liste ist keine vollständige Historie; die GUI weist darauf hin. Für Clients, die zwingend gespeicherte Historie brauchen, `source=history` verwenden: bei fehlender/nicht erreichbarer DB HTTP 503 statt Rückfall. `source=controller` verlangt keine DB. `observed_at`, `age_seconds`, `stale`, `error` und `last_attempt` beziehen sich weiterhin auf die letzte vollständige Steuerungsabfrage; `read_at` ist bei Datenbankantworten der SQL-Lesezeitpunkt, `history_sync` meldet den letzten Abgleich. `available` bezeichnet die Verfügbarkeit der ausgegebenen Liste. Eine DB-Antwort kann also vorhanden sein, obwohl die Steuerungsabfrage veraltet ist.

Bei konfigurierter MariaDB synchronisiert der getrennte Historienworker die bestehende p4d-Tabelle `errors`. Zuordnung und Zustandsübergänge folgen `P4d::updateErrors`: Schlüssel Fehlernummer und Auftretenszeit, „gekommen“/„gegangen“/„quittiert“, `time1`/`time4`/`time2`. Bestehende IDs, Quittierungen, Mailzähler und außerhalb des Steuerungsspeichers liegende Historie bleiben erhalten. Keine Fehlerquittierung wird an die Heizung gesendet. Ein fehlgeschlagener DB-Abgleich wird separat in `/api/v1/runtime.history.controller_errors` gemeldet und beeinträchtigt weder aktuelle Messungen noch die übrige Aufzeichnung. Der DB-Abgleich wird nach 30 Sekunden erneut versucht, ohne neue serielle Schreibbefehle. Bestehende Tabellen werden nicht migriert; eine neue/leere Datenbank erhält die kompatible Fehler-Tabelle automatisch.

**Bestehende SQL-Clients:** Original-p4d erzwingt für Status, Betriebsart und Heizungszeit (UD 1–3) die interne Aufzeichnung in `applyConfigurationSpecials`, auch wenn das gespeicherte Recordflag ausgeschaltet ist. Der Standalone-Nachbau übernimmt dies ab 0.5.5; eine zuvor dokumentierte gegenteilige Aussage war falsch. Gespeicherte Flags bleiben unverändert. API-Livewerte sind weiterhin von MariaDB unabhängig. SQL-Clients sollten den Messzeitpunkt prüfen, um einen ausgefallenen Collector nicht mit einem aktuellen Zustand zu verwechseln.

Ein vorhandener Client liest `samples` für `address=1 AND type='UD'` nach `updsp DESC`. Das liefert bei aktiver Aufzeichnung aktuell den richtigen Status, ist aber gegenüber Verdichtung anfällig: `updsp` bezeichnet die Datenbankaktualisierung, nicht den Messzeitpunkt. Für den jüngsten Einzelmesspunkt verwenden:

```sql
SELECT text, time
FROM samples
WHERE address = 1 AND type = 'UD' AND aggregate = 'S'
ORDER BY time DESC
LIMIT 1;
```

Der Client sollte `time` auf ausreichende Aktualität prüfen. Ein erfolgreicher SELECT allein belegt keinen laufenden Heizungszugriff. Diese Empfehlung ändert weder die vorhandene Clientsoftware noch ihre Recordflags.

### Automatische interne Werte ab 0.5.5

`GET /api/v1/sensors` liefert `recording` als effektive Aufzeichnung, `configured_recording` als gespeichertes Flag und `recording_required` für die automatische UD-Regel. Bei UD 1–3 ist `recording=true` auch bei leerem/ausgeschaltetem Flag. Die Webansicht kennzeichnet diese Werte ausdrücklich als automatisch aufgezeichnet; ihr Historie-Kästchen ist aktiviert und nicht abschaltbar. Normale Sensorflags bleiben frei einstellbar. Automatische Aufzeichnung führt ohne konfigurierte MariaDB nicht zur Pflicht, eine Historien-DB einzurichten; Livewerte funktionieren weiterhin allein.

Originalbeleg: [applyConfigurationSpecials im Referenzstand](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/specific.c#L389), ebenso im tatsächlich installierten Originalquellstand 1bc324d. Der Speicherpfad allein zeigt nur die Prüfung des **bereits intern überschriebenen** Recordflags; daraus darf keine Abhängigkeit vom sichtbaren gespeicherten Flag abgeleitet werden.

### Darstellung des Fehlerspeichers

Ab 0.5.5 verwenden Fehlermeldungen eigene Einträge mit voller Textbreite, Zustandskennzeichnung und zugehörigen Zeitpunkten. Sie verwenden nicht mehr das Menü-Raster mit schmaler Symbolspalte. Auf kleinen Displays stehen die Zeitpunkte untereinander; auf dem Desktop nebeneinander. Auch die Kopfzeile bricht bei sehr kleinen Displays um.

`PYTHONPATH=src .venv/bin/python docs/tools/verify_error_browser.py --simulate-only` prüft im Chromium 320/390/768/1440 Pixel, lange fiktive Meldungen, alle drei Zustände, Zeitdarstellung, Seitenbreite und sichere Textausgabe ohne HTML-Auswertung. Ausschließlich Simulator, kein Zugriff auf die echte Heizung.

### Aktueller Fehlerzustand und historische Einträge ab 0.5.7

`state` ist der letzte gespeicherte historische Übergang. Ein alter Eintrag „gekommen“ ohne dokumentiertes Ende beweist keine heute aktive Störung. Dafür liefert die API zusätzlich `active`: **true** nur bei frischer vollständiger Steuerungsabfrage, die genau dasselbe Vorkommnis noch als offen meldet; **false** bei dokumentiertem Ende/Quittierung; **null** bei unbestätigtem Zustand. `activity_basis` nennt die Grundlage (`controller`, `documented_end`, `not_in_controller`, `controller_unavailable`), `activity_checked_at` bei Steuerungsbestätigung den Lesezeitpunkt. Eine fehlgeschlagene oder veraltete Abfrage darf keine aktuelle Aktivität bestätigen. Fehlende ältere Meldungen im begrenzten Steuerungsspeicher beweisen kein Ende.

Clients sollen für aktuelle Störungen `active === true` verwenden und null als unbekannt behandeln. Die GUI markiert Unbestätigtes neutral statt als aktive Störung. Historische Rohzustände und vorhandene Zeitpunkte bleiben erhalten; kein Quittierbefehl und keine erfundene Endzeit.

Der DB-Abgleich aktualisiert dasselbe Vorkommnis bei neuen bestätigten Zuständen (gekommen → gegangen → quittiert), ohne eine neue ID anzulegen. Nachgelieferte oder korrigierte Steuerungszeitpunkte werden auch dann übernommen, wenn der gespeicherte Zustandsname bereits passt. Wiederholte vollständige Listen bleiben idempotent; frühere Quittierung wird nicht durch wiederholtes Lesen älterer Anfangsmeldungen zurückgenommen. Ein neuer Auftretenszeitpunkt derselben Fehlernummer ist dagegen ein neues historisches Vorkommnis.


## Verbindlicher API-Dauerbetrieb

Auf dem abgenommenen Host ist seit 18.10.2026 die automatische Rückkehr zu p4d abgeschaltet. Der rootgeschützte Installerzustand `/var/lib/froeling-bridge-installer/installation.json` enthält `automatic_p4d_fallback: false`; `p4d_fallback: true` bezeichnet weiterhin die vorhandene manuelle Rückfalloption. Ohne neues Feld gilt für bestehende Installationen die bisherige Rückfallpolitik.

Installer, Lifecycle-Helfer und Health-Guard berücksichtigen dieses Feld gemeinsam. Bei ausgeschalteter automatischer Rückkehr startet systemd die Bridge nach Prozessende erneut (`Restart=always`, zehn Sekunden Pause, kein Startlimit); der Health-Guard startet bei anhaltend fehlenden Live-Daten ebenfalls die Bridge neu. Rescue schaltet nicht um, ein Startfehler lässt die Bridge zur Wiederherstellung bestehen, und der p4d-Starttimer wird nicht aktiviert. Explizites `rollback` bleibt eine bewusste administrative Abschaltung mit p4d-Rückkehr und ist kein normaler Betriebsablauf. Installer-Neuausführung erhält den gespeicherten Richtlinienwert.

Alte p4d-Cronjobs müssen nach Sicherung gezielt entfernt werden, andere Jobs erhalten. Nur `systemctl disable p4d` verhindert keine ausdrücklich geplanten Starts. Kein zweiter serieller Dienst parallel. Keine geplanten Stopps oder Updates am laufenden Host ohne neuen Auftrag; notwendige automatische Wiederherstellung kann kurze Unterbrechungen verursachen.


## Anlagenübersicht

Die eigene Seite `/anlage` gruppiert Messwerte, Pumpenansteuerungen und Parameter nach den Geräteinstanzen im Heizungsmenü. Sie benötigt kein passendes p4d-Schemabild und behauptet keine Rohrverbindungen. Zusätzliche Messwerte werden nur über ausdrückliche Aktivierung zur Abfrage ausgewählt; Historienflags bleiben erhalten. Cache, API, separate Vorschau und Prüfungen: [Anlagenübersicht](plant-overview.md). Der laufende Bestandsdienst bleibt bis zu einem gesonderten Rollout unverändert.
