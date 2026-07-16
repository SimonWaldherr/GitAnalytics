# Optionale Netzwerkanalyse: Modell, Grenzen und Zielbild

Die Autoren-/Repository-Distanz ist in GitAnalytics standardmäßig deaktiviert. Sie ist eine frei konfigurierbare Heuristik für Experimente mit Repository-Nähe, aber keine normale KPI. Sie misst weder persönliche Bekanntschaft, Kompetenz, Einfluss noch die Qualität einer Zusammenarbeit.

Die jeweiligen Entscheidungen hinter Opt-in, Bot-Ausschluss, Remote-Evidenz, Identitätsauflösung und Quellenbegrenzung sind in [DECISIONS.md](DECISIONS.md) mit Begründung und Umsetzungsstatus festgehalten.

Einfache Distanzzahlen verbinden Entwickler bereits dann, wenn beide irgendwann in demselben Repository auftauchen, und berechnen daraus einen kürzesten Pfad zu einer Referenzperson. Das ist technisch leicht, aber inhaltlich schwach: Ko-Präsenz wird wie Zusammenarbeit behandelt, während Bots, große Projekte, Forks und importierte Historien künstliche Abkürzungen erzeugen können. Der interessante Anwendungsfall ist daher nicht eine möglichst kleine Zahl, sondern ein erklärbares Modell digitaler Kollaboration.

## Standardmodell

Autoren werden nur dann über ein gemeinsames Repository verbunden, wenn beide die konfigurierte Mindestanzahl von Commits beitragen und ihre Beitragszeiträume höchstens `max_contribution_gap_days` auseinanderliegen. Service-Accounts werden standardmäßig ausgeschlossen. Der Pfad weist jedes vermittelnde Repository aus.

```json
{
  "network": {
    "enabled": true,
    "reference_names": ["Referenzperson"],
    "exclude_service_accounts": true,
    "ignored_account_patterns": ["(?i)dependabot", "(?i)renovate", "(?i)codex", "(?i)claude"],
    "min_commits_per_author_repository": 2,
    "max_contribution_gap_days": 365,
    "require_remote_reference": true,
    "max_display_nodes": 500
  }
}
```

Dieses Basismodell verwendet ausschließlich Git-Commitdaten. Es verarbeitet derzeit weder Pull Requests noch Reviews oder Forge-spezifische Ereignisse als eigene Kanten. Die Kennzeichnung einer Kante als Zusammenarbeit wäre deshalb irreführend; im Bericht heißt sie bewusst Repository-Verbindung.

## Zielbild für belastbarere Kollaboration

Ein weiterentwickeltes Modell sollte nicht bloß gemeinsame Repository-Zugehörigkeit zählen, sondern mehrere nachvollziehbare Beziehungssignale unterscheiden und ihre Herkunft offenlegen:

- direkte Interaktion wie Review, Kommentar, Merge oder bestätigte Co-Authorship stärker als bloße Ko-Präsenz gewichten,
- Menschen, Bots, CI-, Merge- und Dependency-Accounts getrennt behandeln und Regeln dafür sichtbar konfigurierbar machen,
- Identitäten aus Namen, E-Mail-Adressen, `.mailmap`, Forge-Accounts und – soweit verfügbar – verifizierten Zuordnungen konsolidieren, ohne ungesicherte Gleichsetzungen als Fakt auszugeben,
- Zeit, Projektgröße, Beitragsumfang, Fork-Beziehungen und identische Commit-Historien in die Gewichtung einbeziehen,
- zu jeder Kante Ereignistyp, Quelle, Zeitraum, Vertrauensniveau und verwendete Modellversion ausgeben.

Damit wäre eine Distanz zu einer Referenzperson nur eine Ansicht auf ein allgemeineres Kollaborationsnetzwerk. Der kürzeste Pfad allein ist nicht zwingend der glaubwürdigste; ein nachvollziehbar gewichteter Pfad ist aussagekräftiger als eine unkommentierte Zahl.

## Wichtige Grenzen

- Git-Autor und Committer sind frei wählbare Metadaten; Signaturen erhöhen nur die Zuordnungskonfidenz.
- Die Analyse erscheint im HTML-Bericht nur bei `network.enabled: true`. Ohne dieses Opt-in bleiben Standardlauf und Bericht auf klassische Repository-Kennzahlen fokussiert.
- Standardmäßig zählen nur Commits, die über `refs/remotes/*` oder verwaltete `refs/gitanalytics/trusted/*` erreichbar sind. Das reduziert lokale oder nicht gemergte Commit-Kanten, ist aber kein Identitäts- oder Kollaborationsbeweis. Mit `require_remote_reference: false` kann diese Schutzregel bewusst ausgeschaltet werden.
- Forks, Mirrors, kopierte Historien und globale SHA-Duplikate können weiterhin künstliche Kanten erzeugen, besonders wenn dieselben Upstream-Commits in mehreren Quellen sichtbar sind.
- Gemeinsame Repository-Mitgliedschaft beweist keine direkte Zusammenarbeit, besonders bei großen oder langlebigen Projekten.
- Bots, CI-, Merge- und Dependency-Accounts können Superknoten bilden; Muster dafür sollten projektspezifisch gepflegt werden.
- Reviews, Pull Requests, Co-Authorship, Maintainer-Beziehungen, Mailinglisten, Gerrit und Patch-Serien werden aus reiner Git-Historie nicht vollständig erfasst. Das aktuelle Basismodell wertet sie nicht als eigene Kanten aus.
- Private, gelöschte oder nicht analysierte Repositories sowie andere VCS-Systeme fehlen. Die Reichweite ist daher immer unvollständig und forge-abhängig.
- Gewichtungen, Zeitfenster und Mindestbeiträge sind normative Entscheidungen und können gezielt manipuliert werden.

Jede Auswertung sollte Referenzperson, Pfad, Repository-Ereignisse, Zeitraum, Datenquellen, Konfiguration, Modellversion und Vertrauensniveau offenlegen. Eine niedrige Distanz misst weder Können noch Einfluss oder Qualität; sie beschreibt ausschließlich eine Position im ausgewählten und unvollständigen Netzwerkausschnitt. Solange das aktuelle Basismodell einzelne dieser Angaben noch nicht pro Kante ausgibt, ist dies als bekannte Grenze zu verstehen, nicht als stillschweigende Zusage.

## Quellen und Reproduzierbarkeit

Die Netzwerkanalyse crawlt keine Foren, Profile oder Fork-Netzwerke automatisch. Weitere Repositories werden nur über explizite URLs mit `gitanalytics fetch` eingebracht und können ausschließlich über die Quellen-Registry synchronisiert werden. Das begrenzt Zugriffsfläche, API-Abhängigkeit und unbeabsichtigte Erfassung, bedeutet aber auch, dass die Distanz immer nur den bewusst gewählten Ausschnitt beschreibt. Siehe [SOURCES.md](SOURCES.md).
