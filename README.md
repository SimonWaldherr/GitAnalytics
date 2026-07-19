# GitAnalytics

GitAnalytics ist ein lokales, read-only Analysewerkzeug für eine Sammlung von Git-Repositories. Es durchsucht einen oder mehrere Stammordner, liest Git-Metadaten und die Inhalte der versionierten `HEAD`-Blobs, speichert einen wiederverwendbaren Snapshot in SQLite und erzeugt daraus einen vollständig offline nutzbaren HTML-Bericht sowie JSON- und CSV-Exporte.

Die normale Analyse benötigt keine GitHub-, GitLab- oder Cloud-Verbindung. Sie führt keinen Fetch aus und verändert weder Worktrees noch `.git`-Verzeichnisse. Die separat opt-inbare Quellenfunktion arbeitet ausschließlich in neu angelegten, registrierten Bare-Clones.

Für Datenmodell, Kennzahlendefinitionen, Datenschutzgrenzen und Weiterentwicklung siehe die [Dokumentationslandkarte](docs/DEVELOPMENT.md).

## Funktionsumfang

GitAnalytics erfasst und berechnet unter anderem:

- Aktivität nach Jahr, Monat, Tag, Wochentag, Stunde und Wochentag-Stunden-Matrix
- aktivste Tage, längste tägliche Serie und längste Aktivitätslücke
- Vergleiche der letzten 30, 90 und 365 Tage mit der jeweiligen Vorperiode
- Autoren, E-Mail-Identitäten, `.mailmap`, frei definierbare Aliase und Bot-Erkennung
- Autorenkonzentration, Gini, HHI sowie BF50/BF80-Heuristiken
- privacy-klassifizierte Repositories (`exclude`, `private`, `public`) und einen fail-closed, lokal prüfbaren GitHub-Profilentwurf
- Commits, Autoren, Churn, Aktivität, Branches, Tags und Hauptsprache pro Repository
- Insertions, Deletions, Binärdateien, Commit-Größen und historische Datei-Touches
- aktuelle Sprachverteilung des `HEAD` anhand von Git-Blobs
- dynamische Dashboard-Filter nach letztem Bearbeitungszeitpunkt (1, 7, 30, 180, 365 Tage und weitere), Repository, Programmiersprache und Dateityp
- Kommentarzeilen und Kommentardichte je Repository und Sprache, getrennt nach Zeilen-, Block- und Python-Dokumentationskommentaren
- Codezeilen, Kommentarzeilen, HEAD-Dateien und Kommentar-Dichte als zusätzliche Portfolio-KPIs
- Datei-Hotspots, Verzeichnisaktivität und Sprachaktivität über die Historie
- erkannte CI-Systeme (GitHub Actions, GitLab CI, Jenkins, CircleCI, Azure Pipelines, Travis CI und Bitbucket Pipelines) sowie Lizenzhinweise pro Repository
- Conventional-Commit-ähnliche Typen, Scopes, Breaking Changes und Issue-Referenzen
- Git-Tags mit Creator-Datum
- shallow/partial/bare Repositories, Scanfehler und mögliche Identitätsduplikate

Der HTML-Bericht enthält keine externen Skripte, Fonts, CDNs oder Tracker. Er kann direkt per `file://` geöffnet werden.

> **Kennzahlen richtig lesen:** GitAnalytics misst beobachtbare Spuren in Git-Historien, nicht den Wert von Menschen, Teams oder Projekten. Commits, Codezeilen, Churn, Aktivität, Kommentar-Dichte und Konzentrationswerte sind Hinweise für Rückfragen – keine Produktivitäts-, Qualitäts- oder Leistungsrangliste. Werden sie zum Ziel, können sie Verhalten verzerren: Mehr Commits, Code oder Modellaktivität bedeuten nicht automatisch bessere Ergebnisse. Nutze sie stets zusammen mit fachlichem Kontext, Qualitätssicherung und menschlichem Urteil. Details stehen in [docs/METRICS.md](docs/METRICS.md) und [docs/DECISIONS.md](docs/DECISIONS.md).

