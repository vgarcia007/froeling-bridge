# Arbeitskontext für Fröling Bridge

## Einstieg in jede Session

1. `git status --short --branch` und Submodulstatus prüfen; vorhandene Benutzeränderungen erhalten.
2. `docs/project-context.md` und `docs/decisions.md` lesen. Falls vorhanden, zusätzlich `.local/operator-context.md` lesen; dort liegen ausschließlich lokale Betreiberangaben. Öffentliche Beispieladressen sind keine Live-Ziele.
3. Für Fachfragen `docs/README.md` und die dort verlinkte Bestandsaufnahme lesen. Quellcode ist die Autorität für Bestandsverhalten; Annahmen und Empfehlungen davon unterscheiden.

Mit dem Benutzer auf Deutsch und konkret kommunizieren. Er möchte schrittweise einen Python-Nachbau auf Grundlage belegter Protokoll-/Datenbankkenntnisse entwickeln und hat die autonome Umsetzung des Offline-Kerns beauftragt. Routineentscheidungen selbst treffen und dokumentieren; nur bei tatsächlich fehlenden Freigaben oder blockierenden Informationen nachfragen.

## Ziel und feste Grenzen

- p4d ist die verbindliche funktionale Vorlage. Vor Änderungen den vollständigen relevanten Ablauf in Protokoll, Dienst, Datenbank und Webmenü sowie die bestehenden Fachnotizen abgleichen. Namen, Menüpfade, Adress-/Wochentagszuordnung und Cacheverhalten gehören zum Funktionsumfang, nicht zu späteren kosmetischen Extras. Benutzer möchte nicht erneut auf bereits dokumentiertes Originalverhalten hinweisen müssen.
- Empfangene Heizungsdaten nach dem Original verlustfrei lesen; keine Eingabevalidierung auf Rohantworten anwenden. Abweichungen ausdrücklich belegen, begründen und testen. Moderne Darstellung darf keine namenlosen Rohadressen oder zusätzliche manuelle Leseschritte anstelle vorhandener p4d-Funktionen einführen.

- Schwerpunkt: Heizung lesen, Parameter zuverlässig schreiben, moderne API und Servicemenü; einfache Installation.
- Bestehende MariaDB und historische Messreihen weiterführen; p4d als Rückfalloption erhalten.
- Kein dauerhafter Parallelbetrieb zweier unabhängiger serieller Heizungsdienste als Default.
- Charts, Dashboards, Pelletverwaltung und weitere Integrationen zunächst außerhalb des Kernumfangs.
- Lokaler API-Prototyp: Flask 3.1/Waitress 3, PyMySQL 1.1 und /api/v1; siehe docs/service.md. Webmenü: paketiertes HTML/CSS/JavaScript. Lesender Hosttest mit Rückkehr: docs/host-test.md. Produktionsauthentifizierung und native Installation sind umgesetzt; Projektlizenz ist GPLv2 (`GPL-2.0-only`); fremde Copyright-Hinweise bleiben erhalten (LICENSE/NOTICE.md). Siehe docs/authentication.md.
- Die vollständige Danksagung im README steht direkt nach dem Intro vor der Installation. Bei Vereinfachungen nicht ans Ende verschieben oder kürzen.
- Herkunft und Arbeit von Jörg Wendel und den p4d-Mitwirkenden respektvoll würdigen. Keine unbelegte Kritik oder Behauptung einer offiziellen Zusammenarbeit.

## Aktuelle Lizenz: GPLv2

Benutzer hat die vorherige MIT-Aufteilung ausdrücklich durch „mach gpl“ ersetzt. Aktueller Projektstand einheitlich GNU GPL Version 2, ausschließlich diese Version (`GPL-2.0-only`): LICENSE enthält den unveränderten GPLv2-Text, README/NOTICE.md und Paketmetadaten stimmen überein. Fremde Copyright-/Lizenzhinweise und die Danksagung direkt nach dem Intro bleiben erhalten. Doppelte GPL-Datei unter LICENSES entfernt; Paket enthält LICENSE und NOTICE.md. Frühere bereits erteilte MIT-Rechte an damaligen eigenen Beiträgen werden nicht rückwirkend widerrufen; dies steht in NOTICE.md. Keine Änderung am laufenden Dienst.

## Sofort nutzbares Parameterschreiben / öffentliches README 0.7.2

Benutzer verlangt, dass eine Neuinstallation unmittelbar alle bereits angebotenen Funktionen bereitstellt, insbesondere normales Parameterschreiben ohne erneute eigene Abnahme/Freischaltung. Zudem soll das README von einem öffentlichen Repository ausgehen: HTTPS-Clone-URL, kein GitHub-/SSH-Zugang als Voraussetzung. Danksagung unverändert direkt nach dem Intro erhalten.

Quellstand 0.7.2: `serve_standalone` erlaubt ohne `write_validation` standardmäßig `write_parameter` und verwendet dafür den normalen schreibfähigen Client. Benutzer-/API-Schlüsselrechte, bearbeitbare p4d-Menütypen, frische Grenzen/Skalierung, Nachlesen und keine automatische Wiederholung unklarer Änderungen bleiben erhalten. Bereits ausdrücklich konfigurierte Geräte-/Firmware-/Operationsnachweise wirken weiterhin als Begrenzung. Zeitprogramm-Intervalle behalten die zuvor vereinbarte gesonderte Behandlung; nicht ungeprüft weitere Funktionen oder echte Tests ableiten. Neue Benutzer müssen keine Freischaltdatei erzeugen und keinen LED-Abnahmelauf machen.

README und aktuelle Fachanleitungen korrigiert; historische Abnahmeberichte als solche gekennzeichnet. Isolierter nativer Installer ohne Nachweis geprüft: keine automatischen Heizungsänderungen beim Start, Schreibbenutzer kann Menüparameter über echte HTTP-/Pseudo-Serial-Strecke ändern und bestätigen, ungültiger Bereich wird ohne Schreibtelegramm abgelehnt, Lesebenutzer erhält 403 ohne Übertragung. Neu-/Wiederholungsinstallation erfolgreich. Vollsuite mit separater MariaDB: 281 Tests grün. Produktivhost bleibt unverändert 0.7.0/HTTPS, keine realen Heizungs-Schreibtests, keine Veröffentlichung/Änderung der GitHub-Sichtbarkeit. Private Belege `.local/default-writing-*`.

