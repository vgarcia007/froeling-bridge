# Heizungsdaten über MCP lesen

Der zusätzliche MCP-Dienst stellt aktuelle Werte, gespeicherte Messreihen und das Heizungsmenü über **Streamable HTTP unter `/mcp`** bereit. Ein KI-Client findet Sensoren anhand ihrer Namen und fragt anschließend Werte und Historie ab.

MCP gehört zu diesem Repository, läuft aber separat: auf dem Bridge-Rechner oder einem anderen Rechner im Netz. Er benötigt ausschließlich die bestehende API und einen eigenen Leseschlüssel. Der Heizungsdienst wird dafür nicht neu gestartet.

## Ausschließlich Lesen

- Neun fest definierte Lesewerkzeuge; keine Schreibwerkzeuge, beliebigen URLs, SQL-Abfragen oder Heizungsjobs.
- Ausschließlich GET an erlaubte API-Routen; keine Weiterleitungen oder Umgebungs-Proxys.
- Eigener Bridge-Benutzer mit Rolle `read` und Schlüssel mit Scope `read`. Beim Start und vor jedem Datenabruf werden die effektiven Rechte geprüft. Schreibschlüssel und fehlende Anmeldung werden abgelehnt.
- Ein **anderes MCP-Bearer-Token** schützt jeden HTTP-Aufruf, auch auf localhost.
- Bei nativer Installation eigener Dienstbenutzer ohne Gerätezugriff und ohne Zugriff auf den lokalen Bridge-Zustand. Keine direkte MariaDB-Verbindung.

Es gibt keinen OAuth-Login; der Client muss HTTP-Bearer-Header unterstützen. Zugangsdaten ausschließlich in privaten Umgebungsdateien beziehungsweise der Clientumgebung speichern.

## 1. Bridge-Lesezugang erstellen

Auf dem **Heizungsrechner**:

```sh
sudo froeling-bridge-users add mcp-reader --role read --generate-password
sudo froeling-bridge-users key-create mcp-reader --label heating-mcp --scope read
```

Das Passwort privat verwahren. MCP benötigt den API-Schlüssel aus dem zweiten Befehl. [Schlüsselverwaltung und Widerruf](authentication.md).

## 2. MCP installieren

MCP benötigt **Python 3.11 oder neuer** mit `venv` und passender Architektur. Die Bridge funktioniert weiterhin ab Python 3.9. Das offizielle SDK `mcp==2.3.0` wird separat installiert. Auf älteren 32-Bit-Systemen ist eine passende neuere Laufzeit oder ein anderer MCP-Rechner erforderlich.

Im Checkout auf dem **MCP-Rechner**:

```sh
install -m 600 deploy/mcp.env.example /tmp/froeling-mcp.env
nano /tmp/froeling-mcp.env
```

Eintragen:

- `BRIDGE_MCP_API_URL`: Ursprung der API, beispielsweise `https://heizung.example.org`, ohne `/api/v1`.
- `BRIDGE_MCP_API_KEY`: der eigene Bridge-Leseschlüssel.
- `BRIDGE_MCP_TOKEN`: ein anderes zufälliges Token, mindestens 32 Zeichen. Erzeugen mit `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`.

Dann installieren, gegebenenfalls den Python-Pfad anpassen:

```sh
sudo bash deploy/install-mcp.sh --python /usr/bin/python3.11 --config /tmp/froeling-mcp.env
rm /tmp/froeling-mcp.env
systemctl status froeling-bridge-mcp.service
```

Der Installer erstellt `/opt/froeling-bridge-mcp/venv`, den Benutzer `froeling-mcp`, die rootgeschützte `/etc/froeling-bridge-mcp.env` und den eigenen Autostartdienst. Er verändert weder p4d noch den Bridge-Dienst. Eine Wiederholung aktualisiert ausschließlich MCP; ohne `--config` bleibt die vorhandene Konfiguration erhalten.

Standardadresse: **`http://127.0.0.1:8767/mcp`**. Jeder Aufruf benötigt `Authorization: Bearer <BRIDGE_MCP_TOKEN>`. Das ist das MCP-Token, nicht der Bridge-Schlüssel.