### Kommentar-Analyse

GitAnalytics liest dafür ausschließlich Blob-Inhalte aus dem aktuellen `HEAD` über Git-Plumbing; der Arbeitsbaum wird nicht ausgecheckt oder verändert. Leere Zeilen zählen nicht zur Dichte. Die Kennzahl lautet `Kommentarzeilen / (Kommentarzeilen + Codezeilen)` und ist eine pragmatische, sprachabhängige Heuristik: Sie erkennt kommentierende Zeilen mit `#`, `//`, `--`, `/* … */`, `<!-- … -->` sowie Python-Docstrings. Inline-Kommentare verbleiben als Codezeile, damit die Dichte nicht durch einzelne End-of-Line-Hinweise überzeichnet wird. Dateien über 2 MB und Binärdateien werden nicht inhaltlich gezählt.

Die Analyse ist standardmäßig aktiv und kann bei sehr großen Repositories über die Konfiguration deaktiviert werden:

```json
{
  "history": { "collect_comments": false }
}
```

### Interaktive Filter

Im HTML-Bericht stehen oberhalb aller Seiten Filter für den letzten Bearbeitungszeitpunkt, Repository, Sprache und Dateityp zur Verfügung. Der Zeitfilter wählt Repositories anhand ihres jüngsten Commits. Mehrfachauswahl ist möglich; die Übersichts-, Repository- und Code-KPIs sowie die Kommentar-Tabellen verwenden unmittelbar die Auswahl.

Alle Visualisierungen mit einer Repository-Zuordnung können ebenfalls als Filter dienen: Ein Klick ersetzt die zugrunde liegende Repository-Auswahl, Shift, Ctrl oder Cmd kombiniert sie. Das gilt auch für Autoren-, Commit-Typ- und Zeit-Elemente; sie wählen die Repositories, aus denen der jeweilige Wert stammt, statt Personen als Leistungsfilter zu behandeln. Der Hinweis neben der Filterleiste zeigt die aktuell verbleibende Repository-Anzahl.

Tabellen lassen sich per Maus oder Tastatur nach jeder Spalte sortieren. Die aktive Sortierrichtung wird sichtbar und über `aria-sort` vermittelt, damit sie auch mit Screenreadern nachvollziehbar bleibt.

## Voraussetzungen

- Python 3.10 oder neuer
- Git im `PATH`
- bei Installation unter Windows: `tzdata` wird automatisch mitinstalliert, damit IANA-Zeitzonen verfügbar sind

Für einen Aufruf direkt aus einem ausgecheckten Projektordner ohne Installation gilt unter Windows: Wird eine IANA-Zeitzone wie `Europe/Berlin` verwendet, muss `tzdata` zuvor installiert sein (`python -m pip install tzdata`). Die Modi `commit` und `UTC` benötigen es nicht.

## Schnellstart

Ohne Installation aus dem entpackten Projektordner:

```bash
python -m gitanalytics analyze ~/Projects
```

Unter Windows:

```powershell
py -m gitanalytics analyze "C:\Users\Name\Projects"
```

Installiert als Kommando:

```bash
python -m pip install .
gitanalytics analyze ~/Projects
```

## Makefile

Das Makefile schreibt ausschließlich in den angegebenen Ausgabeordner und niemals in die analysierten Repositories:

```bash
make analyze ROOT=~/Projects OUTPUT=./gitanalytics-report
make refresh ROOT=~/Projects OUTPUT=./gitanalytics-report
make report OUTPUT=./gitanalytics-report
make serve OUTPUT=./gitanalytics-report PORT=8765
make fetch SOURCES=~/GitAnalytics/sources URL=https://github.com/organisation/projekt.git
make fetch-account FORGE=github ACCOUNT=mein-name SOURCES=~/GitAnalytics/sources
make fetch-starred FORGE=github ACCOUNT=mein-name SOURCES=~/GitAnalytics/sources
make sync SOURCES=~/GitAnalytics/sources
make profile OUTPUT=./gitanalytics-report GITHUB_USER=mein-github-name PROFILE_OUTPUT=./gitanalytics-profile-review
make init-config CONFIG_PATH=./gitanalytics.json
make doctor
make query OUTPUT=./gitanalytics-report SQL="SELECT repository, commits FROM v_repository_summary ORDER BY commits DESC" FORMAT=table
make test
```