README-Screenshots auf Benutzerwunsch aus der echten laufenden Installation (19.10.2026, Liveversion 0.7.0) ergänzt: Desktop-Anlagenübersicht, Servicemenü, Parameterdialog und zwei mobile Ansichten unter `docs/images/`. Reale Heizungswerte ausdrücklich zur Darstellung freigegeben; Zugangsdaten bleiben privat. Übersicht sichtbar, weitere Bilder aufklappbar nach den ersten Bedienungsschritten; Danksagung bleibt vorne. Nur lesend navigiert und Parameter angesehen, nichts gespeichert, keine Browserfehler. Privates Aufnahmeprogramm `.local/capture_readme_screenshots.py`.

## Einfacher Erststart und Dokumentation 0.7.1 (noch nicht produktiv ausgerollt)

Benutzer verlangt Raspberry installieren → im Heimnetz direkt `http://RECHNER-IP:8000` → Login. Reverse Proxy ist ausdrücklich eine selten benötigte optionale eigene Einrichtung, keine Voraussetzung und keine Domainfrage im normalen Installer. README als vollständigen einfachen Hauptweg gestalten: Installation, p4d-Übernahme falls nötig, Browseradresse, rootgeschütztes Erstpasswort für operator und eigene Konsolenbenutzer. Danksagung unverändert; Datenbank, API, HTTPS und Entwicklung passend verlinken statt im README vermischen. Technische/historische Details sind keine zusätzlichen Pflichtschritte.

Quellstand 0.7.1 implementiert und getestet: neue interaktive Konfiguration `auth={"mode":"lan"}`, direkte HTTP-Anmeldung mit getrennten HttpOnly-/SameSite-Strict-Cookies, CSRF und bisherigen Raten-/Rollenregeln. Lokale Client-IP und lokale Host-IP/kurzer Rechnername/.local erforderlich. Öffentliches HTTP ist nicht der Betriebsweg; LAN ist bewusst unverschlüsselt. Der Installer zeigt Browseradresse sowie Erstpasswort-/Benutzerbefehle. Bestehende Konfiguration mit HTTPS-public_origin bleibt unverändert, HTTPS behält Secure-/__Host-Cookies und Proxy-Vertrauensgrenze. Keine Abschaltung der Authentifizierung und keine Änderung von Hardware-Schreibnachweisen.

README und Dokumentationsübersicht führen nach Aufgaben; Datenbankkonfiguration aus README in Standalone-Anleitung verschoben, technische Releasehistorie dort reduziert. API-Einstieg verwendet generische lokale Beispieladresse, HTTPS eigener optionaler Abschnitt in Zugangsanleitung. Isolierter nativer Erst-/Wiederholungsinstall mit echtem Dialog, PTY-Discovery, Erstpasswort-Login und eigener Benutzeranlage erfolgreich; Browser beider Rollen im direkten HTTP und HTTPS erfolgreich. Vollsuite mit separater MariaDB: 280 Tests, danach zusätzlicher gezielter Test zum Erhalt vorhandener HTTPS-Konfiguration; acht LAN-Tests grün. Keine produktive Installation/Neustarts/Heizungs-Schreibtests: Der dokumentierte Funktionsstand der Bestandsinstallation bleibt 0.7.0; die tatsächliche Adresse steht ausschließlich im privaten Betreiberkontext. Private Belege `.local/lan-*` und `.local/https-after-lan-browser.log`.

## Einfacher API-Einstieg

`docs/api-einstieg.md` erklärt für Nichtentwickler den Nur-Lesen-Zugang per curl: Schlüssel einlesen, Heizungsstatus UD/1 aus `/values` auswählen, gesamten Sensorkatalog mit letzten Werten abrufen/speichern und geschützte OpenAPI-Datei ansehen/herunterladen. Arbeitsspeicher/Aktualität/Neustartstand und Fehlerseiten ausdrücklich erklärt, keine pauschale Vollabfrage der Hardware oder vollständiges DB-Backup behaupten. Aus README, Dokumentationsübersicht und Anmeldeanleitung verlinkt. Vier kopierte curl-Beispiele und sieben zusätzliche GET-Routen an echter HTTPS-API mit Nur-Lesen-Schlüssel erfolgreich geprüft; keine Heizungs-/Konfigurationsänderung. Privates Prüfwerkzeug `.local/verify_api_guide.py`.

## Home-Verzeichnis des Heizungsrechners bereinigt (19.10.2026)

Unbenutzte Release-/Testverzeichnisse wurden bei erhaltener Erfassung entfernt. Bestandsaufnahme des Benutzerverzeichnisses und konkrete Sicherungsorte bleiben ausschließlich im privaten Betreiberkontext. Künftig keine Releasekopien oder Einmalhelfer im Benutzer-Home ansammeln; aktive Installation und bestehende Sicherungen erhalten.

## Navigation auf Handy und Desktop seit 19.10.2026

Mobiles Aufklappmenü bis einschließlich 650 Pixel: Logo/Menüknopf bleiben sichtbar, sechs Ziele untereinander; nach Auswahl schließen und Fokus auf Ansichtsüberschrift, Escape schließt mit Fokus zurück zum Knopf. Benutzer/Rolle/Abmelden separat unter der Navigation; Desktop-Benutzerbereich unten in der vertikal scrollbar bleibenden Seitenleiste. Verbindungsstatus und Danksagung erhalten, lange Namen/Beschriftungen umbrechen. Kein horizontales Navigationsscrollen. Aktive Ansicht per `aria-current`, Knopfzustand per `aria-expanded`.

Drei Frontenddateien ohne Dienstneustart live ersetzt, Modi/Eigentümer erhalten und Quellenhash aktualisiert; private Sicherung `PRIVATE_SICHERUNG` (Platzhalter; tatsächlicher Ort nur lokal dokumentiert). Laufendes Flask hält die alte HTML-Vorlage im Speicher: JavaScript ergänzt deren Navigationsstruktur bei Bedarf, damit bis zum nächsten regulären Neustart dieselbe Bedienung möglich ist. Diesen Kompatibilitätsweg nicht unbedacht entfernen. Backend/Authentifizierung unverändert, PID und alle Sensorflags erhalten, weiterhin 67 Historienpunkte ohne Erfassungsfehler.

Browserprüfung beider Rollen mit neuer und alter zwischengespeicherter Vorlage, jeweils 320/390/650/768/1440 Pixel: alle sechs Ansichten, echte Maus-/Tastaturbedienung, Escape/Fokus/Viewportwechsel, 64 Zeichen Benutzername, niedrige Desktopfenster, kein seitlicher Überlauf. Live dieselben Navigationsprüfungen und Login/Logout, sichere Cookies, Nur-Lesen-Sperre und deaktivierte Zeitfelder erfolgreich, keine Browser-Ausnahmen. Keine realen Heizungsparameter geändert. Werkzeuge `docs/tools/verify_navigation_browser.py` und erweiterter Auth-Browsercheck; private Nachweise `.local/navigation-*`.

