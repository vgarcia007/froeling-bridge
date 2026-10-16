# Fröling Bridge

Ein Python-Projekt zur Kommunikation mit Fröling-Heizungssteuerungen der Lambdatronic-S3200-Familie.

Ziel sind eine dokumentierte API, ein modernes Servicemenü zum Lesen und Ändern von Heizungsparametern sowie eine einfache Installation. Vorhandene p4d-Messdaten sollen weiterverwendet und die bestehende MariaDB-Datenbank möglichst kompatibel fortgeführt werden.

## Grundlage und Dank

Dieses Projekt baut auf der Arbeit von Jörg Wendel (horchi) und dem Open-Source-Projekt [linux-p4d](https://github.com/horchi/linux-p4d) auf.

p4d erschließt die Kommunikation mit der Heizungssteuerung und stellt umfangreiche Funktionen zur Überwachung und Bedienung bereit. Der veröffentlichte Quellcode ist eine wesentliche Grundlage für unsere Untersuchung des Protokolls und der Datenbankstruktur. Vielen Dank an den Autor und alle Mitwirkenden dafür.

Als Ausgangspunkt der Bestandsaufnahme verwenden wir den [Fork von vgarcia007](https://github.com/vgarcia007/linux-p4d). Der konkret untersuchte Stand ist in der Dokumentation festgehalten.

Fröling Bridge ist ein eigenständiges Projekt mit dem Schwerpunkt auf Python, API-Zugriff und Parameterbedienung. Es wird unabhängig vom p4d-Projekt und vom Heizungshersteller entwickelt.

## Projektstand

Version 0.4.0 enthält das moderne Webmenü mit echten Menüpfaden, benannten Zeitprogrammen und gemeinsamem persistentem Cache, eine HTTP-API und kontinuierliche Messwertaufzeichnung. Der Modus `hardware-live` liest die reale Heizung und führt `samples` und `peaks` in der bestehenden p4d-Datenbank fort. Ein eigener systemd-Dienst übernimmt Dauerbetrieb und Autostart; bei Fehlern wird Original-p4d wiederhergestellt. Die [Dauerbetriebsanleitung](docs/production.md) beschreibt die Umschaltung auf einem bereits vorbereiteten Host.

Ein vollständiger 15-Minuten-Lesetest an der realen Heizung war erfolgreich: 15 Sammeldurchläufe, 195 Testmesspunkte, komplette Zeitprogrammliste und automatische Rückkehr zu p4d. Die produktive Installation wird gesondert aktiviert und bestätigt; den tatsächlichen Betriebsstand dokumentiert [project-context.md](docs/project-context.md).

Heizungsparameter schreiben bleibt im Hardwarebetrieb gesperrt. Parameter- und Zeitprogrammänderungen sind bislang nur am Simulator durch Nachlesen geprüft. Simulator und begrenzter Hardwaretest mit separater Test-MariaDB bleiben verfügbar; `database` bleibt eine reine Bestandsansicht. Grundlage sind der dokumentierte [Schemaabgleich](docs/live-database.md) und [installierte p4d-Stand](docs/live-server.md).

## Installieren und ausprobieren

Python 3.9 oder neuer; der Protokollkern benötigt keine externen Laufzeitabhängigkeiten:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/froeling-bridge demo
```

Die Demo verwendet ausschließlich fiktive Daten im Speicher. Sie benötigt keine Zugangsdaten, Datenbank oder angeschlossene Heizung. Die [Anleitung zum Python-Kern](docs/python-core.md) beschreibt Schnittstellen, Fehlerverhalten und Einschränkungen.

Für API und dauerhafte Datensammlung:

```bash
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install '.[service]'
.venv/bin/froeling-bridge serve
```

Das Webmenü läuft im LAN unter `http://SERVER-IP:8000/`, die API unter `http://SERVER-IP:8000/api/v1/health`. Standardbindung ist `0.0.0.0`; `--host 127.0.0.1` beschränkt den Zugriff bei Bedarf auf den eigenen Rechner. Der Sammler startet sofort und liest danach alle 60 Sekunden. Ohne Konfiguration bleiben alle Daten fiktiv und im Speicher. Die [Dienstanleitung](docs/service.md) beschreibt Testdatenbank, Bestandsansicht, API-Beispiele und Integrationstests. Die [Host-Testanleitung](docs/host-test.md) beschreibt die einmalige Einrichtung, SSH-Zugriff und den begrenzten Test mit automatischer Rückkehr. Ein alter Webinterface-Schreibmitschnitt ist keine Voraussetzung für die Weiterentwicklung.

## Dokumentation

Der Einstieg befindet sich in [docs/README.md](docs/README.md).

Für die Fortsetzung der Arbeit gibt es außerdem [Arbeitsregeln](AGENTS.md), einen [aktuellen Projektstand](docs/project-context.md) und ein [Entscheidungsprotokoll](docs/decisions.md).

## Referenzcode und Checkout

Der unveränderte p4d-Referenzcode ist als Git-Submodul unter `reference/linux-p4d` eingebunden und auf den dokumentierten Commit festgelegt.

```bash
git clone --recurse-submodules git@github.com:vgarcia007/froeling-bridge.git
cd froeling-bridge
```

Nach einem bereits erfolgten Checkout:

```bash
git submodule update --init --recursive
```

Für den Referenzcode gelten die ursprünglichen Copyright-Hinweise und die dort enthaltene [GPLv2-Lizenz](reference/linux-p4d/LICENSE). Diese Zuordnung legt noch keine separate Lizenz für künftig neu geschriebene Projektteile fest.

## Offline-Prüfung

Die Kern- und Sammlertests laufen ohne weitere Abhängigkeiten; HTTP-Tests benötigen das Service-Extra, MariaDB-Tests eine ausdrücklich konfigurierte lokale Testdatenbank (siehe Dienstanleitung):

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Für den zusätzlichen Vergleich mit extrahierten Originalfunktionen werden Git und ein C++17-Compiler (`c++`) benötigt:

```bash
python3 docs/tools/verify_protocol_examples.py
```

Die Prüfung verwendet Speicher-Stubs, öffnet keinen seriellen Port und stellt keine Datenbankverbindung her.

Lokale Zugangsdaten, Datenbankdumps und Telegrammmitschnitte werden nicht eingecheckt.