`refresh` verwendet zusätzlich `data/repository-index.json`: Der Index vergleicht lokal `HEAD`, lose Refs, `packed-refs` und das Reflog. Nur bei veränderten Git-Metadaten startet GitAnalytics einen Git-Prozess und liest den Snapshot erneut. Der Index befindet sich ausschließlich im Ausgabeordner.

`report`, `profile` und `query` verwenden standardmäßig `DATABASE=$(OUTPUT)/data/gitanalytics.sqlite3`; eine abweichende Datenbank lässt sich direkt über `DATABASE=` überschreiben, etwa `make query DATABASE=./andere.sqlite3 SQL="..."`.

## Optionale Netzwerkanalyse

GitAnalytics fokussiert standardmäßig auf klassische Repository-Kennzahlen: Aktivität, Churn, Sprachen, Kommentar-Dichte, Releases, CI, Lizenzen, Hotspots und Datenqualität. Die experimentelle Autoren-/Repository-Netzwerkanalyse ist deaktiviert und erscheint im Bericht nur, wenn sie ausdrücklich eingeschaltet wird:

```json
{
  "network": {
    "enabled": true,
    "reference_names": ["Referenzperson"],
    "max_display_nodes": 500
  }
}
```

Die optionale Netzwerkanalyse enthält Autoren und Repositories als getrennte Knoten. Im aktuellen Basismodell sind zwei Autoren über ein Repository verbunden, wenn beide die konfigurierten Mindestbeiträge und den zulässigen zeitlichen Abstand erfüllen. Die Distanz ist die kleinste Zahl von Autor-zu-Autor-Schritten; jeder Schritt weist das vermittelnde Repository aus.

Das ist technische Repository-Nähe, kein Nachweis persönlicher Bekanntschaft oder Zusammenarbeit. Die bekannte Idee einer Distanz zu einer Referenzperson ist daher nur ein anschaulicher Einstieg, nicht der Zweck der Funktion. Das aktuelle Basismodell legt den Pfad mit den vermittelnden Repositories offen; ein späteres, belastbareres Modell soll zusätzlich Ereignisse, Quellen, Zeitraum, Konfiguration, Modellversion und Vertrauensniveau pro Verbindung ausweisen. Service-Accounts, Mindestbeiträge, Zeitabstände und Remote-Evidenz sind in `network` konfigurierbar. Die vollständigen Messgrenzen, gegenwärtigen Grenzen und Ziele eines belastbareren Kollaborationsmodells stehen in [docs/COLLABORATION.md](docs/COLLABORATION.md).

Warum diese Schutzregeln gewählt wurden und welche Grenzen bewusst offen bleiben, erläutert [docs/DECISIONS.md](docs/DECISIONS.md). Dort ist auch jeweils markiert, ob eine Regel bereits umgesetzt oder erst Teil des Zielmodells ist.

## Weitere Repositories herunterladen

`fetch` unterstützt jede Git-URL, somit GitHub, GitLab, Gitea, Gogs und selbst gehostete Git-Server. Er klont ausschließlich in einen explizit angegebenen, separaten Zielordner und registriert jeden Bare-Clone dort. Ziele innerhalb eines bestehenden Repositories werden abgelehnt:

```bash
gitanalytics fetch https://github.com/organisation/projekt.git \
  git@gitlab.com:gruppe/projekt.git \
  --destination ~/GitAnalytics/sources

gitanalytics analyze ~/GitAnalytics/sources --output ~/GitAnalytics/report
```

Nur diese registrierten, tool-eigenen Bare-Clones können später aktualisiert werden:

```bash
gitanalytics sync --destination ~/GitAnalytics/sources
```

`sync` verwendet `fetch --prune --tags`, nie `pull` oder einen Checkout, und ändert keine vorhandenen Arbeits-Repositories. Weitere Details zur Quellen-Registry und zu verwalteten Bare-Clones stehen in [docs/SOURCES.md](docs/SOURCES.md).

