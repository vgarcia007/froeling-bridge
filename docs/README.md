# p4d: Bestandsaufnahme für einen Python-Nachbau

Für den Einstieg in die aktuelle Bridge: [README mit Schnellstart und Datenbank-Konfiguration](../README.md) und [eigenständige Installation und Betrieb](standalone.md). Der Hauptweg ist seit 0.5.0 `standalone`: direkte Heizungsverbindung, lokaler Katalog und optionale MariaDB-Historie. Webmenü, API, kontinuierliche Erfassung und Fehlerabgleich sind implementiert und auf der Bestandsanlage in Betrieb. Aktuelle Abnahmen und Grenzen stehen im [Projektkontext](project-context.md).

Die folgenden Abschnitte dokumentieren die ursprüngliche p4d-Bestandsanalyse vom 16.10.2026. Angaben zum damaligen Hardwarezugriff sind historische Untersuchungsschritte, nicht der aktuelle Betriebsstand.

## Referenz und Aussagekraft

| Merkmal | Untersuchte Referenz |
| --- | --- |
| Repository | https://github.com/vgarcia007/linux-p4d |
| Branch | `master` |
| Commit | `4d1176c4a9081893e4c2cc27a535bb2bc4737d0a` |
| Commitdatum | 08.12.2025, 09:29:07 +0100 |
| Commitbeschreibung | Fixed widget scaling on 'Skala Min' option (Thx to HautdenLukas) |
| Lokaler Checkout | [`../reference/linux-p4d/`](../reference/linux-p4d/) |
| Vergleich | `git ls-remote https://github.com/horchi/linux-p4d.git HEAD refs/heads/master` lieferte am Untersuchungstag ebenfalls diesen Commit. Damit stimmen die beiden geprüften Branchspitzen einschließlich Historie überein; es gibt dort keinen Fork-spezifischen Protokoll-, Menü- oder Schema-Diff. Andere Branches sind damit nicht bewertet. |
| Original-Lizenz | [`GPLv2`](../reference/linux-p4d/LICENSE); Copyright-Hinweise im Referenzcode bleiben erhalten. |

Der installierte Quellstand und die Versionskennung der Dienstpfad-Binärdatei wurden inzwischen lesend als p4d 0.10.2 eingegrenzt: [Live-Server-Abgleich](live-server.md). Heizungsmodell und Firmware sind noch unbekannt. Die ursprüngliche Quellcodeanalyse erfolgte offline; anschließend wurde das reale Datenbankschema mit ausdrücklicher Nur-Lesen-Erlaubnis untersucht: [Live-Abgleich](live-database.md). Die Heizung wurde nicht angesprochen. Die Dokumentation beschreibt **belegtes Verhalten des Referenzcodes**, keine vom Hersteller bestätigte Protokollspezifikation.

## API einfach benutzen

[Schritt-für-Schritt-Anleitung mit curl](api-einstieg.md): Schlüssel verwenden, Heizungsstatus und alle Sensoren lesen, technische Dokumentation öffnen oder herunterladen.

## Zugangsschutz

Ab 0.7.0 benötigen produktive GUI und API eine Anmeldung. [Benutzer, Rollen, API-Schlüssel und HTTPS einrichten](authentication.md). Die Konsole bleibt der einzige Weg zur Benutzer-/Passwortverwaltung.

## Anlagenübersicht

Ab 0.6.0 ergänzt die [Anlagenübersicht](plant-overview.md) eine eigene Seite und Komponenten-API. Sie zeigt Funktionsgruppen aus dem Heizungsmenü; die separate lesende Vorschau erfordert keine Unterbrechung des laufenden Dienstes.

## Lesereihenfolge

Für Installation und Konfiguration zur [Standalone-Anleitung](standalone.md), für zusätzliche Betriebsarten zur [Dienstanleitung](service.md), für Protokollschnittstellen zur [Anleitung des Offline-Kerns](python-core.md).