## Produktiver Zugangsschutz 0.7.0 seit 19.10.2026

Anonymisiertes Beispiel für HTTPS über einen Reverse Proxy: `https://heizung.example.org`, Proxy `192.0.2.20`, Backend `192.0.2.10:8000`. Domain und IPs sind Platzhalter, keine Betriebsadressen. Internes HTTP setzt ein vertrauenswürdiges LAN voraus. Backend vertraut ausschließlich diesem Proxy für weitergereichte Header. GUI und API verlangen Anmeldung, auch im LAN; nur `/healthz` und statische Assets sind öffentlich. Kein zusätzlicher öffentlicher Backend-Port. Eine allgemeine Apache-Vorlage liegt im Repository unter `deploy/apache/`; konkrete Zertifikats- und Sitekonfigurationen bleiben privat.

Zwei Rollen `read`/`write`, Benutzername und Passwort ohne MFA. Verwaltung ausschließlich per `sudo froeling-bridge-users …` auf dem Heizungsrechner; keine Web-Passwortänderung. Initialkonto `operator` mit Schreibrechten; zufälliges Erstpasswort nur in root-lesbarer `/var/lib/froeling-bridge-installer/initial-login.json`. Keine Zugangsdaten in Chat, Git oder Logs kopieren. Argon2id-Passworthashes in privater `auth.sqlite3`; benutzergebundene API-Schlüssel mit begrenzbarem Scope, SHA-256 gespeichert und nur einmal ausgegeben. Sichere Sitzungscookies, CSRF-/Origin-Prüfung, Anmelde-/Anfrageraten begrenzt. Details und CLI-Beispiele: `docs/authentication.md`. Konto-Deaktivierung widerruft Sitzungen und Schlüssel, Passwortsetzen nur Sitzungen. Wartende physische Schreibjobs prüfen die aktuellen Rechte unmittelbar vor Ausführung erneut.

Zeitprogramme sichtbar, aber Eingaben und Speichern deaktiviert: vorhandener physischer Schreibnachweis erlaubt ausschließlich `write_parameter`. Rollen heben die Hardwarefreigabe nicht auf. Kein neuer Heizungs-Schreibtest und keine Änderung des Schreibnachweises. Native Überwachung nutzt eigenes Nur-Lesen-Konto `bridge-monitor` und root-lesbare `/etc/froeling-bridge/monitor-api-key`; Auth-Fehler führen nicht zu Neustartschleifen. Auth-Sicherungen erhalten Benutzer/Schlüssel, verwerfen Sitzungen bei Wiederherstellung.

0.7.0 separat vorbereitet, Paketdateien geprüft und nach privater Sicherung kontrolliert gewechselt; Erfassung nach 14,1 Sekunden bereit. Erst nach belegter anonymer Zugriffssperre Apache aktiviert und sanft neu geladen. Alle Sensor-/Recordflags erhalten, weiterhin 149 ausgewählte Sensoren und 67 Historienpunkte pro Zyklus, keine Sammler-/Historienfehler. p4d bleibt inaktiv, `automatic_p4d_fallback=false` und Dauerbetriebspolitik unverändert. Alte Bridge-Versionen erhalten; niemals auf eine ungeschützte Altversion zurückschalten, solange die öffentliche Proxy-Site aktiv ist. Kein Hostneustart.

Private Sicherung/Upgradebericht `PRIVATE_SICHERUNG` (Platzhalter; tatsächlicher Ort nur lokal dokumentiert). Nachweise nur `.local/auth-*`. 273 Tests einschließlich separater MariaDB erfolgreich, isolierte native Neu-/Wiederholungsinstallation und echte HTTPS-Browsertests beider Rollen erfolgreich. Live geprüft: öffentliches Zertifikat/Domain, anonyme API 401, Nur-Lesen-API und Mutationssperre, Operator-Login/Logout, sichere Cookies, Zeitfelder bei 390/1440 Pixel deaktiviert, keine Browser-Ausnahmen. Keine realen Heizungsparameter geändert. Ältere Zugangshinweise und Versionsstände weiter unten sind historische Berichte.

## Aktuelle Vorlaufaufzeichnung seit 19.10.2026

Benutzer möchte auch die Vorlauftemperaturen speichern. Für alle vier Heizkreise je Vorlauf Ist/Soll aus eindeutigem Komponentenmenü auf `record=true` gesetzt (acht VA-Signale), bereits aktive Abfrage unverändert. Nun 67 statt 59 Historienpunkte pro Zyklus, weiterhin 149 ausgewählte frische Sensoren, keine zusätzlichen seriellen Abfragen. Zwei vollständige neue MariaDB-Zyklen einschließlich aller bisherigen 59 Werte unabhängig bestätigt; keine Sammler-/Historienfehler, Auswahlübernahmen null, andere API-/DB-Flags unverändert. API-PID/Neustartzähler und geschützte Konfiguration unverändert, kein Deployment/Neustart/Heizungsparameter-Schreiben. Private Sicherung und Verifikation `PRIVATE_SICHERUNG` (Platzhalter; tatsächlicher Ort nur lokal dokumentiert), lokale Belege `.local/flow-temperature-recording-*`. Bestehender Minutentakt und Verdichtung erhalten. Mischerfahrbefehle weiterhin nicht aufgezeichnet; dieser Auftrag ergänzt ausschließlich Vorlauf Ist/Soll, keinen automatischen Default anderer Anlagen.

## Aktuelle Heizkreis-Einordnung in der GUI

Benutzer möchte die Bedeutung von Vorlauf Ist/Soll, Pumpenansteuerung und Mischerfahrbefehlen in der GUI sehen. Reiner Frontend-Nachtrag: Heizkreiskarten zeigen Vorlauf im Sollbereich (±2 °C), unter/über Soll oder Pumpe nicht angesteuert; fehlende/veraltete/mehrdeutige notwendige Werte ergeben unbekannt. Temperaturbewertung nur bei frisch angesteuerter Heizkreispumpe und eindeutigen Ist-/Sollwerten in °C. Keine Störungsdiagnose, Wärmeleistung, Fördermenge oder Mischerstellung errechnen. Motorbefehle ausdrücklich wärmer/kühler/kein Fahrbefehl; Offline nimmt alte Einordnung zurück.

