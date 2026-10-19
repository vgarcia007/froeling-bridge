# Copyright, Lizenz und Herkunft

## Fröling Bridge: GPLv2

Copyright (c) 2026 Fröling Bridge contributors.

Fröling Bridge wird unter der **GNU General Public License Version 2**, ausschließlich dieser Version, veröffentlicht (`GPL-2.0-only`). Der vollständige Lizenztext steht in [LICENSE](LICENSE). Die Projektfreigabe umfasst eigene Beiträge einschließlich Dokumentation und Oberflächengestaltung.

Nutzung, Änderung, Weitergabe und Verkauf sind erlaubt. Bei Weitergabe müssen die GPL-Bedingungen eingehalten werden, einschließlich der Anforderungen zum zugehörigen Quellcode sowie zum Erhalt von Copyright- und Lizenzhinweisen. Es wird keine Gewährleistung übernommen; maßgeblich ist der vollständige Lizenztext.

## linux-p4d und fremde Bestandteile

Fröling Bridge wurde anhand des veröffentlichten Quellcodes und des daraus dokumentierten Protokoll- und Datenbankverhaltens von **linux-p4d**, Jörg Wendel (horchi) und weiteren Mitwirkenden entwickelt. Die Danksagung im README und die Quellverweise bleiben erhalten.

- Das Referenz-Submodul `reference/linux-p4d` behält seine ursprünglichen Lizenz- und Copyright-Hinweise. Seine Hauptlizenz ist die GNU GPL Version 2. Einzelne dort enthaltene Fremdbibliotheken haben eigene Lizenzdateien.
- Das Prüfwerkzeug `docs/tools/verify_protocol_examples.py` extrahiert Originalfunktionen aus diesem Submodul für einen temporären C++-Vergleich. Die extrahierten Originalfunktionen behalten die ursprünglichen Copyright- und GPL-Hinweise.
- Die Projektlizenz entfernt oder ersetzt keine fremden Copyright-Hinweise. Abweichend lizenzierte Drittbestandteile und installierte Abhängigkeiten behalten ihre eigenen Lizenzen.

Untersuchte Referenz: [vgarcia007/linux-p4d](https://github.com/vgarcia007/linux-p4d), Commit `4d1176c4a9081893e4c2cc27a535bb2bc4737d0a`. Das Originalprojekt befindet sich unter [horchi/linux-p4d](https://github.com/horchi/linux-p4d).

## Frühere Freigabe eigener Beiträge

Bereits früher erteilte MIT-Nutzungsrechte an eigenen Beiträgen bleiben für die damals freigegebenen Fassungen bestehen. Die Rechte am p4d-Code waren von dieser Freigabe nicht betroffen. Der aktuelle Projektstand wird unter GPLv2 veröffentlicht.
