# Python-Protokollkern und Offline-Simulator

Stand: Version 0.1.0. Der Benutzer hat nach der Bestandsaufnahme die autonome Umsetzung des Offline-Kerns beauftragt. Dieses Paket implementiert die aus p4d 0.10.2 abgeleitete Bytecodierung und simulierte Transaktionsabläufe. Es gibt keinen seriellen Adapter, keine Live-Verbindung, keine Datenbankanbindung und noch keine HTTP-API.

## Installation und Demo

Python 3.9 oder neuer genügt; das Paket hat keine externen Laufzeitabhängigkeiten. Der Build verwendet setuptools. Die normale Paketinstallation funktioniert auch mit dem hier vorhandenen älteren pip; ein Editable-Install benötigt dagegen ein entsprechend modernes pip und ist nicht erforderlich.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/froeling-bridge demo
```

Ohne Installation aus dem Checkout:

```bash
PYTHONPATH=src python3 -m froeling_bridge demo
PYTHONPATH=src python3 -m froeling_bridge encode 55 '12 34'
PYTHONPATH=src python3 -m froeling_bridge decode '02 FD 00 03 55 12 34 91'
```

`demo` liest fiktive Daten, entdeckt ein Menü, ändert einen fiktiven Parameter sowie ein Zeitintervall und liest beides erneut. Ein- und Ausgaben werden in kleine Byte-Stücke zerlegt. Das Ergebnis ist JSON mit `mode=offline-simulator` und `hardware_verified=false`. Alle Daten stammen aus synthetischen Fixtures, nicht aus der Live-Anlage. Dezimalwerte erscheinen in der CLI als Zeichenketten, damit ihre Genauigkeit erhalten bleibt; dies ist noch kein HTTP-API-Vertrag.

## Schichten und Schnittstellen

| Modul | Zuständigkeit |
| --- | --- |
| `codec` | unveränderliches `Frame`, Prüfsumme, Encoder, vollständiger und inkrementeller Decoder |
| `messages` | Parameter-/Messwertmetadaten, Menü, Status, Firmware/Zeit, Fehler und Zeitprogramme |
| `session` | `ByteTransport`-Vertrag, exklusiver Besitzer einer gesamten Transaktion, Deadline, Antwortprüfung |
| `client` | fachliche Lese-/Schreiboperationen und bestätigtes Nachlesen |
| `simulator` | fiktive Heizung, fragmentierender Speichertransport und Fehler-Injektion |
| `__main__` | ausschließlich lokale CLI-Kommandos `demo`, `encode`, `decode` |

Die entsprechenden Dateien liegen unter [src/froeling_bridge](../src/froeling_bridge/). Runtime-Code importiert keine SSH-/DB-Bibliotheken und kennt keine Zugangsdaten oder Gerätepfade.

```python
from decimal import Decimal
from froeling_bridge.client import HeatingClient
from froeling_bridge.session import ProtocolSession
from froeling_bridge.simulator import MemoryTransport