Live ohne Dienstneustart: zwei statische Dateien atomisch mit erhaltenen Modi/Eigentümern ausgetauscht, Quellenhash aktualisiert, private Sicherung `PRIVATE_SICHERUNG` (Platzhalter; tatsächlicher Ort nur lokal dokumentiert). API-PID unverändert, Erfassung bereit/fehlerfrei und weiterhin 59 Punkte je Zyklus. Bestehenden Browsercheck um Temperaturgrenzen, Pumpenauswahl, fehlende/veraltete/mehrdeutige Werte, widersprüchliche Mischerbefehle und Offline ergänzt; vier Breiten erfolgreich. Produktive Ansicht zusätzlich streng lesend bei 390/1440 Pixel geprüft, keine Heizungsjobs/Mutationen, keine JS-Fehler/Überläufe. Rohbelege `.local/plant-circuit-*`. Backendversion weiter 0.6.0; Sensorflags unverändert.

## Aktuelle Pumpenaufzeichnung und Ursachenanalyse

Benutzer bestätigt je Haus einen gemeinsamen isolierten Zylinder für Puffer und Warmwasserteil. Eine historische Vergleichsreihe zeigt wiederholte enge Abkühlung von Speicher 1 mit dem Kessel, zeitweise deutlich langsamere Abkühlung von Speicher 2. Nahezu identische Boiler-/Puffer-oben-Anzeigen stammen bereits aus p4d; keine falsche Zuordnung oder bestimmte hydraulische Ursache behaupten. Fühlereingänge bisher ungeprüft, historische Pumpenwerte fehlen.

Auf ausdrücklichen Auftrag alle 43 unterstützten pumpenbezogenen Katalogsignale per bestehender Sensor-PATCH-Route lesend aktiviert und zur Historie ausgewählt. 17 zusätzliche Abfragen; 149/149 ausgewählte Werte frisch, 59 Punkte je Sammelzyklus statt 16. Zwei vollständige neue MariaDB-Zyklen unabhängig bestätigt; bisherige 16 Werte weiter aufgezeichnet, andere Flags unverändert, keine Fehler/ausstehenden Einstellungen. API-PID, Neustartzähler und geschützte Konfiguration unverändert; keine Heizungsparameteränderung oder Softwarebereitstellung. Vorzustand/Verifikation privat unter `PRIVATE_SICHERUNG` (Platzhalter; tatsächlicher Ort nur lokal dokumentiert), lokale Belege `.local/pump-recording-*`.

43 Signale sind keine 43 eingebauten Pumpen: darunter mögliche ungenutzte Ausgänge und der Pumpstrom der Breitbandsonde, der keine Heizwasserpumpe ist. Minutentakt und bestehende Verdichtung erhalten. Keine nachträgliche September-Pumpenhistorie, keine tatsächliche Fördermenge aus Ansteuerungen ableiten. Nach mehreren Lade-/Abkühlphasen gemeinsam mit Temperaturen auswerten. Aktuelle Auswahl überschreibt ältere Angaben zu unveränderten Recordflags ausschließlich für diese 43 Signale; kein neuer Default für andere Installationen.

## UI-Nachtrag: Sollwerte direkt an Messwerten

Benutzer beauftragt kleine passende Sollwerte an gemessenen Werten und ausdrücklich direkt live. Nur Frontend geändert: Ist/Soll innerhalb derselben Komponente, berechneter Kesselsollwert vor fester Einstellung, Heizkreis-Vorlauf und Abgas über dynamische Soll-Messwerte, Boiler über gewünschte Temperatur. Keine Grenzwerte/Pufferschwellen als Sollwert darstellen; mehrdeutige Paarungen auslassen. Fehlende/veraltete verwendete Soll-Einstellungen über vorhandenen lesenden Komponentenjob laden, auch bei geschlossenen Details; kein Backend-/Schema-/Flagwechsel.

Live als statischer UI-Nachtrag zu 0.6.0, ohne Dienstneustart; API-PID mit Zustand vor Änderung identisch. Zwei Dateien atomisch ersetzt und Quellenhash aktualisiert; private Sicherung `PRIVATE_SICHERUNG` (Platzhalter; tatsächlicher Ort nur lokal dokumentiert). Beim ersten Dateiaustausch setzte umask 077 die Leserechte zu eng (kurz HTTP 500 auf statische Assets), direkt auf ursprüngliche Modi korrigiert. Bei künftigen atomischen Austauschen immer Modus ausdrücklich mit fchmod nach Erstellen setzen, Besitzer/Gruppe erhalten; nicht auf open(mode) unter umask verlassen. Kein Ausfall der laufenden Erfassung/API. Browser mit unterschiedlichen Boiler-Sollwerten, dynamischer Vorrangregel, fehlender Paarung und Mobil/Desktop geprüft. Rohbelege nur unter `.local/plant-inline-targets-*`.

## Aktueller Livebetrieb 0.6.0 seit 18.10.2026

Benutzer beauftragt ausdrücklich „nun bitte live“, nachdem der nötige kurze Dienstneustart erklärt wurde. Dies autorisiert diesen Rollout einschließlich zusätzlicher Abfragen und lesender Schwellwertinitialisierung. Erledigt: 0.6.0 neben weiterlaufender 0.5.7 installiert und alle Paketdateien geprüft, privates Konfigurations-/SQLite-Backup, kurz kontrolliert gewechselt. Rückkehr bei fehlgeschlagenem Upgrade ausschließlich zur bisherigen Bridge, kein p4d-Start. Bereit nach ca. 12 Sekunden; keine Rückkehr nötig. Dauerpolitik Restart=always und automatic_p4d_fallback=false erhalten, Health-Timer aktiv, alle Upgrade-/Starttimer wieder inaktiv.

Live `/anlage` auf dem vorhandenen API-Host Port 8000. Neun Gruppen, 38 zusätzliche Messwerte über ausdrücklich beauftragte Aktivierung ergänzt; nun 132/132 ausgewählte Werte frisch. Alle 112 zugeordneten Schwell-/Einstellungswerte der neun Gruppen rein lesend erfolgreich initialisiert. Drei bestätigte fehlerfreie Sammelzyklen, weiterhin 16 Messpunkte pro Zyklus, Datenbank-/Fehlerabgleich gesund, keine Warnungen. Alle lokalen und MariaDB-Recordflags unverändert; Konfiguration, Schreibnachweis und Wiederherstellungspolitik bytegleich erhalten. Kein Rechnerneustart oder Heizungs-Schreibtest. Frühere Vorschau-/Nicht-Ausrollangaben weiter unten sind historische Stände.

Privates Backup und Upgradeprotokoll unter `PRIVATE_SICHERUNG` (Platzhalter; tatsächlicher Ort nur lokal dokumentiert); Rohbelege `.local/plant-060-live-*`. Alte Releases erhalten. Ab jetzt wieder ohne neuen Auftrag unverändert produktiv laufen lassen.

