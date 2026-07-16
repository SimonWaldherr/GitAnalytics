# Metrikdefinitionen

## Interpretation und Grenzen

Die folgenden Kennzahlen beschreiben Daten aus dem konfigurierten Git-Ausschnitt. Sie sind Diagnosehilfen, keine objektiven Bewertungen von Personen, Teams oder Projekten. Eine Kennzahl beantwortet nur die Frage, die sie tatsächlich misst: Commit-Anzahl misst Commits, Churn misst geänderte Zeilen und Kommentar-Dichte misst eine sprachabhängige Zeilenheuristik. Keine dieser Größen misst automatisch Qualität, Wirkung, Kompetenz, Sicherheit, Wartbarkeit oder Produktivität.

Kennzahlen werden besonders unzuverlässig, wenn sie zur Ziel- oder Ranglistengröße werden. Dann kann es rational erscheinen, viele kleine Commits zu erzeugen, Code nicht zu löschen oder Änderungen künstlich aufzuteilen. Das verbessert die Zahl, nicht zwingend das Ergebnis. GitAnalytics soll daher Auffälligkeiten sichtbar machen und fachliche Gespräche unterstützen – nicht Leistungsbeurteilungen, Recruiting-, Vergütungs- oder Personalentscheidungen automatisieren.

Für eine belastbare Einordnung gehören mindestens fachlicher Kontext, Tests und Qualitätsprüfung, Nutzer- oder Betriebswirkung, Kosten, Datenabdeckung und die dokumentierten Einschränkungen der jeweiligen Kennzahl dazu. Eine hohe, niedrige oder veränderte Kennzahl ist ein Anlass zur Untersuchung, kein Urteil.

## Effektiver Commit-Datensatz

Alle Kennzahlen basieren auf `effective_commits`. Ein Commit ist enthalten, wenn sein Repository aktiv und sein Snapshot `ready` oder `stale` ist. Optional werden Bots ausgeschlossen und gleiche Commit-SHAs repositoryübergreifend dedupliziert.

Der ausgewählte Revisionsumfang kann sein:

- `current`: `HEAD`
- `local`: lokale Branches, Tags und `HEAD`
- `all`: alle lokal vorhandenen Refs
- explizite `refs`: vom Benutzer angegebene Revisionen

`git log` zeigt einen Commit bei mehreren erreichbaren Refs nur einmal pro Repository.

## Aktivitätszeit

`activity_timestamp` bestimmt, ob Autor- oder Committer-Zeit verwendet wird. `timezone=commit` behält den im Commit gespeicherten Offset. Eine IANA-Zeitzone oder UTC transformiert alle Aktivitätszeiten vor der Aggregation.

Wochentage verwenden Montag = 0 bis Sonntag = 6.

## Aktiver Tag, Serie und Lücke

Ein aktiver Tag hat mindestens einen effektiven Commit. Eine Serie ist eine maximale Folge kalendarisch aufeinanderfolgender aktiver Tage. Die längste Lücke zählt volle Tage zwischen zwei aktiven Tagen, ohne Randzeiträume vor dem ersten oder nach dem letzten Commit.

## Repository-Status

- `empty`: kein effektiver Commit
- `active`: letzter Commit jünger als `quiet_after_days`
- `quiet`: mindestens `quiet_after_days`, aber weniger als `dormant_after_days`
- `dormant`: mindestens `dormant_after_days`

Die Berechnung erfolgt relativ zum Tag der Berichtserzeugung in UTC.

## Churn

`churn = insertions + deletions` aus `git log --numstat`. Binärdateien liefern keine Zeilenzahlen. Merge-Commits können Numstat enthalten und werden in Gesamtsummen einbezogen, sofern Merges nicht ausgeschlossen sind. Commit-Größen werden nur für Nicht-Merge-Commits klassifiziert.

## Autoren

Die kanonische Identität entsteht in dieser Reihenfolge:

1. rohe Git-Identität,
2. optional `.mailmap`,
3. erste passende projektübergreifende Aliasregel,
4. stabiler Hash des kanonischen E-Mail-Werts oder normalisierten Namens.

Der Hash ist keine kryptografische Anonymisierung des Rohdatensatzes; rohe Identitäten bleiben in SQLite gespeichert.

## Konzentration

