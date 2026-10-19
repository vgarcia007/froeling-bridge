# API benutzen: Schritt für Schritt

Mit der API kann ein anderes Programm Heizungsdaten abfragen. `curl` ist ein kleines Terminalprogramm, das solche Anfragen stellt. Die Antwort kommt als JSON: eine Textdarstellung mit benannten Feldern und Werten.

Diese Anleitung verwendet unsere laufende Anlage **https://heizung.example.org**. Bei einer anderen Installation ersetzt du diese Adresse durch deren HTTPS-Adresse. Alle Beispiele lesen ausschließlich Daten.

## 1. Einen API-Schlüssel besorgen

Der Serverbetreiber erstellt den Schlüssel auf dem **Heizungsrechner**, beispielsweise für den vorhandenen Benutzer `NAME`:

```sh
sudo froeling-bridge-users key-create NAME --label mein-client --scope read
```

`NAME` durch den tatsächlichen Benutzernamen ersetzen. Der vollständige Schlüssel wird nur einmal angezeigt. Er ist der Zugang für dein Programm; dein normales Login-Passwort brauchst du für die folgenden Abfragen nicht. Benutzer anlegen und Schlüssel sperren: [Zugang verwalten](authentication.md#benutzer-auf-der-konsole-verwalten).

## 2. Terminal vorbereiten

Die folgenden Befehle sind für ein **Bash-Terminal unter Linux**, beispielsweise auf dem Heizungsrechner. Benötigt werden `curl` und für die lesbare Darstellung `python3`. Es ist egal, in welchem Verzeichnis du stehst; gespeicherte Dateien landen im aktuellen Verzeichnis.

Diese drei Zeilen kopieren:

```bash
API_URL="https://heizung.example.org"
read -r -s -p 'API-Schlüssel einfügen und Enter drücken: ' API_KEY
printf '\n'
```

Bei der Nachfrage den vollständigen Schlüssel einfügen und Enter drücken. Währenddessen bleibt die Eingabe unsichtbar. Der Schlüssel wird so nicht als eingegebener Befehl in der Terminal-Historie gespeichert.

**Alle weiteren Beispiele im selben Terminal ausführen.** `$API_URL` und `$API_KEY` werden automatisch durch die dort hinterlegten Angaben ersetzt. Bei einem neuen Terminal Schritt 2 wiederholen.

## 3. Heizungsstatus abrufen

Gemeint ist der Betriebszustand der Heizung, etwa „Heizen“ oder „Betriebsbereit“, nicht nur die Erreichbarkeit der Software.

Diesen gesamten Block kopieren:

```bash
curl --fail --silent --show-error \
  --header "Authorization: Bearer $API_KEY" \
  "$API_URL/api/v1/values" \
  | python3 -c 'import json, sys
items = json.load(sys.stdin)["items"]
status = next((x for x in items if x["type"] == "UD" and x["address"] == 1), None)
print(json.dumps(status, ensure_ascii=False, indent=2))'
```

`curl` holt die zuletzt erfassten Werte. Der Teil nach `|` wählt daraus den Heizungsstatus aus und stellt ihn lesbar dar. `UD` mit Adresse `1` ist eine feste Statuskennung der Bridge, keine zu erratende Temperaturfühleradresse.

Die Ausgabe enthält beispielsweise diese Felder (gekürzt, Werte nur als Beispiel):

```json
{
  "type": "UD",
  "address": 1,
  "text": "Heizen",
  "observed_at": "2026-10-19T12:00:00+02:00",
  "stale": false,
  "origin": "controller"
}
```

- `text`: der lesbare Heizungszustand.
- `observed_at`: wann dieser Zustand aus der Heizung gelesen wurde.
- `stale: false`: der Wert gilt nach den Aktualitätsregeln der Bridge als aktuell.
- `stale: true`: der Wert ist veraltet oder seine Aktualität kann nicht bestätigt werden. Nicht ungeprüft als gegenwärtigen Zustand anzeigen.
- Ausgabe `null`: bislang liegt kein Statuswert vor.

Die Antwort kommt aus dem laufend aktualisierten Arbeitsspeicher der Bridge. Diese GET-Anfrage löst **keine zusätzliche serielle Abfrage** aus und liest den Status nicht aus der MariaDB-Historie. Im eigenständigen Betrieb wird der Status normalerweise alle zehn Sekunden erfasst, die übrigen ausgewählten Messwerte standardmäßig alle 60 Sekunden. Zeitstempel und `stale` immer mit auswerten. Nach einem Neustart kann ein lokal gespeicherter Wert mit `origin: "local-persisted"` erscheinen; er ist als veraltet markiert.

## 4. Alle Sensoren mit ihren letzten Werten ansehen

Für den ersten Überblick:

```bash
curl --fail --silent --show-error \
  --header "Authorization: Bearer $API_KEY" \
  "$API_URL/api/v1/sensors" \
  | python3 -m json.tool
```

Die Liste enthält den vollständigen bekannten Sensorkatalog, einschließlich nicht zur Abfrage ausgewählter Sensoren. Bei jedem Sensor stehen unter anderem:

| Feld | Bedeutung |
| --- | --- |
| `title` / `usrtitle` | Bezeichnung / gegebenenfalls eigener Anzeigename |
| `type` und `address` | Zusammengehörige Kennung dieses Sensors für weitere Zugriffe |
| `active` | Wird regelmäßig abgefragt |
| `recording` | Wird zusätzlich als Historienwert gespeichert |
| `latest` | Letzter erfasster Wert einschließlich Zeitstempel und Aktualität |

`latest: null` heißt, dass noch kein Wert vorliegt, beispielsweise weil dieser Sensor nicht abgefragt wird. Nicht jeder Katalogeintrag steht für ein tatsächlich eingebautes Bauteil. Die gemessene Zahl steht in `latest.value`, ein Zustandstext gegebenenfalls in `latest.text`; die Einheit steht beim Sensor unter `unit`.

Suche zunächst nach der Bezeichnung, beispielsweise „Boiler 1“ oder „Kesseltemperatur“. Verwende danach die dort gefundene Kombination aus `type` und `address`. Für Temperatursensoren keine Adressen aus Beispielen anderer Anlagen übernehmen.

Alles in eine Datei speichern:

```bash
curl --fail --silent --show-error \
  --header "Authorization: Bearer $API_KEY" \
  "$API_URL/api/v1/sensors" \
  --output sensoren.json
```

Die Datei `sensoren.json` kannst du mit einem Texteditor öffnen oder an einen Entwicklungsagenten zur Auswertung geben. Sie enthält Heizungsdaten, aber nicht deinen API-Schlüssel.

Das ist ein Abruf des Katalogs mit den bereits vorliegenden Werten, kein Befehl, alle möglichen Sensoren sofort aus der Heizung zu lesen. Es ist auch kein vollständiges Datenbank-Backup. Menüzweige, Historie und Fehlerseiten werden separat abgefragt.

## 5. API-Dokumentation ansehen oder herunterladen

Im Browser zuerst auf **https://heizung.example.org** anmelden. Danach diese Adresse öffnen:

**https://heizung.example.org/api/v1/openapi.json**

Dort steht die technische Beschreibung aller Routen, Eingaben und Antworten im OpenAPI-Format. Es ist eine JSON-Datei, keine interaktive Swagger-Oberfläche. Du kannst sie einem Entwicklungsagenten zusammen mit dieser Anleitung geben. Ein API-Schlüssel gehört in dessen private Clientkonfiguration, nicht in die Dokumentationsdatei.

Mit `curl` herunterladen:

```bash
curl --fail --silent --show-error \
  --header "Authorization: Bearer $API_KEY" \
  "$API_URL/api/v1/openapi.json" \
  --output openapi.json
```

Die technische Beschreibung liegt außerdem ohne Login im [Repository](../src/froeling_bridge/openapi.json). Sie muss zur Version deiner Installation passen.

## 6. Weitere nützliche Abfragen

Im Befehl aus Schritt 4 kannst du `/api/v1/sensors` durch einen dieser Pfade ersetzen:

| Pfad | Inhalt |
| --- | --- |
| `/api/v1/values` | Alle bereits erfassten letzten Werte, ohne vollständigen Sensorkatalog |
| `/api/v1/plant` | Zuordnung zu Kessel, Puffer, Boiler und Heizkreisen |
| `/api/v1/errors` | Gespeicherte Fehlerhistorie; standardmäßig höchstens 100 Einträge pro Seite |
| `/api/v1/errors?source=controller` | Zuletzt ausgelesener Fehlerspeicher der Steuerung |
| `/api/v1/time-programs` | Bekannte Zeitprogramme und Cacheinformationen |
| `/api/v1/menu?parent=1` | Oberste Ebene des Heizungsmenüs; Untermenüs separat laden |
| `/api/v1/health` | Informationen zur Bridge und ihren verfügbaren Funktionen |
| `/api/v1/runtime` | Heizungsverbindung, laufende Erfassung und Datenbankspeicherung |

Bei Fehlern bedeutet `active: true` bestätigt aktiv, `false` bestätigt nicht aktiv und `null` unbekannt. Der gespeicherte Zustandstext allein beweist keine aktuell bestehende Störung. Für alle Fehlerseiten `limit` und `offset` gemäß OpenAPI verwenden; eine erste Antwort ist nicht zwingend die ganze Historie.

## Wenn es nicht funktioniert

| Meldung | Was tun? |
| --- | --- |
| `curl: command not found` | `curl` fehlt auf dem verwendeten Rechner. |
| `python3: command not found` | `python3` fehlt. Ohne den Teil ab `|` zeigt curl die JSON-Antwort unformatiert. |
| HTTP `401` | Schlüssel fehlt, wurde falsch kopiert, ist abgelaufen oder wurde gesperrt. |
| HTTP `403` | Der Zugriff ist für diesen Schlüssel nicht erlaubt. |
| HTTP `429` | Zu viele Anfragen; eine Pause einlegen. |
| HTTP `503` | Dienst vorübergehend nicht verfügbar; Serverbetreiber informieren. |
| Zertifikats- oder Verbindungsfehler | HTTPS-Adresse, Netzwerk und Zertifikat prüfen. |
| Zusätzlicher JSON-Fehler nach einer curl-Fehlermeldung | Zuerst den curl-Fehler beheben: Ohne gültige Antwort kann Python nichts darstellen. |

Für diese Abfragen genügt ein Nur-Lesen-Schlüssel. Die normale Browser-Anmeldung ersetzt in curl keinen API-Schlüssel.

Wenn du fertig bist, den Schlüssel aus der aktuellen Terminal-Sitzung entfernen:

```bash
unset API_KEY
```