Benutzer kritisiert zu viel manuelle Vorbereitung/Nachkontrolle und lange Updateabläufe. Künftige Routineupdates kurz und wiederverwendbar organisieren: vorbereitetes Paket, Sicherung, kurzer Wechsel und kompakte Funktionsprüfung; nicht jedes Mal neue Einzelskripte oder komplette Abnahmen. Eine dauerhafte öffentliche Updatefunktion ist damit als Verbesserungsbedarf festgehalten, in diesem Rollout nicht zusätzlich gebaut. Nach bestätigten Checks keine weiteren Prüfrunden ohne konkreten Anlass.

## Vorheriger Stand: Anlagenübersicht 0.6.0 separat als Vorschau

Benutzer beauftragt die eigene Funktionsübersicht nach gemeinsamem Plan und bestätigt zusätzliche gezielte Messwertabfragen. Das falsche p4d-Schema nicht verwenden; Gruppen und Beziehungen aus erreichbaren Geräte-Menüpfaden, keine erfundenen Rohrverbindungen. Implementierung 0.6.0: `/anlage`, Navigation, `GET /api/v1/plant`, ausdrückliches `POST /api/v1/plant/activate`, lesender Job `refresh_component`. Aktivierung nutzt vorhandenen Sensor-Konfigurationspfad, verändert keine Recordflags; niemals durch GET. Parametercache zehn Minuten, SQLite-Metadaten; Einzelabfragen über denselben Worker, maximal vier parallele Gruppen. Nicht zugeordnete Pumpen, veraltete Werte und Mehrdeutigkeiten ausdrücklich darstellen. Allgemeine Display-Bedienrechte sind keine zusätzlichen Kessel. Normale Sensor-/Menü-/API-Wege erhalten.

**Nicht produktiv ausgerollt.** Vorhandener 0.5.7-Dienst, PID und alle Sensor-/Recordflags vor/nachher lesend identisch; Erfassung/History gesund. Keine Änderung am Produktionshost, keine Heizungs-Schreibtests und kein serieller Zugriff durch Agenten. Zusätzliche 38 Abfragewerte aus dem Katalog erst bei beauftragtem produktiven Rollout ausdrücklich aktivieren. Neuer Code/Installer 0.6.0, laufende Installation nicht ungefragt ersetzen.

Getrennte Vorschau auf dem Arbeitsrechner Port 8001, direkter Pfad `/anlage`. Hintergrundprozess und private Quelle unter `.local/plant-preview.pid`, `.local/plant-readonly-source.json`, `.local/plant-live-preview.log`. Vorschau liest nur GET /sensors der bestehenden API, alle Mutationen/Heizungsjobs gesperrt; kein serieller Adapter, keine Verbindung zur MariaDB. Sollwerte sind dort mangels neuem produktivem Cache noch unbekannt. Nur diesen eindeutig identifizierten Vorschauprozess bei Bedarf beenden/aktualisieren; niemals Produktionsdienst dafür stoppen. Öffentliche Anleitung docs/plant-overview.md; keine privaten IPs/Rohberichte committen.

255 Tests mit separater wegwerfbarer MariaDB erfolgreich, vier Chromium-Breiten sowie echte API-Vorschau mobil/Desktop geprüft; native Installation isoliert und PTY-Wiederanlauf erfolgreich. Produktive Aktivierung bleibt gesonderter Auftrag. Danksagung im README weiter wortgleich erhalten.

## Verbindlicher Dauerbetrieb seit 18.10.2026

Benutzer: „p4d crons müssen weg!“ und „unsere API ist nun reif für den Dauerbetrieb und darf auch nicht mehr beendet werden“. Keine geplanten Bridge-Stopps, Deployments oder Rückkehr zu p4d ohne neuen konkreten Auftrag. Automatische Wiederherstellung bleibt notwendig: Bridge statt p4d wiederherstellen. Keine hundertprozentige Verfügbarkeit aus der Freigabe ableiten.

Erledigt: einzigen aktiven p4d-Cronjob aus Root-Crontab nach privater Vollsicherung entfernt, andere Jobs bytegleich erhalten; Benutzer-/System-Cronquellen geprüft. Anschließend bislang inaktive Bridge über regulären Helfer wieder aktiviert. Bridge 0.5.7 active/enabled, p4d inactive/disabled, Health-Timer aktiv, Starttimer inaktiv. Installerzustand `automatic_p4d_fallback=false`, `p4d_fallback=true` erhält ausschließlich manuelle Rückfallmöglichkeit. Wirksames Drop-in: Restart=always, StartLimitIntervalSec=0; Health-Guard startet bei anhaltender Störung Bridge neu, Rescue beendet Bridge nicht und aktiviert kein p4d. Verwaltungshelfer/Health-Skript aktualisiert, API-Prozess dabei unverändert. Installer erhält diese Politik bei Neuinstallation. Kein Hostneustart, kein künstlicher Ausfalltest und keine zusätzliche Heizungsänderung durch Agenten.

Reale Kontrolle: 94/94 ausgewählte Werte frisch, Collector fehlerfrei mit 16 Messpunkten je Zyklus, frischer MariaDB-Status, Fehlerabgleich verfügbar, 83 Historieneinträge und 0 bestätigt aktive Fehler vor Benutzer-Ascheboxtest. Detaillierte Belege/Backuporte in docs/project-context.md. Vorheriger Cron-Ausfall ist historisch; nicht erneut als aktuellen Dienstzustand annehmen.

Benutzer führt danach eigenen Aschebox-Fehlertest durch. Tatsächlich erkannt und in DB übernommen: neuer Fehler 179, gekommen/aktiv, 84 statt 83 Historieneinträge; API/Erfassung unverändert gesund. Danach Benutzer bestätigt gekommen/gegangen; unabhängig lesend in API und MariaDB bestätigt: derselbe Eintrag jetzt quittiert/inaktiv, End- und Quittierzeit gespeichert, genau ein Datensatz für dieses Vorkommnis. Bridge-PID unverändert, acht fehlerfreie Zyklen, Fehlerabgleich erfolgreich. Dieser reale Fehlerlebenszyklus ist damit geprüft; keine weiteren künstlichen Fehler auslösen. Privater Nachweis `.local/ashbox-closed-verified-20261018.json`.

## Neuer Auftrag: alte unvollständige Fehler und neue Zustandsmeldungen

