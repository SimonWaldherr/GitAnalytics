# Privatsphäre und öffentliche Profilpakete

GitAnalytics unterscheidet zwischen dem lokalen Analyse-Snapshot und einem öffentlichen Profil-Entwurf. Ein lokaler Snapshot kann personenbezogene Git-Metadaten enthalten; ein Profilpaket darf das nicht implizit übernehmen.

## Repository-Klassen

| Klasse | Lokale Analyse | Lokaler Cache | Öffentlicher Profil-Export |
| --- | --- | --- | --- |
| `exclude` | nein | bei einem erneuten Lauf für diesen Pfad gelöscht | nein |
| `private` | ja | ja | nein |
| `public` | ja | ja | ja, aber nur über den expliziten `profile`-Befehl |

`private` ist der Standard. `public` bedeutet ausschließlich „für diesen Profil-Export freigegeben“; es ist keine Aussage darüber, ob Quellcode, Lizenz oder Remote tatsächlich öffentlich sind.

Regeln werden in Reihenfolge ausgewertet; die erste passende Regel gewinnt. Ein Glob wird gegen den absoluten Pfad, den Pfad relativ zur Analysewurzel, den Anzeigenamen und den Verzeichnisnamen geprüft.

```json
{
  "privacy": {
    "default_repository_classification": "private",
    "repository_rules": [
      {"match": "oss/*", "classification": "public"},
      {"match": "**/customer-*", "classification": "exclude"}
    ]
  }
}
```

`exclude` ist absichtlich stärker als ein UI-Filter: Beim nächsten Analyse-Lauf werden vorher gespeicherte Snapshots für diesen entdeckten Pfad mit ihren Commits, Dateiänderungen und Signalen aus dem lokalen SQLite-Cache entfernt. Bereits separat kopierte Exporte oder Backups werden dadurch nicht verändert und müssen bei Bedarf manuell gelöscht werden.

## Was standardmäßig öffentlich wird

Ein Profilpaket enthält ausschließlich explizit als `public` klassifizierte Repositories. Standardmäßig darf es enthalten:

- die freigegebenen Repository-Namen,
- die grobe Technologien-/Sprachübersicht dieser Repositories,
- einen vom Nutzer angegebenen GitHub-Namen.

Standardmäßig ausgeschlossen sind:

- alle `private`- und `exclude`-Repositories, auch als anonymisierte Summe,
- lokale Pfade, Remote-URLs und Forge-Hosts,
- Autorennamen, E-Mail-Adressen, Committer, Bots und optionale Netzwerkanalysen,
- Commit-Betreffzeilen, genaue Uhrzeiten, Code-/Kommentarzeilen und Hotspots,
- exakte Commit-, Datei- und Release-Zahlen,
- CI- und Lizenzsignale.

Diese Trennung vermeidet auch indirekte Lecks: Eine Sprachsumme, ein Zeitverlauf oder eine Netzwerkverbindung aus einem privaten Repository kann bereits Geschäftsbeziehungen, Technologieentscheidungen oder Projektgrößen offenlegen.

Auch öffentliche Netzwerkdaten bleiben personenbezogen und kontextsensitiv: Verknüpfte Accounts, historische Beiträge und abgeleitete Verbindungen können Arbeitsbeziehungen oder Pseudonyme sichtbar machen. Die Netzwerkanalyse bleibt deshalb optional; ihre Quellen- und Identitätsentscheidungen sind in [DECISIONS.md](DECISIONS.md) dokumentiert.

## Bewusste Opt-ins

Wer die Details veröffentlichen möchte, aktiviert sie in der Konfiguration des Analyse-Laufs oder beim Profil-Befehl:

```json
{
  "profile": {
    "include_repository_names": true,
    "include_languages": true,
    "include_exact_metrics": false,
    "include_last_activity_date": false
  }
}
```

`include_exact_metrics` erlaubt Commit-, Datei- und Release-Zahlen. `include_last_activity_date` zeigt nur ein Datum, niemals eine genaue Uhrzeit. Beides bleibt standardmäßig deaktiviert.

## Profilpaket erzeugen

Das Paket wird nur in einen separaten Ordner geschrieben; ein Ziel innerhalb eines Git-Repositories wird abgelehnt. GitAnalytics erstellt weder ein GitHub-Repository noch einen Commit und führt keinen Push aus.

```bash
gitanalytics profile report/data/gitanalytics.sqlite3 \
  --github-user mein-github-name \
  --output ./profile-review
```

Der Ordner enthält `README.md` und `PROFILE_DATA.md`. Beide Dateien sind vor dem manuellen Kopieren in ein GitHub-Profilrepository zu prüfen. Mit `--include-repo NAME` lässt sich die freigegebene Auswahl weiter einschränken.