- Top-Autor-Anteil: größter Commit-Anteil eines Autors.
- BF50/BF80: kleinste Zahl der nach Commit-Anteil sortierten Autoren, deren kumulierter Anteil mindestens 50/80 Prozent beträgt.
- Gini: Ungleichverteilung der Commit-Zahlen von 0 bis nahe 1.
- HHI: Summe der quadrierten Commit-Anteile.

Diese Werte messen Commit-Konzentration, nicht Wissen, Qualität, Verantwortlichkeit oder Ausfallrisiko.

Ein kleiner BF50/BF80 kann auf konzentriertes Wissen hinweisen, ist aber kein Nachweis für einen tatsächlichen Bus-Faktor. Er berücksichtigt weder Dokumentation, Vertretung, Code-Ownership, Betriebswissen noch Personen außerhalb der Git-Historie.

## Commit-Typen

Betreffzeilen werden gegen ein Conventional-Commit-ähnliches Muster geprüft. Zusätzlich werden Merge, Revert und Initial Commit erkannt. `has_issue_reference` erkennt `#123` und Schlüssel wie `ABC-123`. Das ist eine Heuristik; projektspezifische Formate können fehlen oder falsch klassifiziert werden.

## Hotspots

Ein Datei-Touch ist eine Dateiänderungszeile eines effektiven Commits. Hotspots werden primär nach Touch-Anzahl und sekundär nach Churn sortiert. Umbenannte Pfade werden standardmäßig unter dem neuen Pfad gezählt und speichern optional den alten Pfad.

## Sprachen

Die Klassifikation ist pfadbasiert. `tree_languages` beschreibt den aktuellen `HEAD` und wird nach Git-Blob-Bytes gewichtet. `churn_languages` beschreibt historische Datei-Touches und Churn. Vendoring, Generierung oder eingebettete Sprachen werden nicht semantisch erkannt.

## Releases

GitAnalytics bezeichnet alle Git-Tags als Releases im Datenmodell. Das Creator-Datum ist bei annotierten Tags normalerweise das Tagger-Datum, bei Lightweight Tags typischerweise das Commit-Datum. Ein Tag ist nicht zwingend eine veröffentlichte Produktversion.

## Kommentar-Dichte

GitAnalytics analysiert Text-Blobs im aktuellen `HEAD` je Repository und Sprache. Die Dichte ist `Kommentarzeilen / (Kommentarzeilen + Codezeilen)`; Leerzeilen sind ausgeschlossen. Erkannte Kommentararten sind Zeilenkommentare, Blockkommentare und Python-Dokumentationsstrings. Die Erkennung ist bewusst heuristisch und keine vollständige Sprachsyntax-Analyse. Inline-Kommentare werden als Codezeilen gezählt, große Dateien (über 2 MB) und Binärdateien werden übersprungen.

## Optionale Netzwerkanalyse

Die Autoren-/Repository-Distanz ist keine Standardkennzahl. Sie wird nur berechnet und im Bericht angezeigt, wenn `network.enabled` explizit `true` ist. Dann ist sie ein kürzester Pfad im bipartiten Autoren-/Repository-Netzwerk. Eine Verbindung setzt im gegenwärtigen Modell die konfigurierte Mindestzahl von Commits pro Autor/Repository, zeitlich überlappende oder hinreichend nahe Beitragszeiträume und standardmäßig die Erreichbarkeit der Commits über eine Remote- oder verwaltete Vertrauensreferenz voraus.

Sie ist keine Kennzahl für Bekanntschaft, Qualität, Einfluss oder persönliche Zusammenarbeit. Insbesondere werden Reviews, Pull Requests, Co-Authorship und Maintainer-Beziehungen derzeit nicht als eigene, stärker gewichtete Kanten berechnet. Details zum Modell, seinen Messfehlern und den Anforderungen an eine belastbarere Kollaborationsmetrik stehen in [COLLABORATION.md](COLLABORATION.md).

## Öffentliche Profilpakete

Ein Profilpaket ist keine Aggregation des gesamten lokalen Berichts. Es wird direkt aus Repositories mit der expliziten Klasse `public` erzeugt. `private` und `exclude` beeinflussen weder dessen Zähler noch Sprachübersicht. Standardmäßig sind exakte Kennzahlen und Aktivitätsdaten nicht enthalten. Siehe [PRIVACY.md](PRIVACY.md).