Benutzer meldet scheinbar aktive alte Fehler und fordert ausdrücklich, vorhandene Fehler bei neuen Zuständen zu aktualisieren. Lesend: drei alte 2025-Vorkommnisse mit Zustand „gekommen“ ohne End-/Quittierzeit, nicht im aktuellen Steuerungsspeicher; aktuelle Übernahme passt. Danach ausdrücklich „die alten unvollständigen löschen wir jetzt einmalig“: genau diese drei Datensätze nach privater Sicherung gelöscht, 83 statt 86 DB-Zeilen. Einmalige Freigabe, keine allgemeine Bereinigungsroutine; nicht wiederholen. Backup/Protokoll privat unter Installerzustand, Details in Kontext. Zustands-Upsert erweitern: bestätigte Meldungen aktualisieren denselben Schlüssel Nummer/Auftretenszeit einschließlich bislang fehlender Zeitpunkte auch bei bereits gleichem Status, keine Duplikate und keine erfundenen Endzeiten. API/UI unterscheiden gespeicherten historischen Zustand von aktuell belegter Aktivität (`active` true/false/null). Keine Heizungs-Schreibtests/Hostneustarts.

Als 0.5.7 produktiv aktiviert: bestätigte Zustandswechsel und nachgelieferte Zeitpunkte aktualisieren dasselbe Vorkommnis, stabile IDs/Mailzähler; 241 Tests mit isolierter MariaDB erfolgreich. `active` true/false/null trennt aktuelle Belege von historischem Rohzustand. Einmalige Löschung bestätigt: 83 Einträge bleiben, 0 bestätigt aktiv, gelöschte IDs nach neuem Abgleich weiterhin fort. Sicherung unter `PRIVATE_SICHERUNG` (Platzhalter; tatsächlicher Ort nur lokal dokumentiert). Keine neue Bereinigung ausführen. Konfiguration/Schreibnachweis erhalten, Erfassung und Fehler-DB-Abgleich fehlerfrei, keine Heizungsparameter-/Flagänderung und kein Hostneustart. Aktueller Detailstand in docs/project-context.md; wieder unverändert beobachten.

## Aktueller Nachtrag: vollständige Fehlerhistorie

Benutzer meldet, dass `/errors` weniger Einträge als MariaDB liefert. Lesend bestätigt: API 16 Steuerungsvorkommnisse, DB 86 historische Zeilen. Original `performErrors` verwendet `selectAllErrors` aus MariaDB, sortiert time1 absteigend. Route und GUI auf diese vollständige gespeicherte Historie ergänzen; reine Steuerungsansicht separat anwählbar, Quelle/Gesamtzahl/Seitennavigation deutlich. DB-Ausfall darf keine scheinbar vollständige kurze Liste liefern: Fallback ausdrücklich kennzeichnen, explizite History-Abfrage dann 503. Keine historischen Zeilen oder Sensorflags ändern; keine Heizungs-Schreibtests/Hostneustarts. Erweitert die frühere Beobachtungsabsprache für diese Korrektur.

Umgesetzt und produktiv als 0.5.6: Default `/errors` und GUI liefern jetzt alle 86 DB-Vorkommnisse, `source=controller` weiterhin 16 aktuelle Steuerungsvorkommnisse. SQL/API-Felder und Seitennavigation real geprüft, alte IDs/Mailzähler erhalten. 233 Tests einschließlich separater MariaDB, Browser-/PTY-/Installationsprüfungen erfolgreich. Collector schreibt weiter 16 Messpunkte; keine Flag-/Heizungsparameteränderung und kein Hostneustart. Aktueller Vertrag und Detailstand am Anfang von docs/project-context.md und in OpenAPI. Wieder unverändert beobachten.

## Korrektur: automatische UD-Aufzeichnung wie Original-p4d

Benutzer widerspricht der falschen Aussage, Statusaufzeichnung erfordere beim Original das sichtbare Recordflag. Vollständiger Abgleich bestätigt ihn: `P4d::applyConfigurationSpecials` setzt intern `sensors["UD"][udState/udMode/udTime].record = true`, nach dem Laden der gespeicherten Flags. Sowohl Referenz-Pin als auch installierter Originalquellstand 1bc324d enthalten dies. Die gegenteilige frühere Erklärung war falsch; nicht erneut als Fakt übernehmen. Aktuellen Nachbau um genau diese Regel ergänzen: UD 1–3 im Standalonebetrieb unabhängig von Flags abfragen und aufzeichnen, gespeicherte Auswahl unverändert erhalten, effektive Aufzeichnung in API/UI ausdrücklich zeigen. Änderung ist DB-Aufzeichnung, kein Heizungs-Schreibtest. Kein Hostneustart.

Umgesetzt und produktiv als 0.5.5 geprüft: UD 1–3 werden jetzt auch bei leeren/ausgeschalteten gespeicherten Flags aufgezeichnet. Neue MariaDB-Messpunkte für UD 2/3 bei unverändert leerem Flag real bestätigt, 16 Messpunkte je Zyklus. Gleichzeitig gemeldete unlesbare Fehlerliste durch eigenes responsives Layout repariert und real mobil/Desktop geprüft. 228 Tests einschließlich isolierter MariaDB, Browser-/PTY-/Installationsprüfung erfolgreich. Keine Liveflags oder Heizungsparameter geändert; kein Hostneustart. Aktueller Detailstand am Anfang von docs/project-context.md. Nun wieder unverändert beobachten.

## Neuer Auftrag: Fehlerspeicher und bestehender DB-Client

Benutzer meldet einen weiteren Client, der Heizungsstatus regelmäßig aus MariaDB liest; erst aktiviertes Status-Recordflag lieferte wieder aktuelle Messpunkte. Fehlerspeicher ausdrücklich essentiell. Regelmäßiges Lesen und p4d-kompatible Synchronisation von `errors` sowie API-/Webanzeige ergänzen, separat testen und kontrolliert bei erhaltener Erfassung ausrollen. Dieser Auftrag ersetzt die folgende Beobachtungsabsprache für dieses Arbeitspaket. Gesetzte Sensorflags erhalten. Korrektur nach erneutem Originalabgleich: `P4d::applyConfigurationSpecials` erzwingt intern Aufzeichnung von UD 1–3 unabhängig vom gespeicherten Recordflag; diese Originalausnahme ab 0.5.5 übernehmen, keine DB-Flags dafür umschreiben. Client-SQL ist inzwischen bekannt: samples, UD/1, ORDER BY updsp DESC LIMIT 1. Aktuell stimmt der Text mit der Live-API überein; empfohlen sind aggregate=S und ORDER BY time DESC, damit alte neu verdichtete Daten nicht als aktueller Zustand erscheinen. Keine Heizungs-Schreibtests und kein Hostneustart.

