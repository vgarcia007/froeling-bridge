# Webmenü und temporärer Hardwaretest (0.3.0)

Das moderne Menü ist jetzt Teil des Python-Pakets: unter `/` werden Menübaum, Suche, Parametereditor, Messwerte, Zeitprogramme und Aufzeichnungsstatus ausgeliefert. HTML/CSS/JavaScript liegen im Paket; es gibt keinen zusätzlichen Frontend-Build. Änderungen am Simulator werden bestätigt und durch Nachlesen geprüft. Die Hardwaretest-Ansicht ist vollständig lesend.

## Lokal ansehen

```bash
.venv/bin/python -m pip install '.[service]'
.venv/bin/froeling-bridge serve
```

Browser: `http://127.0.0.1:8000/`. Die Oberfläche kennzeichnet Demo und reale Daten. Sichtbare bekannte Parameter werden nacheinander frisch gelesen; beim Navigieren werden veraltete Ergebnisse ignoriert. Ein Schreib-POST wird genau einmal gesendet. Nach unklarem Ergebnis muss neu gelesen werden, bevor der Editor eine weitere Änderung erlaubt. Verbindungsprobleme führen ausschließlich zu erneuten Statusabfragen.

Menüsuche verwendet `GET /api/v1/menu/search?q=…`, maximal 100 Ergebnisse. `/health` enthält Version, Lesebestätigung und Fähigkeiten (`controller_read`, `heating_write`). `hardware_verified` bleibt false: erfolgreiche Leseabfragen sind keine vollständige Hardware-/Schreibvalidierung. `read_connection_verified` bestätigt nur die initial erfolgreich gelesenen Status-/Firmwareantworten.

## Vereinbarter erster Hosttest

- 15 Minuten, mit unabhängiger automatischer Rückkehr zu `p4d.service`.
- Nur echte Werte und Parameter lesen; keine Heizungsparameter ändern, keine Uhr stellen und keine Zeitprogramme schreiben.
- Originaldatenbank ausschließlich lesend für Menü und Sensorauswahl verwenden. Neue Messpunkte nur in einer **frischen separaten Testdatenbank** speichern.
- Originalinstallation, Dienstdatei und Autostart unverändert erhalten. Während des Tests entsteht eine Lücke in der Originalhistorie; es gibt keine automatische Rückübertragung der Testmesspunkte.
- Demo kann bereits vor dem Wechsel parallel laufen. Keine zwei Prozesse gleichzeitig am USB-Port.

Die lesende Vorprüfung des Zielhosts ergab Python 3.12, Docker, einen aktiven/enabled p4d-Dienst und den vorhandenen USB-Adapter. Für den historischen Test war eine separate einmalige administrative Einrichtung vorgesehen. Persönliche Berechtigungsdetails werden ausschließlich privat dokumentiert.

## Vorbereitetes Einrichtungspaket

Die reproduzierbaren Quellen stehen unter [deploy](../deploy/). Das private Paket enthält zusätzlich die DB-Verbindung, Projekt-Wheel und passende Linux-x86_64-/Python-3.12-Abhängigkeiten. Es wird unter `.local` erzeugt und nicht eingecheckt:

```bash
.venv/bin/python -m pip wheel . --no-deps --wheel-dir .local/wheels
PYTHONPATH=src .venv/bin/python docs/tools/prepare_host_test.py --upload
```

Das Werkzeug liest die bestehenden ignorierten `live-db.con` und `live-server-ssh.con`. Es schreibt die Verbindung ausschließlich in eine private Datei, prüft die JSON-Struktur ohne Live-DB-Verbindung und überträgt das Paket per SSH in einen neuen privaten Ordner `~/froeling-bridge-test-0.3.0`. Keine Überschreibung vorhandener Pakete, kein sudo und keine Dienstaktion bei der Übertragung.

**Auf dem Zielhost**, nach Durchsicht von `install.sh`, einmal ausführen:

