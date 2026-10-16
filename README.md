# Fröling Bridge

Ein Python-Projekt zur Kommunikation mit Fröling-Heizungssteuerungen der Lambdatronic-S3200-Familie.

Ziel sind eine dokumentierte API, ein modernes Servicemenü zum Lesen und Ändern von Heizungsparametern sowie eine einfache Installation. Vorhandene p4d-Messdaten sollen weiterverwendet und die bestehende MariaDB-Datenbank möglichst kompatibel fortgeführt werden.

## Grundlage und Dank

Dieses Projekt baut auf der Arbeit von Jörg Wendel (horchi) und dem Open-Source-Projekt [linux-p4d](https://github.com/horchi/linux-p4d) auf.

p4d erschließt die Kommunikation mit der Heizungssteuerung und stellt umfangreiche Funktionen zur Überwachung und Bedienung bereit. Der veröffentlichte Quellcode ist eine wesentliche Grundlage für unsere Untersuchung des Protokolls und der Datenbankstruktur. Vielen Dank an den Autor und alle Mitwirkenden dafür.

Als Ausgangspunkt der Bestandsaufnahme verwenden wir den [Fork von vgarcia007](https://github.com/vgarcia007/linux-p4d). Der konkret untersuchte Stand ist in der Dokumentation festgehalten.

Fröling Bridge ist ein eigenständiges Projekt mit dem Schwerpunkt auf Python, API-Zugriff und Parameterbedienung. Es wird unabhängig vom p4d-Projekt und vom Heizungshersteller entwickelt.

## Projektstand

Aktuell befindet sich das Projekt in der Analysephase. Eine eigene Kommunikation mit der Heizung ist noch nicht implementiert.

Bisher dokumentiert sind:

- Aufbau und Codierung der seriellen Telegramme
- Lesen von Messwerten und Parameter-Metadaten
- Schreibabläufe für Parameter und Zeitprogramme
- Menüstruktur und Anforderungen an die Datenbankkompatibilität

Die bisherigen Protokollprüfungen erfolgen offline anhand des Referenzcodes. Ein erster ausschließlich lesender [Abgleich mit dem bestehenden Datenbankschema](docs/live-database.md) ist dokumentiert. Die Kompatibilität mit der bestehenden Installation und deren Firmware muss noch überprüft werden.

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

Benötigt werden Python 3, Git und ein C++17-Compiler (`c++`).

```bash
python3 docs/tools/verify_protocol_examples.py
```

Die Prüfung verwendet Speicher-Stubs, öffnet keinen seriellen Port und stellt keine Datenbankverbindung her.

Lokale Zugangsdaten, Datenbankdumps und Telegrammmitschnitte werden nicht eingecheckt.
