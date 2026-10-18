# Fröling Bridge

Heizungsüberwachung und Parameterbedienung für Fröling-Steuerungen der **Lambdatronic-S3200-Familie**: ein Python-Dienst mit Webmenü und HTTP-API, der direkt über den seriellen Adapter mit der Heizung kommuniziert.

Die Bridge kann eigenständig starten, ohne vorhandene p4d-Installation und ohne MariaDB. Wer bereits eine p4d-Datenbank hat, kann deren Historie und Einstellungen weiterverwenden. Aktueller Stand: **0.5.7**.

- Live-Status und ausgewählte Messwerte automatisch abfragen.
- Heizungsmenü mit den Namen aus der Steuerung durchsuchen und Parameter bedienen.
- Benannte Zeitprogramme anzeigen und zwischenspeichern.
- Fehlerspeicher regelmäßig abgleichen, einschließlich Auftreten, Ende und Quittierung.
- Optional Messwerte in MariaDB aufzeichnen, Aufzeichnung je Sensor auswählen und ältere Daten verdichten.
- Dieselben Funktionen über eine dokumentierte API für eigene Clients nutzen.

## Grundlage und Dank

Dieses Projekt baut auf der Arbeit von Jörg Wendel (horchi) und dem Open-Source-Projekt [linux-p4d](https://github.com/horchi/linux-p4d) auf.

p4d erschließt die Kommunikation mit der Heizungssteuerung und stellt umfangreiche Funktionen zur Überwachung und Bedienung bereit. Der veröffentlichte Quellcode ist eine wesentliche Grundlage für unsere Untersuchung des Protokolls und der Datenbankstruktur. Vielen Dank an den Autor und alle Mitwirkenden dafür.

Als Ausgangspunkt der Bestandsaufnahme verwenden wir den [Fork von vgarcia007](https://github.com/vgarcia007/linux-p4d). Der konkret untersuchte Stand ist in der Dokumentation festgehalten.

Fröling Bridge ist ein eigenständiges Projekt mit dem Schwerpunkt auf Python, API-Zugriff und Parameterbedienung. Es wird unabhängig vom p4d-Projekt und vom Heizungshersteller entwickelt.

## Schnellstart: auf einem Heizungsrechner installieren

Voraussetzungen: Debian/Ubuntu mit systemd, Python ab 3.9 und ein angeschlossener serieller Heizungsadapter. Der Installer verwendet eine eigene Python-Umgebung; Docker wird nicht benötigt. Für das derzeit private Repository brauchst du GitHub-Zugriff, beim folgenden SSH-Checkout einen eingerichteten SSH-Schlüssel.

```bash
sudo apt-get update
sudo apt-get install -y git python3 python3-venv

git clone --recurse-submodules git@github.com:vgarcia007/froeling-bridge.git
cd froeling-bridge
sudo bash deploy/install-standalone.sh
```

Der Installer richtet Dienstbenutzer, Adapterrechte, Konfiguration, systemd-Dienst und Gesundheitsüberwachung ein. Er wählt einen eindeutig erkannten Adapter, bevorzugt über `/dev/serial/by-id/…`, oder fragt nach dem Gerätepfad. Danach fragt er, ob du MariaDB verwenden möchtest; das Passwort wird verdeckt eingegeben. Er startet die Bridge und aktiviert den Autostart.

Beim ersten Start liest die Bridge Sensorbeschreibungen, Menü und Zeitprogramme direkt aus der Heizung. Das kann mehrere Minuten dauern. Spätere Starts verwenden den lokal gespeicherten Katalog.

Im Browser öffnen; `SERVER-IP` durch die Adresse des Heizungsrechners ersetzen:

| Adresse | Inhalt |
| --- | --- |
| `http://SERVER-IP:8000/` | Webmenü mit Sensoren, Parametern, Zeitprogrammen und Fehlerspeicher |
| `http://SERVER-IP:8000/api/v1/health` | Betriebsart und verfügbare Funktionen |
| `http://SERVER-IP:8000/api/v1/runtime` | Startfortschritt, Heizungsverbindung, Erfassung und Datenbankstatus |
| `http://SERVER-IP:8000/api/v1/openapi.json` | OpenAPI-Vertrag für eigene Clients und Entwicklungsagenten |

Standardmäßig lauscht der Dienst auf `0.0.0.0:8000` und ist damit im LAN erreichbar. Adresse und Port sind konfigurierbar.

### Wenn auf dem Rechner bereits p4d läuft

Für die kontrollierte Übernahme:

```bash
sudo bash deploy/install-standalone.sh --take-over-p4d
```

Eine private Konfigurationsdatei lässt sich zusätzlich mit `--config /geschuetzt/bridge-settings.json` übergeben. Der Installer stoppt p4d vor dem exklusiven seriellen Zugriff und erhält die Originalinstallation als Rückfalloption. **Bridge und p4d dürfen nicht gleichzeitig auf denselben Adapter zugreifen.** Alte Cronjobs, die p4d starten oder neu starten, müssen nach Sicherung gezielt entfernt werden; allein dessen Autostart zu deaktivieren reicht dafür nicht. Der Installer entfernt keine fremden Cronjobs.

Bei einer bisherigen Bridge-Testeinrichtung kann der Einrichtungsdialog die Verbindung aus `/etc/froeling-bridge-test/source-db.json` übernehmen. Ansonsten die vorhandene p4d-Datenbank im Dialog oder im Feld `history` der folgenden Konfiguration angeben.

## Wo konfiguriere ich die Datenbank?

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

Ein MariaDB-Ausfall beendet das Live-Monitoring nicht, erzeugt aber sichtbare Aufzeichnungslücken. SQLite ist kein vollständiges Backup der MariaDB-Historie. Details zu Speicherung, Verdichtung und Sicherung: [Eigenständiger Betrieb](docs/standalone.md).

## Dienst prüfen und betreiben

```bash
sudo /usr/local/sbin/froeling-bridge-control status
systemctl status froeling-bridge.service
journalctl -u froeling-bridge.service -n 60
```

Einen eingerichteten, inaktiven Dienst starten:

```bash
sudo /usr/local/sbin/froeling-bridge-control start
```

Der native Dienst startet beim Booten automatisch. Auf einem neuen Host stellt systemd die Bridge nach einem Prozessausfall wieder her; der Health-Timer überwacht aktuelle Heizungsdaten. Bei einer übernommenen p4d-Installation ist zunächst automatische Rückkehr zu p4d vorgesehen. Für verbindlichen API-Dauerbetrieb kann die Wiederherstellung auf die Bridge festgelegt werden; diese Richtlinie bleibt bei erneuter Installation erhalten. Auf der Bestandsanlage ist dies bereits so eingerichtet. Details zur Richtlinie und zur ausdrücklich manuellen Rückkehr: [Dauerbetrieb](docs/standalone.md#verbindlicher-api-dauerbetrieb).

## Ohne Heizung ausprobieren oder manuell starten

Für lokale Versuche aus dem Checkout:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install '.[service]'
```

Webmenü mit fiktiven Daten und eigenem lokalem Katalog starten:

```bash
.venv/bin/froeling-bridge serve --mode standalone-demo   --state-dir .local/demo
```

Die Demo läuft ebenfalls auf Port 8000, benötigt weder Heizung noch Datenbank und erlaubt simulierte Änderungen. `froeling-bridge serve` ohne Modus startet die ältere flüchtige Demo; **echte Heizungsdaten erhältst du damit nicht**. Für eine reine Protokolldemo im Terminal genügt `.venv/bin/froeling-bridge demo`.

Manueller Vordergrundbetrieb mit echter Heizung, ohne systemd-Installation; Adapterrechte müssen vorhanden sein und kein anderer Dienst darf den Adapter verwenden:

```bash
.venv/bin/froeling-bridge serve --mode standalone   --device /dev/ttyUSB0   --state-dir .local/heizung
```

Für eine optionale MariaDB-Verbindung `--history-config /geschuetzt/database.json` ergänzen. Diese Datei enthält **nur** die fünf Datenbankfelder aus `history`, ohne umschließendes `history`-Objekt. `--host`, `--port` und `--interval` passen den manuellen Start an. Bei abweichenden Antwortcodes kann ein passendes `--reply-profile` nötig sein; der native Installer liefert das auf der Bestandsanlage bestätigte Profil mit.

Weitere Modi für bestehende Installationen und Entwicklung:

| Modus bei `serve --mode …` | Zweck |
| --- | --- |
| `standalone` | Empfohlener eigenständiger Hardwarebetrieb mit Discovery und optionaler Historie |
| `standalone-demo` | Derselbe eigenständige Ablauf mit simuliertem Gerät |
| `database` | Bestehende p4d-Datenbank mit `--config DATEI` ausschließlich lesend anzeigen; keine Heizungsverbindung |
| `demo` / `demo-db` | Ältere Simulator-Modi, flüchtig oder mit separater Testdatenbank |
| `hardware-read` / `hardware-live` | Ältere Hardware-Modi auf Basis vorhandener DB-Metadaten; siehe [Dienstanleitung](docs/service.md) |

## API für eigene Clients

Einstieg für einen Client oder Entwicklungsagenten: `http://SERVER-IP:8000/api/v1/openapi.json`. Der maschinenlesbare Vertrag liegt auch im Repository unter [openapi.json](src/froeling_bridge/openapi.json).

```bash
curl -sS http://SERVER-IP:8000/api/v1/sensors
curl -sS http://SERVER-IP:8000/api/v1/runtime
curl -sS http://SERVER-IP:8000/api/v1/errors
```

`/sensors` liefert den Katalog **mit den letzten Werten**. Suche den gewünschten Sensor über `title` beziehungsweise `usrtitle`, etwa die Kesseltemperatur, und verwende dessen Kombination aus `type` und `address`. Keine fest angenommenen Adressen oder Menüzeilen-IDs verwenden. In `latest` stehen Wert, Beobachtungszeit, Herkunft und `stale`; `latest=null` bedeutet, dass noch kein Wert vorliegt. Nach einem Neustart wird ein lokal gespeicherter Stand ausdrücklich als solcher gekennzeichnet.

`/errors` liefert bei konfigurierter MariaDB standardmäßig die gespeicherte Historie mit Seitennavigation. `source=controller` wählt nur den zuletzt gelesenen Steuerungsspeicher. `active` unterscheidet bestätigt aktiv, beendet und unbekannt; der gespeicherte Zustand allein beweist keine aktuelle Störung. Menü, Zeitprogramme, Historienabfragen und asynchrone Aufträge sind ebenfalls im OpenAPI-Vertrag beschrieben.

## Parameter schreiben und aktueller Nachweis

Das Parametermenü orientiert sich an den bearbeitbaren Typen des p4d-Heizungsmenüs. **Eine neue Hardwareinstallation startet mit gesperrtem Heizungs-Schreiben.** Eine Freigabe benötigt einen geschützten, zu Gerät, Firmware und Operation passenden Hardware-Nachweis über `write_validation`; Parameter- und Zeitprogramm-Schreiben sind getrennte Freigaben. Die tatsächlich verfügbaren Operationen stehen in `/api/v1/health` unter `write_operations`. Vorgehen: [Heizungs-Schreiben und Abnahme](docs/standalone.md#heizungs-schreiben-und-abnahme).

Auf der Bestandsanlage sind Discovery, laufende Erfassung, MariaDB-Aufzeichnung, Dienstwiederanlauf und normales Parameterschreiben nach einem reversiblen LED-Test bestätigt. Ein realer Aschebox-Fehler wurde einschließlich Ende/Quittierung ohne Duplikat in API und MariaDB nachverfolgt. Zeitprogramm-Schreiben und ein vollständiger Hostneustart sind dort noch nicht abgenommen. Diese Ergebnisse sind keine pauschale Freigabe für andere Geräte oder Firmwarestände.

## Weiterführende Dokumentation und Entwicklung

- [Installation, Konfiguration, Sensoren, Historie und Wiederherstellung](docs/standalone.md)
- [Dokumentationsübersicht und p4d-Bestandsanalyse](docs/README.md)
- [API, ältere Betriebsarten und separate Testdatenbank](docs/service.md)
- [Parametermenü und Schreibprotokoll](docs/parameter-menu.md)
- [Python-Protokollkern und Simulator](docs/python-core.md)
- [Aktueller Arbeitskontext](docs/project-context.md), [Entscheidungen](docs/decisions.md) und [Arbeitsregeln](AGENTS.md)

Tests aus dem Checkout; das Service-Extra ermöglicht die HTTP-Tests, MariaDB-Tests brauchen eine ausdrücklich konfigurierte separate Testdatenbank:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
python3 docs/tools/verify_protocol_examples.py
```

Die zweite Prüfung benötigt Git und einen C++17-Compiler und vergleicht die Telegrammcodierung mit extrahierten Originalfunktionen. Sie öffnet weder seriellen Port noch Datenbank.

Der unveränderte Referenzcode liegt als gepinntes Git-Submodul unter `reference/linux-p4d`. Bei einem Checkout ohne Submodule nachholen:

```bash
git submodule update --init --recursive
```

Für den Referenzcode gelten die ursprünglichen Copyright-Hinweise und die enthaltene [GPLv2-Lizenz](reference/linux-p4d/LICENSE). Eine separate Lizenz für neue Projektteile ist bislang nicht festgelegt. Lokale Zugangsdaten, Datenbankdumps und Telegrammmitschnitte gehören nicht ins Repository.
