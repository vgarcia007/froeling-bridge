# Anmeldung und API-Zugang ab 0.7.0

Im produktiven Betrieb sind GUI und `/api/v1` geschützt, auch im LAN. Die Browser-Anmeldung verwendet Benutzername und Passwort ohne zweiten Faktor. Benutzer, Passwörter und API-Schlüssel verwaltet ausschließlich der Serverbetreiber auf der Konsole. Es gibt keine Registrierung, Passwortänderung oder Passwortwiederherstellung im Web.

## Einrichtung und HTTPS

Der native Installer richtet die lokale Zugangsdatenbank und einen eigenen Leseschlüssel für die Gesundheitsprüfung ein. Bei der Ersteinrichtung erzeugt er `operator` mit Schreibrechten und einem zufälligen Passwort. Auf dem Heizungsrechner abholen:

```sh
sudo cat /var/lib/froeling-bridge-installer/initial-login.json
```

Nach Übernahme in den Passwortmanager die einmalige rootgeschützte Übergabedatei entfernen. Das Passwort kann jederzeit auf der Konsole ersetzt werden. Gewöhnliche Konten speichern ausschließlich Passwort-Hashes.

Die geschützte Konfiguration erhält zusätzlich:

```json
"auth": {
  "public_origin": "https://heizung.example.org",
  "trusted_proxy": "192.0.2.20"
}
```

`public_origin` ist die genaue HTTPS-Adresse ohne Unterpfad. `trusted_proxy` ist genau die IP des Reverse Proxy, niemals `*`. Die [Apache-Vorlage](../deploy/apache/froeling-bridge.conf.example) reicht Authorization/Cookies weiter und bereinigt fremde Proxy-Header. Browser verwenden die HTTPS-Adresse auch im LAN. Unverschlüsselter Browser-Login am Backend ist gesperrt; lokale Monitor-Anfragen dürfen Bearer-Schlüssel über Loopback verwenden.

Bei HTTP zwischen Reverse Proxy und Bridge endet die Verschlüsselung am Proxy: Passwörter, Cookies und API-Schlüssel sind auf diesem internen Abschnitt unverschlüsselt. Diese Variante setzt ein vertrauenswürdiges LAN voraus. Keine zusätzliche öffentliche Portweiterleitung auf den Backend-Port einrichten. Fehlende/defekte Authentifizierung schaltet niemals auf anonymen Zugriff zurück. `/healthz` liefert öffentlich nur `{"status":"ok"}`, keine Heizungsdaten.

## Benutzer auf der Konsole verwalten

Auf dem Heizungsrechner:

```sh
sudo froeling-bridge-users add gast --role read
sudo froeling-bridge-users add bediener --role write
sudo froeling-bridge-users list
sudo froeling-bridge-users password gast
sudo froeling-bridge-users role gast --role write
sudo froeling-bridge-users disable gast
sudo froeling-bridge-users enable gast
```

Passwörter werden verdeckt eingegeben und bestätigt, nicht als Kommandozeilenargument übergeben. Länge: 15–128 Zeichen; Passphrasen sind möglich. `add` und `password` unterstützen zusätzlich `--generate-password` zur einmaligen Konsolenausgabe. Im Quellcheckout lautet der Einstieg `python -m froeling_bridge users --state-dir /privater/zustand …`.

| Rolle | Rechte |
| --- | --- |
| `read` – Nur Lesen | Messwerte, Historie, Fehler, Menü und Zeitprogramme ansehen; vorhandene lesende Aktualisierungen auslösen |
| `write` – Lesen + Schreiben | Zusätzlich freigegebene Heizungsparameter und Abfrage-/Historienauswahl ändern sowie Anlagenabfrage aktivieren |

Die Rolle hebt keine Hardware-Sperre auf. Zeitprogramme bleiben sichtbar, aber deaktiviert, solange `write_time_range` auf der Anlage nicht freigegeben ist. Das gilt auch für Schreibbenutzer und deren API-Schlüssel. Benutzerverwaltung bleibt bei beiden Rollen auf der Konsole.

Passwortsetzen beendet alle Browser-Sitzungen. Eine Kontosperre beendet Sitzungen und widerruft die Schlüssel; nach erneuter Aktivierung sind neue Schlüssel erforderlich. Rollenänderungen gelten bei der nächsten Anfrage und werden bei wartenden Heizungs-Schreibjobs nochmals unmittelbar vor Ausführung geprüft.

## API-Schlüssel für Programme