1. [Heizungsprotokoll](protocol.md): Transport, Telegramme, Befehle, Lesen und Fehlerfälle.
2. [Parametermenü und Schreiben](parameter-menu.md): kompletter Bedien- und Schreibpfad, einschließlich Zeitprogrammen.
3. [Datenbankkompatibilität](database-compatibility.md): Tabellen, Identitäten, Werte und Zeitsemantik.
4. [Live-Abgleich](live-database.md): bereinigte Strukturunterschiede zur laufenden Datenbank.
5. [Live-Server-Abgleich](live-server.md): installierte Version, Quellvergleich und vorhandene Empfangstelegramme.
6. [Befunde und nächste Schritte](findings-and-next-steps.md): priorisierte offene Punkte und nächste gemeinsame Entscheidungen.

Quellverweise zeigen auf den unveränderlichen Commit. **Belegt** bedeutet im Code nachvollzogen. **Offen** bedeutet ohne weitere Untersuchung oder echte Mitschnitte nicht geklärt. **Empfehlung** bezeichnet einen Vorschlag für den Nachbau, keine bereits beschlossene Architektur.

## Architektur des Bestands

```mermaid
flowchart LR
    H[Fröling S3200 COM1] <-->|57600 Baud, 8N1| T[lib/serial.c]
    T <--> P[p4io.c: Telegramme und Befehle]
    P <--> S[specific.c: P4d, Polling und Servicemenü]
    S <--> D[daemon.c und lib/db: Speicherung]
    D <--> DB[(MariaDB)]
    S <--> W[WebSocket-Ereignisse über wsactions.c]
    W <--> U[htdocs/menu.js: Browsermenü]
```

Die `.c`-Dateien werden als C++ gebaut. `main.c` startet die Klasse `P4d`; `Daemon` enthält die allgemeine Infrastruktur, `P4d` die Heizungsfunktionen. `FroelingService` definiert Befehle und Datenstrukturen, `P4Request` serialisiert und liest sie. Das Menü ist teilweise aus der Heizung ermittelt, teilweise durch p4d-Heuristiken ergänzt. Quellen: [Make.config:51](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/Make.config#L51) [main.c:131](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/main.c#L131) [specific.c:118](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/specific.c#L118) [service.h:20](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/service.h#L20) [p4io.h:27](https://github.com/vgarcia007/linux-p4d/blob/4d1176c4a9081893e4c2cc27a535bb2bc4737d0a/p4io.h#L27).

Für den Nachbau sind drei Grenzen wichtig: serielle Kommunikation unabhängig vom HTTP-Zugriff; fachliche Parameterwerte unabhängig von alten Anzeigezeichenketten; Datenbankkompatibilität unabhängig von allen übrigen p4d-Funktionen. Das sind aus der Analyse abgeleitete Empfehlungen, noch keine Implementierungsentscheidung.

## Reproduzierbare Prüfung

```bash
cd froeling-bridge
python3 docs/tools/verify_protocol_examples.py
```

Benötigt werden Python 3, Git und ein C++17-Compiler (`c++`). Das Prüfwerkzeug extrahiert die Originalfunktionen `prepareRequest`, `readByte`, beide `readWord`-Varianten, `readHeader` sowie `crc` in einen temporären C++-Prüfstand. Nur Transport und umgebende Typen werden durch Speicher-Stubs ersetzt. Es öffnet weder TTY noch Datenbank und baut/installiert nicht den Daemon.

Ergebnis: acht [synthetische Telegrammvektoren](protocol-vectors.json) stimmen mit Encoder und Decoder überein; alle 65.536 16-Bit-Muster werden vorzeichenbehaftet und vorzeichenlos geprüft. Ungültige und abgeschnittene Escape-Folgen werden abgelehnt. Die Beispiele belegen die Bytecodierung, **nicht** die Antwortsemantik einer realen Heizung oder den kompletten Schreibablauf. Die extrahierten Originalfunktionen unterliegen der Lizenz des Referenzprojekts.

- [Produktiver Dauerbetrieb und Rückkehr](production.md)

- [Eigenständiger Betrieb, Neuinstallation, Discovery und optionale Historie ab 0.5.0](standalone.md)