### Alle Repositories eines Forge-Accounts

`fetch-account` fragt ausschließlich die API des ausdrücklich angegebenen GitHub-, GitLab-, Gitea-, Forgejo- oder Gogs-Accounts ab. Es folgt weder Followern noch Contributors oder Fork-Netzwerken. Standardmäßig werden nur öffentliche, nicht geforkte Repositories angezeigt und anschließend als getrennte, registrierte Bare-Clones geladen. Mit `--dry-run` lässt sich die Liste vor dem Klonen prüfen:

```bash
gitanalytics fetch-account --forge github --account mein-name \
  --destination ~/GitAnalytics/sources --dry-run

gitanalytics fetch-account --forge gitlab --account gruppe \
  --destination ~/GitAnalytics/sources
```

Für private oder alle sichtbaren Repositories wird ein Token nur über eine Umgebungsvariable übergeben, nie als Kommandoargument. Die tatsächlich sichtbare Menge hängt von dessen Berechtigungen ab:

```bash
export GITHUB_TOKEN=…
gitanalytics fetch-account --forge github --account mein-name \
  --visibility all --token-env GITHUB_TOKEN --clone-protocol ssh \
  --destination ~/GitAnalytics/sources
```

Bei Gitea, Forgejo und Gogs ist zusätzlich die Forge-Basis erforderlich, etwa `--base-url https://git.example.org`. `--include-forks` und `--max-repositories` sind bewusste, explizite Erweiterungen des Imports.

### Favorisierte Repositories eines Accounts

`fetch-starred` importiert die öffentlich sichtbaren, von einem GitHub- oder GitLab-Account mit Stern markierten Repositories. Ein Stern ist ein Lesezeichen oder Interessenssignal, kein Beleg für Mitarbeit, Zustimmung oder eine Kollaborationsbeziehung. Der Befehl folgt nur dieser direkten Liste und lässt sich zuerst als Vorschau ausführen:

```bash
gitanalytics fetch-starred --forge github --account mein-name \
  --destination ~/GitAnalytics/sources --dry-run

gitanalytics fetch-starred --forge gitlab --account name \
  --destination ~/GitAnalytics/sources
```

Sichtbare private Favoriten benötigen `--visibility all --token-env NAME`; die API und Berechtigungen bestimmen, welche davon tatsächlich zurückgegeben werden. Favorisierte Forks bleiben standardmäßig ausgeschlossen und können nur mit `--include-forks` einbezogen werden.

Eigener Ausgabeordner:

```bash
gitanalytics analyze ~/Projects --output ~/gitanalytics-reports/meine-projekte
```

Der Ausgabeordner muss außerhalb aller analysierten Repositories liegen. GitAnalytics prüft das, bevor die SQLite-Datei oder andere Dateien angelegt werden.

## Standardausgabe

Ohne `--output` wird ein stabiler, vom Stammordner abgeleiteter Ordner verwendet:

- Linux: `$XDG_DATA_HOME/gitanalytics/reports/...` oder `~/.local/share/gitanalytics/reports/...`
- macOS: `~/Library/Application Support/gitanalytics/reports/...`
- Windows: `%LOCALAPPDATA%\gitanalytics\reports\...`

Der Bericht besteht aus:

```text
<output>/
├── index.html
├── DATA_DICTIONARY.md
├── MANIFEST.txt
└── data/
    ├── gitanalytics.sqlite3
    ├── report.json
    ├── effective-config.json
    └── csv/
        ├── summary.csv
        ├── repositories.csv
        ├── contributors.csv
        ├── activity_daily.csv
        ├── hot_files.csv
        └── ...
```

`gitanalytics.sqlite3` ist zugleich Cache und BI-Datenbasis. Unveränderte Repositories werden bei späteren Läufen anhand der relevanten Refs, `.mailmap`, shallow-Metadaten und Scan-Konfiguration wiederverwendet.

## Typische Aufrufe