transport = MemoryTransport(read_chunk_size=1, max_write=2)
client = HeatingClient(ProtocolSession(transport))
parameter = client.get_parameter(0x1234)
result = client.set_parameter(0x1234, Decimal('67.5'))
assert result.status.value == 'confirmed'
assert result.current.value == Decimal('67.5')
```

Verfügbare Clientoperationen sind Status, Firmware/Zeit, skalierte Messwerte, I/O-Zustände, Parameter, Messwertdefinitionen, Menü, Fehlerliste und Zeitprogramme. Listen werden vollständig innerhalb einer Transaktion gelesen und erst nach Listenende zurückgegeben. `max_items` begrenzt Discovery-Listen; Zeitprogramme enden wie im Referenzcode bei Adresse `DF`. Unbekannte Menütypen und Rohmetadaten bleiben erhalten.

`get_measurement(address, factor, data_type)` erhält die Metadaten ausdrücklich: Datentyp 1 bedeutet unsigned, sonst signed 16 Bit; anschließend Division durch den Faktor. Ein Faktor 0 wird bei Messwerten zurückgewiesen. Parameter behalten dagegen den Bestandsfallback Faktor 0 → effektiver Faktor 1 und ungeteilte Min-/Max-/Defaultwerte. Unbekannte Felder und der ursprüngliche Faktor werden nicht überschrieben.

## Framing und Fehlerverhalten

Der Encoder stimmt mit den acht bereits gegen C++ geprüften Telegrammvektoren überein. Der Streamdecoder verarbeitet auch innerhalb einer Escape-Folge geteilte Bytes und mehrere Frames in einem Chunk. Nutzdaten sind auf 254 Bytes begrenzt. Ungültige Startkennung, Länge, Maskierung, Prüfsumme oder ein unvollständiger Frame bei `finish()` verursachen explizite Fehler; es wird nicht still bis zur nächsten Startkennung weitergesucht.

Eine `ProtocolSession` serialisiert die **gesamte** Operation, einschließlich Discovery-Listen und Schreib-Nachlesen, mit einem Lock. Die monotone Deadline gilt für Lock-Wartezeit und alle nachfolgenden Transfers zusammen; sie beginnt nicht pro Byte erneut. Transportimplementierungen müssen `read`/`write` innerhalb des übergebenen Timeouts beenden. Nichtblockierende `read(..., timeout=0)`-Prüfungen erkennen bereits wartende unerwartete Bytes. Der Speichertransport modelliert leere Reads als virtuelle Timeouts; Tests müssen nicht tatsächlich auf die Uhr warten.

Nach einem Protokoll-/Transportfehler oder unerwarteten Programmabbruch ist die Sitzung dauerhaft `broken`. Ein `KeyboardInterrupt` bleibt als Abbruch erhalten; die Sitzung kann danach nicht weiterverwendet werden. Auch ein Programmfehler nach begonnenem Schreibversuch wird mit seiner Ursache als unklarer Schreibausgang gemeldet. Es gibt bewusst kein blindes Leeren und Wiederverwenden des Streams. Ein neuer physischer Transport und dessen sichere Synchronisation sind erst im späteren Hardwareplan zu spezifizieren. Ein Timeout beim Warten auf den Lock beschädigt dagegen nicht die bereits aktive Transaktion eines anderen Aufrufers.

**Grenze:** Das Protokoll hat im untersuchten Layout keine Transaktions-ID. Gleicher Antwortcode und gleiche Adresse beweisen daher nicht allein die Frische einer Antwort. Exklusiver Besitz, Idle-Prüfungen und Sperren nach Fehlern reduzieren Verwechslungen; eine spätere Hardwareintegration muss zusätzlich verzögerte Antworten, Wiederanlauf und weitere Teilnehmer untersuchen.

## Parameterschreiben

1. Parameter samt Metadaten frisch lesen und Adresse prüfen.
2. Typ, Grenzen, Nachkommastellen, Faktor und signed-16-Bit-Darstellbarkeit prüfen. Keine implizite Rundung oder Überläufe. Zahlen sind localeunabhängig; boolesche Werte benötigen Python-`bool`, Einzelzeitparameter `HH:MM` oder eine lokale `datetime.time` ohne Sekunden.
3. Unveränderter Rohwert → `unchanged`, kein Schreibtelegramm.
4. `39` mit Adresse und Rohwert senden und zwei Antworten mit passender Adresse verarbeiten. Ihre Werte werden als Belege erhalten, aber nicht mit einer unbewiesenen ACK-Bedeutung versehen.
5. Parameter erneut lesen. Rohwert und Interpretation anhand der aktuellen Metadaten müssen zum gewünschten Wert passen; auch ein geänderter Faktor darf keine falsche Bestätigung erzeugen.
6. Nur nach vollständig abgeschlossenem Austausch ohne weitere wartende Bytes → `confirmed`.

| Ergebnis / Fehler | Bedeutung |
| --- | --- |
| `ParameterWriteResult(status='unchanged')` | frisch gelesener Wert bereits passend, nichts geschrieben |
| `ParameterWriteResult(status='confirmed')` | simulierte Transaktion und Nachlesen erfolgreich |
| `ValidationError` | ungültige Eingabe oder ungeeignete Metadaten; kein Parameter-Schreibtelegramm gesendet |
| Protokoll-/Transportfehler vor dem Schreibversuch | keine Änderung durch diesen Aufruf gesendet; Sitzung anschließend gesperrt |
| `WriteOutcomeUnknown` | Schreibversuch begonnen, vollständige Bestätigung fehlt; keine automatische Wiederholung |
| `WriteVerificationError` | gültiges Nachlesen weicht vom Ziel oder dessen Interpretation ab; aktuelles Ergebnis als `actual` verfügbar |

Die beiden letzten Fehler enthalten Adresse und Operationsphase beziehungsweise Nachleseergebnis. Der ursprüngliche Übertragungsfehler bleibt bei `WriteOutcomeUnknown` als Exception-Cause erhalten. **Kein Fehlerpfad sendet automatisch erneut.**

## Zeitprogramme

Einzelzeitparameter und Zeitprogramme bleiben getrennt. `set_time_range(address, index, TimeRange(...))` verwendet einen **nullbasierten Index 0..3**. Ein leerer `TimeRange()` löscht beide Endpunkte; einseitig ungesetzte Intervalle werden abgewiesen. Alle belegten Endpunkte müssen in Zehn-Minuten-Schritten liegen; 06:19 wird nicht heimlich zu 06:10.

Vor einer Teiländerung liest der Client alle aktuellen Vierergruppen, ersetzt nur das angegebene Intervall und sendet die vollständige Zielgruppe. Danach werden Antwortadresse und die erneut gelesenen vier Intervalle geprüft. Die drei anderen Intervalle stammen dadurch nicht aus einem alten Anwendungscache. Übernachtintervalle werden nicht pauschal verboten; ihre fachliche Bedeutung ist firmwareabhängig und noch nicht bestätigt.

Diese Frische gilt nur innerhalb unseres exklusiven Kommunikationsbesitzes. Ein anderer Teilnehmer oder eine Änderung direkt am Bediengerät kann ohne eine vom Controller unterstützte Versionsprüfung nicht durch ein gewöhnliches Read/Modify/Write atomar ausgeschlossen werden.

## Unbestätigte Hardwareannahmen

Der Simulator verwendet standardmäßig den Requestcode als Antwortcode und bei `39` zwei Antworten desselben Codes. **Das ist ein explizites Simulationsprofil, keine bestätigte Hardwareeigenschaft.** `HeatingClient(..., reply_commands={request_code: (reply_code, ...)})` kann eine belegte Zuordnung aufnehmen; Lesebefehle benötigen einen Code, `39` zwei. Das Defaultprofil darf nicht ungeprüft auf die Anlage übertragen werden.

Die Rohbeobachtungen aus vorhandenen Logs und die Beleggrenzen stehen in [live-server.md](live-server.md). Echte Antwortzuordnungen, die Bedeutung der zwei Schreibantworten sowie Heizungsmodell/Firmware fehlen weiterhin. Deshalb enthält dieses Paket keinen TTY-Transport. Es schreibt weder Heizungsuhr noch Force-/I/O-Manipulationsbefehle.

## Anforderung an die spätere Web- und API-Schicht

Der [Browserbefund der Altinstallation](live-server.md#ergänzung-browserbefund-und-reconnect-schleife) zeigt wiederholte Reconnects. Der dortige Vier-Sekunden-Watchdog ist an Anwendungs-Pings gekoppelt, deren Erzeugung durch synchrone Heizungsaufgaben verzögert werden kann. Die neue API muss deshalb unabhängig vom seriellen Worker reagieren, gecachte Daten samt Aktualität liefern und lange Vorgänge als verfolgbaren Auftrag behandeln. Verbindungsabbruch und Abschluss eines Heizungsauftrags sind getrennte Zustände. Ein Reconnect darf insbesondere keinen Schreibauftrag automatisch wiederholen. Der Offline-Kern erzwingt bereits exklusive Transaktionen und verzichtet auf automatische Wiederholungen; die HTTP-/Job-Schicht ist noch zu implementieren.

## Prüfen und weiterarbeiten

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 docs/tools/verify_protocol_examples.py
```

Die Python-Suite umfasst 72 Tests und prüft bekannte C++-Vektoren, alle Chunk-Splitpositionen, alle Bytewerte, alle 65.536 Messwert-Bitmuster signed/unsigned, Typ-/Grenzen-/Skalierungsfehler, vollständige simulierte Abläufe, beide ACKs, falsche Adressen/Befehle, verlorene Antworten, falsches Nachlesen, verzögerte Daten, Session-Sperre, Lock-Konkurrenz und Gesamtdeadline. Die Original-C++-Prüfung benötigt zusätzlich einen C++17-Compiler; die Python-Suite nicht.

Nächste unabhängige Arbeitspakete sind der DB-Kompatibilitätsadapter gegen lokale Schema-/Datenfixtures und eine darauf aufbauende API. Der gemeinsame Protokollkern kann dafür ohne Hardware verwendet werden. Direkte Live-Schreibtests, eine Logstufenänderung oder ein konkurrierender Prozess an COM1 bleiben außerhalb der bisherigen Freigabe.