```bash
sudo bash ~/froeling-bridge-test-0.3.0/install.sh
```

Die Einrichtung:

- prüft Paket-Prüfsummen, den aktiven p4d-Dienst, verfügbare Ports und vorhandene Werkzeuge;
- installiert in `/opt/froeling-bridge/0.3.0` eine eigene Umgebung und legt einen eigenen Dienstbenutzer an;
- erstellt einen separaten MariaDB-10.11-Container auf `127.0.0.1:33079` mit eigenem Volume und lokal generiertem Passwort;
- legt geschützte Konfiguration unter `/etc/froeling-bridge-test` und private Testberichte an;
- installiert genau vier neue systemd-Einheiten und einen root-eigenen Helfer;
- erlaubt dem aufrufenden SSH-Konto ausschließlich die drei festen Helferaktionen über sudo;
- startet **nur die Simulator-Vorschau** auf Loopback-Port 8000. p4d läuft dabei weiter; der USB-Port wird nicht geöffnet.

Die Einrichtung setzt funktionierendes Docker und `python3 -m venv`, außerdem `fuser`, `visudo` und die Gruppe `dialout` voraus. Sie installiert keine Betriebssystempakete automatisch. Bestehende Installationspfade, ein gleichnamiger Container oder ein gleichnamiges Volume führen zum Abbruch. Bei einem Einrichtungsfehler können angelegte neue Testressourcen verbleiben; Original-p4d wird dabei nicht gestoppt. Wiederholung/Upgrade muss diese Ressourcen vorher ausdrücklich prüfen.

## Browserzugriff

Vom eigenen Rechner einen SSH-Tunnel mit dem vorhandenen SSH-Zugang öffnen:

```bash
ssh -N -L 8000:127.0.0.1:8000 -L 8001:127.0.0.1:8001 SSH_BENUTZER@ZIELHOST
```

- Demo: `http://127.0.0.1:8000/`
- Während des Hardwaretests: `http://127.0.0.1:8001/`

Beide Dienste binden ausschließlich an Loopback; es gibt keine neue LAN-/Internetfreigabe. Der Tunnel kann für die Browseransicht nötig sein, beeinflusst aber die Rückkehr zu p4d nicht.

## Start, Status und sofortige Rückkehr

Nach erfolgreicher Einrichtung sind auf dem Host genau diese Aktionen verfügbar:

```bash
sudo -n /usr/local/sbin/froeling-bridge-test status
sudo -n /usr/local/sbin/froeling-bridge-test start-test
sudo -n /usr/local/sbin/froeling-bridge-test rollback
```

`start-test` prüft Originaldienst, Port, Metadaten und Testdatenbank. Für jedes Fenster wird ein eigener leerer Schemaausschnitt angelegt; vorherige Testdaten bleiben erhalten. Erst nach dauerhaft gespeichertem Fensterzustand und aktiviertem Rückkehrtimer wird p4d gestoppt. Danach prüft `fuser`, dass niemand den Port hält, bevor der Hardwaretest startet.

Der Test öffnet `/dev/ttyUSB0` mit 57.600 Baud, 8N1, ohne Flusskontrolle. `flock` koordiniert Bridge-Prozesse; `TIOCEXCL` verhindert weitere unprivilegierte TTY-Opens. Diese Mechanismen ersetzen nicht die vorherige Prüfung bereits geöffneter Ports. Bei normalem Ende werden Terminaleinstellungen wiederhergestellt und das Gerät geschlossen. Empfangsdaten werden nicht automatisch verworfen.

Status und Firmware werden zuerst abgefragt. Das Echo-Antwortprofil bleibt eine **zu prüfende Annahme**, kein bestätigtes Hardwareprofil. Eine abweichende Antwort beendet den Test; Rohdaten liegen privat für die spätere Zuordnung vor. Der CLI-Adapter unterstützt alternativ eine ausdrücklich angegebene JSON-Antwortzuordnung; die unveränderte Hosteinrichtung verwendet zunächst das strenge Defaultprofil.