Alle lokalen Branches und Tags, der Standardmodus:

```bash
gitanalytics analyze ~/Projects --scope local
```

Nur der aktuell ausgecheckte Branch:

```bash
gitanalytics analyze ~/Projects --scope current
```

Alle lokal vorhandenen Refs, einschließlich Remote-Tracking-Refs:

```bash
gitanalytics analyze ~/Projects --scope all
```

Explizite Revisionen:

```bash
gitanalytics analyze ~/Projects --ref main --ref release/2.x
```

Zeitraum und einheitliche Zeitzone:

```bash
gitanalytics analyze ~/Projects \
  --since 2024-01-01 \
  --until 2025-12-31 \
  --timezone Europe/Berlin
```

Bots und Merge-Commits aus den effektiven Kennzahlen ausschließen:

```bash
gitanalytics analyze ~/Projects --no-include-bots --no-include-merges
```

Globale SHA-Duplikate entfernen, etwa bei Forks oder Spiegeln:

```bash
gitanalytics analyze ~/Projects --deduplicate-global
```

Schneller Metadatenlauf ohne Numstat und Dateihistorie:

```bash
gitanalytics analyze ~/Projects \
  --no-collect-churn \
  --no-store-file-details \
  --no-collect-tree \
  --no-collect-releases
```

Cache vollständig neu aufbauen:

```bash
gitanalytics analyze ~/Projects --force
```

Mehrere Stammordner:

```bash
gitanalytics analyze ~/work ~/private ~/archive
```

## Konfiguration

Eine kommentierbare JSON-Datei gibt es naturgemäß nicht; GitAnalytics erzeugt deshalb eine vollständige Beispielkonfiguration:

```bash
gitanalytics init-config gitanalytics.json
```

Verwendung:

```bash
gitanalytics analyze ~/Projects --config gitanalytics.json
```

CLI-Argumente überschreiben die entsprechenden Werte der Konfiguration.

### Autoren zusammenführen

GitAnalytics respektiert standardmäßig `.mailmap`. Ergänzend können projektübergreifende Aliasregeln verwendet werden:

```json
{
  "identity": {
    "aliases": [
      {
        "name": "Max Mustermann",
        "email": "max@example.com",
        "match_emails": [
          "max@old-company.example",
          "*+max@users.noreply.github.com"
        ],
        "match_names": ["M. Mustermann", "maxm"]
      }
    ]
  }
}
```

Muster verwenden Shell-Globs. Aliasregeln werden in ihrer Reihenfolge ausgewertet; die erste passende Regel gewinnt.

### Datenschutz und Profilentwürfe

Für teilbare Berichte:

```json
{
  "privacy": {
    "include_absolute_paths": false,
    "show_emails": false,
    "anonymize_authors": true,
    "default_repository_classification": "private",
    "repository_rules": [
      {"match": "oss/*", "classification": "public"},
      {"match": "**/customer-*", "classification": "exclude"}
    ]
  }
}
```

Commit-Betreffzeilen werden standardmäßig nicht gespeichert. Remote-URLs werden nicht gespeichert; optional werden nur normalisierte Hostnamen wie `github.com` erfasst.

`private` ist der sichere Standard und bleibt vollständig aus öffentlichen Profilpaketen heraus. `exclude` entfernt den Snapshot beim nächsten Lauf aus dem lokalen Cache; `public` ist eine explizite Freigabe für `gitanalytics profile`, keine Aussage über die tatsächliche öffentliche Verfügbarkeit oder Lizenz des Repositories. Regeln werden in Reihenfolge ausgewertet; die erste passende Regel gewinnt.

Ein GitHub-Profil wird ausschließlich als separates, prüfbares Paket erzeugt und nie gepusht:

```bash
gitanalytics profile ~/gitanalytics-report/data/gitanalytics.sqlite3 \
  --github-user mein-github-name \
  --output ~/profile-review
```

Standardmäßig enthält es nur Namen freigegebener Repositories und eine grobe Sprachübersicht. Exakte Commit-/Datei-/Release-Zahlen und Aktivitätsdaten sind Opt-ins. Die vollständige Freigabe- und Datenminimierungsstrategie beschreibt [docs/PRIVACY.md](docs/PRIVACY.md).