Umgesetzt und auf dem Host aktiviert als 0.5.4: Heizungsfehlerspeicher regelmäßig lesen, SQLite-Cache, API/Webansicht und transaktionaler MariaDB-Abgleich. 226 Tests mit isolierter MariaDB sowie Browser-/PTY-/Installationsprüfung erfolgreich. Reale Fehlerliste und Abgleich bestätigt, bestehende 86 Fehlerzeilen erhalten, Status-Recordflag weiterhin A. Konfiguration inklusive Schreibnachweis unverändert, keine Heizungsparameter-/Flagänderungen. Genaue Ergebnisse in docs/project-context.md. Nun wieder unverändert beobachten; aktuelle Sicherung im Remote prüfen.

## Aktuelle Absprache: unverändert beobachten

Benutzer lässt den Stand zunächst einige Tage laufen und prüft selbst. Ohne neuen Auftrag keine weiteren Deployments, Neustarts oder Heizungs-Schreibtests. Bestehende automatische Erfassung, Aufzeichnung und Gesundheitsüberwachung unverändert laufen lassen. Aktuellen Quell-/Dokumentationsstand auf GitHub sichern; bei Rückmeldung mit dem dokumentierten Stand fortsetzen.

## Aktuelle Heizungs-Schreibfreigabe (17.10.2026)

Der Benutzer hat den konkreten LED-Helligkeitstest mit Änderung um einen Prozentpunkt und unmittelbarer Rückstellung bestätigt. Test am echten Gerät erfolgreich: frische Ausgangsmetadaten, Änderung, beide Bestätigungen, frisches Nachlesen, Rückstellung und erneutes Nachlesen. Danach wie vereinbart `write_parameter` für das normale p4d-Parametermenü aktiviert. Aktuelle Produktionskonfiguration verwendet den geschützten Geräte-/Firmware-Nachweis unter `/etc/froeling-bridge/write-validation.json`. Keine eigene Parameter-Freigabeliste; dieselben sechs Menütypen wie p4d. Zeitprogramm-Schreiben bleibt gesperrt (`write_time_range` nicht validiert). Keine weiteren beliebigen Teständerungen autorisiert. Frühere pauschale Heizungs-Schreibsperren weiter unten sind historische Freigabestände.

Benutzer fragt nach Bootverhalten und sagt ausdrücklich „nicht machen“: keinen Hostneustart ausführen. Lesend bestätigt: Bridge enabled/active, p4d disabled/inactive, Gesundheits-Timer enabled/active; wirksame Host-Drop-in setzt `Restart=no` und `OnFailure` auf Rückkehr zu p4d.

## Aktueller administrativer Zugriff (17.10.2026)

Administrative Zugriffsdaten und Berechtigungen werden ausschließlich im privaten Betreiberkontext festgehalten. Bestehende Autorisierung beachten, verfügbare Rechte bei Bedarf lesend prüfen und den laufenden Betrieb schützen. Daraus folgt keine Freigabe für Heizungsänderungen.

## Neuer Auftrag: eigenständiger Ersatz ab 0.5.0

Der Benutzer hat den Plan für unabhängigen Erststart, Discovery, lokale SQLite-Arbeitsdaten, optionale automatische MariaDB-Einrichtung, Sensor-Auswahl und Verdichtung ausdrücklich zur Implementierung freigegeben. Live-Werte und Menü haben Vorrang vor Historie. Dies erweitert die früheren Nur-Lesen-/Nur-samples-Grenzen im beschriebenen Umfang:

- Eigenständige Installation und Discovery ohne p4d-Bestand, bestehende DB kompatibel weiterführen, neue/leere DB nach expliziter Konfiguration automatisch erstellen. Kein ungefragtes Migrieren bestehender DBs.
- Sensor-Abfrage-/Recordflags dürfen über die neue Oberfläche/API geändert und mit valuefacts synchronisiert werden. Historienverdichtung nach vorhandener Konfiguration ist beauftragt; Einfügen/Löschen transaktional und zunächst separat testen. Agent darf keine Live-Flags nur zum Test umschalten.
- MariaDB-Fehler dürfen Live-Abfragen und Menü nicht beenden. Lokale SQLite-Datei ist dauerhaft, keine Historienpflicht. Wiederherstellung ohne Katalog muss durch Discovery funktionieren.
- Heizungsparameter bleiben bis zum separat vereinbarten Test mit ausgewähltem Parameter und Zielwert gesperrt. Implementierung der Schreibfreigabe ist autorisiert; tatsächliche Heizungs-Schreibtests sind dadurch nicht pauschal erlaubt.
- Hardware-Abnahme verlangt vollständige Discovery, 24 Stunden echten Lesebetrieb und kontrollierten Hostneustart. Nicht aus Simulator-/Pseudo-TTY-Erfolg ableiten. Installation/Abnahme sind von implementiertem Code klar zu unterscheiden.
- Neue Anleitung docs/standalone.md ist maßgeblich. Historische Angaben zu reiner DB-Aufzeichnung/15-Minuten-Grenzen weiter unten sind nur Kontext.

## Aktuelle Freigabe: produktive Aufzeichnung und Dauerbetrieb

Der Benutzer hat nach dem erfolgreichen Lesefenster ausdrücklich bestätigt: „ja wir schreiben nun auch un lassen es laufen“. Dies erweitert die bisherigen Grenzen ausschließlich wie folgt:

- Dauerbetrieb mit exklusivem Heizungs-Lesezugriff und Messwertaufzeichnung in der bestehenden p4d-Datenbank ist autorisiert. Nur `samples` und `peaks` über den geprüften kompatiblen Recorder fortführen; Metadaten und Historie ansonsten lesend. Keine Schemaänderung, Initialisierung, Löschung oder neue Aggregation.
- Umschaltung einschließlich p4d-Stop/Autostartwechsel, neuem Bridge-Autostart und Rückfall zu p4d ist autorisiert. Originalinstallation erhalten. Eigener Produktionsdienst ohne 15-Minuten-Limit; siehe docs/production.md.
- Heizungsparameter schreiben bleibt ausdrücklich gesperrt. Testbetrieb/Bestandsansicht behalten ihre bisherigen Schreibgrenzen. Historische Nur-Lesen-Angaben weiter unten beschreiben die frühere Freigabe und werden durch diesen Abschnitt nur im genannten Umfang ersetzt.
- Administrative Zugriffslage privat dokumentieren; erforderliche Rechte vor freigegebenen Aktionen prüfen. Keine zusätzlichen Heizungs-Schreibrechte daraus ableiten.

## Live-Datenbank: ausdrücklich nur lesen