Für die praktische Nutzung: [Einfache curl-Anleitung mit Heizungsstatus und allen Sensoren](api-einstieg.md).

Pro Client einen eigenen benannten Schlüssel erzeugen:

```sh
sudo froeling-bridge-users key-create gast --label monitoring --scope read
sudo froeling-bridge-users keys gast
sudo froeling-bridge-users key-revoke SCHLUESSEL_ID
```

Der vollständige Schlüssel erscheint nur bei der Erzeugung. Die ID aus `keys` dient zum Widerruf und ist kein Anmeldeschlüssel. Standard ist `read`; `--scope write` setzt einen Benutzer mit Schreibrechten voraus. Wirksam sind die geringeren Rechte aus aktueller Benutzerrolle und Schlüsselberechtigung. Ohne `--expires-days ANZAHL` läuft der Schlüssel bis zum Widerruf; bei Rotation können alter und neuer Schlüssel kurz überlappen. Passwortwechsel ändern unabhängig erzeugte Schlüssel nicht.

Jede Anfrage verwendet:

```http
Authorization: Bearer DEIN_API_SCHLUESSEL
```

Keine Schlüssel in URLs, Chat, Git oder Browser-LocalStorage. Clientkonfigurationen mit Schlüsseln privat halten. Beispiel für Python mit privater Umgebungsvariable:

```python
import json, os
from urllib.request import Request, urlopen
request = Request("https://heizung.example.org/api/v1/sensors",
                  headers={"Authorization": "Bearer " + os.environ["FROELING_API_KEY"]})
with urlopen(request) as response:
    sensors = json.load(response)
```

Die geschützte OpenAPI-Dokumentation unter `/api/v1/openapi.json` beschreibt denselben Header. Datenrouten bleiben erhalten. 401 bedeutet fehlende/ungültige Anmeldung; 403 fehlende Rechte, CSRF-Schutz oder Hardwarefreigabe; 429 eine Begrenzung mit `Retry-After`; 503 einen vorübergehend nicht verfügbaren Dienst. Unklare Heizungs-Schreibaufträge niemals blind wiederholen: den Wert zuerst neu lesen.

Auf dem Handy öffnet der Knopf „Menü“ die Navigation. Benutzername, Rolle und „Abmelden“ stehen unter den Navigationspunkten; auf dem Desktop unten in der Seitenleiste.

## Sitzungen, Speicherung und Überwachung

Sitzungen liegen serverseitig mit einem Secure/HttpOnly/SameSite-Strict-Cookie. Sie enden nach 30 Minuten ohne Anfragen, spätestens nach zwölf Stunden; GUI-Abfragen zählen als Anfragen. Logout widerruft die Sitzung. Browser-POST/PATCH benötigen zusätzlich den CSRF-Header aus `/api/v1/auth/me` und dieselbe Origin. API-Schlüssel benötigen keinen CSRF-Token.

`auth.sqlite3` im privaten Zustandsordner enthält Benutzer, Argon2id-Passwort-Hashes (64 MiB, drei Durchläufe, Parallelität eins), SHA-256-Hashes zufälliger Schlüssel/Sitzungskennungen und Sicherheitsereignisse. Modus 0600; keine Klartextpasswörter oder vollständigen API-Schlüssel darin. Es ist keine Vollverschlüsselung der SQLite-Datei. Sicherungen sind vertraulich und bewahren Benutzer/Schlüssel; Sitzungen werden bei Wiederherstellung verworfen.

Anmeldeversuche sind je Benutzer/IP und IP begrenzt; höchstens zwei Passwortprüfungen laufen gleichzeitig. Authentifizierte Anfragen: 300 pro Minute und Zugang; zusätzliche Heizungsjobs: 120 pro Minute und Benutzer. Sicherheitsereignisse bleiben 30 Tage erhalten. Diese Maßnahmen ersetzen keinen gepflegten Host und keine korrekte HTTPS-/Proxy-Konfiguration.

Die native Überwachung verwendet `bridge-monitor` und `/etc/froeling-bridge/monitor-api-key` (root, 0600). Diesen Benutzer nicht für gewöhnliche Clients verwenden. Abgelehnte Monitor-Anmeldungen und ein ausgefallener Authentifizierungsspeicher lösen keinen Bridge-Neustart aus. Zur Wiederherstellung des Monitorzugangs: `sudo /opt/froeling-bridge/0.7.0/venv/bin/python -I -m froeling_bridge.auth_setup`. Demo-Modi bleiben fiktiv und ohne Anmeldung; sie dürfen keinen produktiven Zugang ersetzen.
