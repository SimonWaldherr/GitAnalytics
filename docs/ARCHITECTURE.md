# Architektur

## Datenfluss

```text
Stammordner
   │
   ├─ Discovery ──> RepositoryLocation
   │
   ├─ Privacy-Klassifikation ──> exclude / private / public
   │                    │
   ├─ Git-Probe ──> RepositoryProbe + Fingerprint
   │                    │
   │                    ├─ Cache-Treffer ───────────────┐
   │                    │                               │
   │                    └─ git log / ls-tree / tags     │
   │                              │                     │
   └──────────────────────────────┴─> SQLite Snapshot <─┘
                                          │
                                          ├─ SQL Analytics
                                          ├─ Offline HTML
                                          ├─ JSON
                                          ├─ CSV / externe BI-Werkzeuge
                                          └─ optionales public-Profilpaket
```

## Discovery

Die Discovery arbeitet breitensuchend und kann mehrere Wurzeln verarbeiten. Sie erkennt:

- Arbeits-Repositories über `.git/`
- verlinkte Worktrees und Submodule über `.git`-Dateien
- Bare-Repositories über `HEAD`, `objects` und `refs` beziehungsweise `packed-refs`

Dateisystemzyklen werden über Geräte-/Inode-Paare beziehungsweise kanonische Pfade verhindert. Symlinks werden standardmäßig nicht verfolgt.

## Repository-Identität

Die kanonische Repository-ID ist der von Git gemeldete `--git-common-dir`. Dadurch werden mehrere Worktrees desselben Objektspeichers nicht als getrennte vollständige Historien gezählt. Der erste entdeckte Worktree repräsentiert das Repository.

## Fingerprint und Cache

Ein Cache-Treffer erfordert gleichzeitig:

1. gleiche kanonische Repository-ID,
2. gleichen Fingerprint der relevanten Refs,
3. gleiche Scan-Signatur.

Der Fingerprint umfasst je nach Scope die Objekt-IDs der betrachteten Refs, `HEAD`, `.mailmap` sowie shallow-Metadaten. Die Scan-Signatur umfasst die GitAnalytics-Version, History-Einstellungen und Identity-Regeln.

Berichtseinstellungen und Datenschutzoptionen sind absichtlich nicht Teil der Scan-Signatur. Sie können mit `gitanalytics report` aus demselben Snapshot geändert werden.

Repository-Klassen werden bei Cache-Treffern ohne Git-Prozess aktualisiert. `exclude` wird beim nächsten Lauf zusätzlich aus dem lokalen Snapshot gelöscht; `private` ist der Standard, `public` ist nur eine Profilfreigabe.

## Fehlerverhalten

Jedes Repository wird transaktional ersetzt. Ein Fehler während eines Neu-Scans löscht den vorherigen gültigen Snapshot nicht. Ist ein älterer Snapshot vorhanden, erhält das Repository den Status `stale`; andernfalls `error`.

Discovery-, Probe- und Scanfehler werden dem Lauf zugeordnet in `scan_errors` gespeichert. Ein Lauf kann `complete`, `partial`, `failed` oder `aborted` sein.

## Git-Prozessmodell

Jeder Git-Aufruf erhält eine Argumentliste ohne Shell-Interpolation. Lange `git log`-Ausgaben werden blockweise gelesen und über Record Separator (`0x1e`) segmentiert. Commit-Felder verwenden Unit Separator (`0x1f`), Numstat ist NUL-separiert. Damit bleiben Leerzeichen, Tabs und fast alle zulässigen Pfadzeichen verarbeitbar.

GitAnalytics setzt `GIT_NO_LAZY_FETCH=1`; bei Partial Clones werden keine Netzwerkzugriffe ausgelöst. Zeitlimits beenden hängende Git-Prozesse.

## SQLite

SQLite ist Cache, Audit-Trail und öffentliche Analyseoberfläche. Der Standard-Journalmodus ist `DELETE`, damit der Bericht nach einem abgeschlossenen Lauf aus einer einzelnen Datenbankdatei besteht. Fremdschlüssel sind aktiviert.

Die persistente Datenbank enthält rohe normalisierte Identitäten, kanonische Identitäten und optionale Commit-Betreffzeilen. Der Bericht wird aus temporären effektiven Views berechnet. Diese wenden Bot-Filter und optionale globale SHA-Deduplizierung an.

`tree_comment_stats` ergänzt den HEAD-Snapshot um Zeilen-, Block- und Dokumentationskommentare je Sprache. Der Scanner ruft `git cat-file --batch` nur für Text-Blobs bis 2 MB auf; dadurch bleibt die Analyse read-only, vermeidet pro Datei einen Git-Prozess und berührt den Arbeitsbaum nicht.

`repository_privacy` speichert die lokale Freigabeklasse. `commits.is_trusted` markiert die Erreichbarkeit über Remote-Tracking- oder verwaltete Quellenreferenzen und wird nur von der optionalen Netzwerkanalyse als zusätzliche Evidenzschwelle verwendet.

## HTML-Bericht

Der Bericht bettet den JSON-Snapshot escaped in ein `application/json`-Element ein. CSS und JavaScript sind inline. Es gibt keine externen Ressourcen. Tabellenfilterung, Sortierung, Charts, Heatmaps, Repository-/Sprachfilter und Theme-Umschaltung funktionieren clientseitig.

## Erweiterungspunkte

Neue Metriken sollten bevorzugt als SQL-Aggregation in `analytics.py` umgesetzt werden. Neue Git-Rohdaten erfordern eine Schema-Migration, ein Feld im Datenmodell und eine Änderung der Scan-Signatur oder Tool-Version. Neue allgemeine Exporte sollten aus dem privacy-bereinigten Report-Snapshot erzeugt werden; ein öffentlicher Export muss dagegen seine Quellen direkt auf `public` klassifizierte Repositories einschränken.

## Explizite Netzwerkquellen

`fetch` und `sync` liegen bewusst außerhalb des read-only Scanners. Sie akzeptieren nur einen expliziten, separaten Zielordner, erzeugen dort Bare-Clones und verwalten eine lokale Registry. `sync` verweigert jedes Ziel, das nicht registriert und innerhalb dieses Ordners liegt. Diese Module dürfen nie für Discovery- oder Arbeits-Repositories wiederverwendet werden.

`forge.py` erweitert dies ausschließlich um die begrenzte API-Abfrage eines vom Nutzer angegebenen Forge-Accounts. `fetch-account` zeigt zuerst die gefundenen URLs und übergibt nur diese anschließend an denselben registrierten Clone-Pfad. Die Abfrage folgt weder Contributors noch Followern oder Fork-Netzwerken; private Sichtbarkeit benötigt ein Token aus einer benannten Umgebungsvariable.