Danach sammelt der vorhandene Worker im 60-Sekunden-Takt. API und Browser bleiben unabhängig davon erreichbar. Schreiboperationen werden in API/Dienst, im lesenden Client und vor dem ersten seriellen Byte abgewiesen. Zusätzlich werden Payload-Längen der erlaubten Lesebefehle geprüft.

Protokoll-/DB-Fehler oder ein Sammeldurchlauf über 120 Sekunden beenden den Hardwareprozess mit Fehlerstatus. `OnFailure` löst die Rückkehr aus. Der unabhängige Timer beendet das Fenster spätestens nach 15 Minuten; `RuntimeMaxSec` begrenzt zusätzlich die Laufzeit des Testdienstes. Keiner der neuen Hardwaredienste wird für den Systemstart aktiviert; beim Neustart bleibt der vorhandene p4d-Autostart maßgeblich.

`rollback` stoppt den gesamten Testdienst, prüft die Portfreigabe und startet erst danach p4d. Anschließend prüft es bis zu 90 Sekunden ausschließlich lesend, ob neue Originalmesspunkte erscheinen. Ein fehlender Messpunkt wird ausdrücklich als unbestätigte Aufzeichnung gemeldet. Wenn ein fremder Prozess den Port hält, wird kein zweiter Prozess parallel gestartet; die Rückkehr meldet den Fehler und die systemd-Rückkehraktion versucht es erneut. Ein Hardware-/Hostausfall lässt sich durch einen Timer nicht ausschließen.

## Erfolg und Auswertung

Erwartet werden mindestens fünf erfolgreiche Sammeldurchläufe, plausible Firmware-/Status-/Messdaten, frisch lesbare Parameter im Webmenü und keine Schreibmöglichkeit. Danach müssen p4d wieder aktiv und neue Originalmesspunkte nachweisbar sein.

Private Daten verbleiben auf dem Host:

- Fensterzustand und Ergebnis: `/var/lib/froeling-bridge-coordinator/window.json`
- begrenzte RX-/TX-Spur und letzter Sammlerstatus: `/var/lib/froeling-bridge-test/`
- Messpunkte: jeweilige `froeling_bridge_test_<fenster-id>`-Datenbank des separaten Containers.

Spuren enthalten reale Betriebsdaten und gehören nicht ins Repository. Es werden nur bereinigte Befunde und belegte Antwortzuordnungen dokumentiert. Die Installation bleibt nach dem Test erhalten; der Hardwaredienst ist gestoppt. Die Vorschau bleibt ein Simulator.

## Reproduzierbare Prüfungen

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
FROELING_TEST_DB_CONFIG=.local/test-database.json \
  PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
python3 docs/tools/verify_protocol_examples.py
```

Zusätzlicher ausdrücklich aktivierter **lokaler** systemd-Test mit einmaligen Ersatzdiensten, ohne Zugriff auf p4d, USB oder Datenbanken:

```bash
sudo .venv/bin/python -I docs/tools/verify_host_rollback.py --run-local-spares
```

Er startet ausschließlich eindeutig benannte `/bin/sleep`-Ersatzdienste, prüft Rückkehr durch Timer und nach SIGKILL und entfernt seine Einheiten wieder. Nicht mit dem echten Hardwaretest verwechseln.

Bereits lokal geprüft: Browserabläufe in Chromium inklusive mobiler Darstellung, Protokoll-/Client-/HTTP-Schreibsperren, Pseudo-Terminal mit echten seriellen Bytes, unabhängige Rückkehr mit echten systemd-Ersatzdiensten sowie Sammlung in separater MariaDB bei unveränderter Metadaten-Quelldatenbank. Der tatsächliche Test am Zielhost steht bis zur administrativen Einrichtung noch aus.