## Bericht aus vorhandener Datenbank neu erzeugen

Damit lassen sich Darstellung und Datenschutz ändern, ohne Git erneut zu lesen:

```bash
gitanalytics report ~/gitanalytics-report/data/gitanalytics.sqlite3 \
  --output ~/gitanalytics-report-anonym \
  --anonymize-authors \
  --no-show-emails
```

## Read-only SQL

Die SQLite-Datenbank kann mit jedem BI- oder SQL-Werkzeug geöffnet werden. GitAnalytics enthält zusätzlich ein strikt read-only Query-Kommando:

```bash
gitanalytics query ~/gitanalytics-report/data/gitanalytics.sqlite3 \
  "SELECT repository, commits FROM v_repository_summary ORDER BY commits DESC"
```

JSON-Ausgabe:

```bash
gitanalytics query data/gitanalytics.sqlite3 \
  "SELECT * FROM v_author_summary ORDER BY commits DESC LIMIT 20" \
  --format json
```

CSV-Ausgabe:

```bash
gitanalytics query data/gitanalytics.sqlite3 \
  "SELECT activity_year, COUNT(*) AS commits FROM v_commits GROUP BY activity_year" \
  --format csv > commits-by-year.csv
```

Das Query-Kommando öffnet SQLite mit `mode=ro` und `PRAGMA query_only=ON`. Ein SQLite-Authorizer blockiert zusätzlich `ATTACH`, DDL, Transaktionen und sämtliche Schreiboperationen, damit auch keine Nebendatenbank angelegt werden kann.

## Lokaler Webserver

Der Bericht funktioniert direkt als Datei. Für Browser, die lokale Einschränkungen anwenden:

```bash
gitanalytics serve ~/gitanalytics-report --port 8765
```

Danach ist er lokal unter `http://127.0.0.1:8765/` erreichbar. GitAnalytics bindet standardmäßig nur an Loopback.

## Discovery

GitAnalytics erkennt normale Repositories, Bare-Repositories und Worktrees mit `.git`-Datei. Standardmäßig wird nach dem Fund eines Repositories nicht in dessen normale Unterordner abgestiegen. Dadurch werden Verzeichnisse innerhalb eines Monorepos nicht fälschlich als Projekte behandelt.

Relevante Optionen:

```text
--max-depth N
--include-hidden / --no-include-hidden
--follow-symlinks / --no-follow-symlinks
--nested-repositories / --no-nested-repositories
--ignore GLOB
```

Ordner wie `node_modules`, `vendor`, `.venv`, `target`, `dist` und `build` werden standardmäßig übersprungen.

## Read-only-Modell

GitAnalytics setzt für alle Git-Prozesse unter anderem:

```text
GIT_OPTIONAL_LOCKS=0
GIT_TERMINAL_PROMPT=0
GIT_NO_REPLACE_OBJECTS=1
GIT_NO_LAZY_FETCH=1
```

Zusätzlich werden Git-Konfigurationswerte wie `protocol.allow=never`, `maintenance.auto=false`, `gc.auto=0` und `fetch.writeCommitGraph=false` pro Prozess gesetzt. Dadurch werden Transportzugriffe und automatische Wartung unterbunden.

`analyze` verwendet ausschließlich lesende Befehle wie `git rev-parse`, `git for-each-ref`, `git log`, `git ls-tree`, `git remote -v` und lesende `git config`-Abfragen. Es verwendet kein `shell=True`, führt keinen Fetch aus und lädt bei Partial Clones keine fehlenden Objekte nach. Nur die separate, opt-in `fetch`/`sync`-Funktion schreibt in neu angelegte, registrierte Bare-Clones im ausdrücklich angegebenen Quellenordner; sie ändert niemals vorhandene Repositories.

GitAnalytics schreibt ausschließlich in den Ausgabeordner. Absolute Repository-Pfade erscheinen nur bei aktivierter Datenschutzoption im Bericht; intern benötigt SQLite sie für inkrementelle Folgeläufe.