Der Benutzer hat am 16.10.2026 Zugang zur laufenden Original-p4d-Datenbank über die lokale Datei `live-db.con` gegeben, ausschließlich zum Umsehen.

- Keine Änderungen an Daten, Schema, Benutzern, Berechtigungen oder Servereinstellungen. Keine Migrationen, Schreibtests, Initialisierung, Bereinigung oder Aggregation gegen die Live-DB.
- Keinen p4d-Daemon gegen die Live-DB starten: schon Startup/Default-Lesen kann Schema und Konfiguration ändern.
- Ausschließlich eng begrenzte lesende SQL-Abfragen (`SELECT`, `SHOW`); Tabellen-Metadaten bevorzugen. Kein `SELECT FOR UPDATE`, keine Sperr-/Adminoperationen und keine teuren Volltabellenanalysen der Historie.
- Wo vom Treiber unterstützt, eine read-only Session/Transaktion als zusätzliche Schranke setzen; das ist kein Ersatz für die Beschränkung der SQL-Abfragen.
- Zugangsdaten nicht ausgeben, committen oder in Shellargumente schreiben. `live-db.con` bleibt ignoriert. Keine vollständigen Config-/User-Dumps, Token, privaten Netzadressen oder privaten Betriebsdaten ins Repository aufnehmen.
- Repository-Dokumentation darf bereinigte Schema-/Kompatibilitätsbefunde enthalten. Raw-Ergebnisse und Mitschnitte bleiben lokal und ignoriert.
- Schreibversuche gehören später ausschließlich auf eine separate DB-Kopie; direkte Heizungs-Schreibtests müssen gesondert mit dem Benutzer vereinbart werden.

## Live-Server per SSH: Bestandsaufnahme und freigegebener Lesetest

Der Benutzer stellt `live-server-ssh.con` für den zuvor angebotenen lesenden SSH-Zugriff bereit. Auch diese Datei bleibt ignoriert und wird nicht ausgegeben. Private SSH-Ergebnisse und Hostschlüssel liegen unter `.local/`, nicht im Repository. Der Benutzer hat inzwischen den erweiterten Plan einschließlich Webmenü, vorbereiteter einmaliger Einrichtung und 15-minütigem lesendem Hardwaretest ausdrücklich zur Umsetzung beauftragt; das aktualisiert die frühere reine SSH-Bestandsaufnahme-Freigabe wie folgt.

- Für freigegebene Hostarbeiten vorher Umfang und erforderliche Rechte prüfen. Persönliche Zugriffs- und Berechtigungsdetails stehen ausschließlich im privaten Betreiberkontext; sie gehören nicht in die öffentliche Dokumentation.
- Keinen weiteren p4d-Prozess starten; auch keine vermeintlichen Versions-/Hilfeflags ausführen, solange deren Nebenwirkungsfreiheit nicht belegt ist.
- Der Adapter liegt unter `/dev/ttyUSB0`. Nur innerhalb des vorbereiteten hardware-read-Testfensters nach aktiviertem Rückkehrtimer, beendetem p4d und geprüfter Portfreigabe öffnen. Kein Parallelzugriff. Keine Heizungs-Schreibbefehle; Originaldatenbank bleibt strikt lesend, Aufzeichnung nur in separater Test-MariaDB. Außerhalb dieses Ablaufs Port nicht öffnen oder konfigurieren.
- Vorhandener Quellcommit, lokale Änderungen und tatsächlich laufende Binärdatei sind getrennte Belege. Eine Gleichheit nicht allein aus einem vorhandenen Checkout folgern.
- Bestehende Logs dürfen begrenzt gelesen werden; keine Logstufe ändern oder neuen Heizungsverkehr für Mitschnitte auslösen.
- Nur bereinigte fachliche Befunde dokumentieren; keine privaten Hostnamen, IPs, Benutzerpfade, Zugangsdaten oder ungefilterten Logs committen.

## Repository und Referenz

- Eigenes Remote: `git@github.com:vgarcia007/froeling-bridge.git`, öffentlich; keine persönlichen Betriebsdaten veröffentlichen.
- Originalcode als Submodul: `reference/linux-p4d`, Herkunft `https://github.com/vgarcia007/linux-p4d.git`.
- Untersuchte Referenz: `4d1176c4a9081893e4c2cc27a535bb2bc4737d0a`. Referenzcode unverändert lassen und nicht still aktualisieren.
- Python-Kern: `src/froeling_bridge`, Anleitung `docs/python-core.md`. Python >=3.9, Kern ohne externe Laufzeitabhängigkeiten. Optional `.[service]` für API/DB; Anleitung `docs/service.md`. Tests: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v`; MariaDB-Integration nur mit explizitem `FROELING_TEST_DB_CONFIG` für separate lokale Test-DB.
- Zusätzliche Offline-Prüfung: `python3 docs/tools/verify_protocol_examples.py`. Sie prüft Original-Bytecodierung, nicht die reale Schreibsemantik.
- Reale Schreibmitschnitte dienen zusätzlicher Hardwarevalidierung, blockieren aber die quellenbasierte Implementierung nicht. Default-Antwortcodes des Simulators sind unbestätigte Annahmen. Keinen TTY-Adapter oder Live-Betrieb daraus als bereits geprüft ableiten.

## Kontinuität und Sicherung

- Nach abgeschlossenen Arbeitspaketen `docs/project-context.md` aktualisieren: belegte Ergebnisse, aktuelle Phase, Prüfungen, offene Punkte, nächster Schritt. Dauerhafte Entscheidungen in `docs/decisions.md` ergänzen.
- Bestehende Fachnotizen aktualisieren statt widersprüchliche Parallelzusammenfassungen anzulegen. Keine privaten Gedankengänge, Zugangsdaten oder ungefilterten Tool-Ausgaben als Kontext speichern.
- Der Benutzer möchte bereinigte Arbeitsstände im öffentlichen Repository sichern. Zusammenhängende, überprüfte Änderungen committen und auf den eingerichteten Branch pushen; keine Force-Pushes oder destruktiven Git-Operationen. Benutzeränderungen nur einbeziehen, wenn sie zum autorisierten Arbeitspaket gehören.
- Vor Commit/Push staged Diff, ignorierte Verbindungsdatei und Submodul-Pin prüfen. Falls Push scheitert, lokalen Commit erhalten und den fehlenden Remote-Stand klar berichten.
- Im Abschluss nennen, was tatsächlich gespeichert/gepusht wurde und was noch unbestätigt ist. Ein Push ist keine Zusage eines vollständigen Backups: lokale Secrets und ignorierte Artefakte sind davon ausgeschlossen.
