# Lizenzumfang und Herkunft

## Eigene Beiträge: MIT

Die [MIT-Lizenz](LICENSE) erteilt die Freigabe für die eigenen, eigenständig geschaffenen Beiträge der Fröling-Bridge-Mitwirkenden, einschließlich eigener Dokumentation und Oberflächengestaltung. Nutzung, Änderung, Weitergabe und Verkauf sind erlaubt; Copyright- und Lizenzhinweis müssen erhalten bleiben. Die Freigabe betrifft ausschließlich Rechte, über die diese Mitwirkenden verfügen können.

## linux-p4d und fremde Bestandteile

Fröling Bridge wurde anhand des veröffentlichten Quellcodes und des daraus dokumentierten Protokoll- und Datenbankverhaltens von **linux-p4d**, Jörg Wendel (horchi) und weiteren Mitwirkenden entwickelt. Die Danksagung im README und die Quellverweise bleiben erhalten.

- Das Referenz-Submodul `reference/linux-p4d` behält seine ursprünglichen Lizenz- und Copyright-Hinweise. Seine Hauptlizenz ist die GNU GPL Version 2; eine unveränderte Kopie steht unter [LICENSES/GPL-2.0.txt](LICENSES/GPL-2.0.txt). Einzelne dort enthaltene Fremdbibliotheken haben eigene Lizenzdateien.
- Das Prüfwerkzeug `docs/tools/verify_protocol_examples.py` extrahiert Originalfunktionen aus diesem Submodul für einen temporären C++-Vergleich. Die extrahierten Originalfunktionen und daraus gebildete GPL-Werke werden durch die MIT-Freigabe nicht umlizenziert.
- Übernommener oder urheberrechtlich abgeleiteter GPL-Code bleibt den GPL-Bedingungen unterworfen; eine Übersetzung in Python allein hebt diese Bedingungen nicht auf. Soweit ein weitergegebenes Gesamtwerk der GPL unterliegt, sind deren Anforderungen für dieses Gesamtwerk einzuhalten. Die MIT-Freigabe eigener Beiträge ist kein Verzicht fremder Rechte und keine pauschale Zusicherung, das gesamte Projekt ausschließlich unter MIT weitergeben zu dürfen.
- Installierte Abhängigkeiten behalten ihre eigenen Lizenzen. Diese werden durch die Projektlizenz nicht ersetzt.

Untersuchte Referenz: [vgarcia007/linux-p4d](https://github.com/vgarcia007/linux-p4d), Commit `4d1176c4a9081893e4c2cc27a535bb2bc4737d0a`. Das Originalprojekt befindet sich unter [horchi/linux-p4d](https://github.com/horchi/linux-p4d).