## Semantik und Grenzen

Ein Commit ist kein valides Maß für individuelle Produktivität. Die Werte werden durch Squash-Merges, Rebase, importierte Historien, Spiegel, Forks, Pair Programming, Bots, Zeitzonen, Monorepos, Codegenerierung und unterschiedliche Arbeitsweisen beeinflusst.

Kennzahlen sollen Fragen eröffnen, keine Menschen bewerten. Eine ungewöhnlich hohe oder niedrige Zahl kann ein wichtiges Signal sein, kann aber ebenso aus Tooling, Projektschnitt, fehlenden Daten oder einer bewusst gewählten Arbeitsweise entstehen. Insbesondere dürfen sie nicht als automatische Grundlage für Leistungsbeurteilungen, Recruiting, Vergütung oder Personalentscheidungen verwendet werden. Gute Steuerung betrachtet Ergebnisse, Qualität, Sicherheit, Wartbarkeit, Nutzerwirkung, Kosten und Kontext gemeinsam – nicht nur eine bequem zählbare Stellvertretergröße.

BF50 und BF80 geben an, wie viele Autoren gemeinsam mindestens 50 beziehungsweise 80 Prozent der Commits erzeugt haben. Diese Werte sind Konzentrationsheuristiken, keine organisatorische Risikoanalyse.

Churn ist die Summe von Git-Numstat-Additionen und -Deletionen. Binärdateien tragen keine Zeilenzahl bei. Umbenennungen werden standardmäßig mit Git-Rename-Erkennung verarbeitet. Historische Hotspots messen Änderungshäufigkeit, nicht Fehleranfälligkeit.

Sprachen im aktuellen `HEAD` werden anhand von Pfad und Dateiendung klassifiziert und nach Git-Blob-Größe gewichtet. Historische Sprachaktivität basiert auf geänderten Dateipfaden. GitAnalytics führt keinen Checkout aus und liest keine Arbeitsbaumdateien für die Inhaltsanalyse.

## Skalierung

Commit-Datensätze werden gestreamt und in Batches in SQLite geschrieben. Große Historien müssen nicht vollständig im Python-Arbeitsspeicher liegen. Dateidetails erhöhen Laufzeit und Datenbankgröße deutlich; für sehr große Monorepos können sie deaktiviert werden:

```bash
gitanalytics analyze /data/repos --no-store-file-details
```

Eine bewusste Obergrenze ist ebenfalls möglich:

```bash
gitanalytics analyze /data/repos --max-commits-per-repository 100000
```

Der Bericht kennzeichnet dann, dass Langzeitkennzahlen abgeschnitten sein können.

## Diagnose und Tests

```bash
gitanalytics doctor
python -m unittest discover -s tests -v
```

## Projektstruktur

```text
gitanalytics/
├── analytics.py      SQL-basierte Kennzahlen
├── cli.py            Kommandozeile und Orchestrierung
├── collaboration.py  optionale Autoren-/Repository-Netzwerkdistanzen
├── config.py         Konfiguration, Aliase und Validierung
├── console.py        Terminalausgabe und Tabellenformatierung
├── database.py       SQLite-Schema und Cache
├── discovery.py      Repository-Erkennung
├── exports.py        JSON-, CSV- und Manifest-Export
├── forge.py          explizite Forge-API-Discovery (GitHub, GitLab, Gitea, Forgejo, Gogs)
├── git_reader.py     read-only Git-Zugriff und Streaming-Parser
├── languages.py      Pfadbasierte Sprachklassifikation
├── models.py         Datenmodelle
├── privacy.py        fail-closed Repository-Privatsphärenklassifikation
├── profile.py        fail-closed öffentliches Profilpaket
├── report.py         eigenständiger Offline-HTML-Bericht
├── sources.py        verwaltete Bare-Clone-Quellenregistrierung
└── util.py           Hilfsfunktionen
```

Weitere Details stehen in `docs/ARCHITECTURE.md`, `docs/METRICS.md` und im erzeugten `DATA_DICTIONARY.md`.