Für direkten Heimnetzzugriff `BRIDGE_MCP_HOST=0.0.0.0` setzen und den genauen HTTP-Host inklusive Port in `BRIDGE_MCP_ALLOWED_HOSTS` erlauben, etwa `mcp-rechner.local:8767`. HTTP im LAN ist unverschlüsselt. Für Internetzugriff HTTPS am Reverse Proxy einrichten, `/mcp` weiterreichen, Authorization erhalten und den öffentlichen Host erlauben. Der MCP-Port muss dafür nicht öffentlich freigegeben werden. Keine Host-Wildcards verwenden; die DNS-Rebinding-Prüfung bleibt aktiv.

Nach Änderungen ausschließlich `sudo systemctl restart froeling-bridge-mcp.service` ausführen. Bei ausgefallener Bridge versucht MCP seinen eigenen Start erneut; der Heizungsdienst wird dadurch nicht gesteuert.

## Werkzeuge

| Werkzeug | Inhalt |
| --- | --- |
| `list_sensors` | Katalog mit IDs, Namen, Einheiten, Aufzeichnungsflags und letztem Wert; Seiten über `offset` |
| `search_sensors` | Suche nach Original-/eigenem Namen oder ID |
| `get_current_values` | Letzte Beobachtungen für bis zu 32 gefundene Sensor-IDs |
| `get_system_overview` | Funktionale Zuordnung zu Kessel, Puffer, Boiler und Heizkreisen |
| `get_history` | Aufgezeichnete Messreihen mit Begrenzung und Fortsetzung |
| `get_errors` | Steuerungsmeldungen oder gespeicherte Fehlerhistorie |
| `get_menu`, `search_menu` | Menüpfade und zwischengespeicherte Anzeigen |
| `get_time_programs` | Zeitprogrammcache mit Geräte-/Wochentagsnamen |

Beispiel: `search_sensors(query="Boiler 1")`, passende `sensor_id` aus der Antwort übernehmen, dann `get_current_values(sensor_ids=["VA:93"])`. Die ID ist nur ein Beispiel und muss aus der eigenen Discovery stammen.

## Aktualität und Historie

Aktuelle Werte stammen aus der laufenden Erfassung. MCP löst keine neue Heizungsabfrage aus. `observed_at`, `origin`, `stale` und `latest=null` bleiben erhalten. Ein Pumpenbefehl beweist keinen Wasserfluss; die Anlagenübersicht ist kein bestätigter Rohrleitungsplan. Menüs und Zeitprogramme zeigen ausschließlich vorhandene Cachewerte.

`get_history` liest nur vorhandene Aufzeichnungen. `resolution="raw"` entspricht p4d-Rohpunkten (`S`), `"aggregated"` der gespeicherten Verdichtung (`A`). Ältere Rohpunkte können verdichtet sein; beide Reihen bewusst getrennt abfragen. Keine nachträglichen Messungen oder Interpolation.

Start ist einschließlich, Ende ausschließlich. Beispiel: `start="2026-01-01T00:00:00+01:00"`, `end="2026-01-02T00:00:00+01:00"`. Zeitangaben mit Offset werden auf die lokale Datenbankzeit `Europe/Berlin` umgerechnet; ohne Offset gelten sie als lokale Zeit. Die Datenbank speichert keine Zeitzone pro Punkt: die doppelte Stunde bei der Zeitumstellung bleibt uneindeutig. Maximal 366 Tage und 999 Punkte pro Aufruf, Standard 500. Bei `truncated=true` mit `next_start` und unverändertem Ende/Auflösung fortsetzen. Längere Zeiträume aufteilen.

Fehler behalten `active=true/false/null`, Zeitstempel, Quellen und Fallbackkennzeichnung. Ein historischer Status „gekommen“ allein belegt keinen aktuell aktiven Fehler.

## Entwicklung und Prüfung

Separate Umgebung, unabhängig vom laufenden Dienst:

```sh
python3.11 -m venv .local/mcp-dev
.local/mcp-dev/bin/python -m pip install '.[mcp]'
PYTHONPATH=src .local/mcp-dev/bin/python -m unittest discover -s mcp_tests -v
PYTHONPATH=src python3 -m unittest discover -s tests -p test_mcp_api.py -v
```

Die HTTP-Prüfung verwendet den offiziellen MCP-Client und eine simulierte Bridge. Sie prüft Bearer-Schutz, alle Werkzeuge, abgelehnte Schreibwerkzeuge und die Sperre bei nachträglich erkannten Schreibrechten. Keine echte Heizungsänderung.

Grundlagen: [offizielles Python-SDK](https://github.com/modelcontextprotocol/python-sdk), [Streamable HTTP](https://py.sdk.modelcontextprotocol.io/run/).
