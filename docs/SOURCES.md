# Zusätzliche Quellen und sichere Synchronisation

Der normale Befehl `analyze` ist strikt read-only und führt niemals ein `git fetch`, `git pull`, einen Checkout oder eine andere Änderung in einem analysierten Repository aus.

Für zusätzliche Analysequellen kann GitAnalytics explizit angegebene Git-URLs als neue Bare-Clones in einen eigenen Ordner laden. Das funktioniert mit GitHub, GitLab, Codeberg, Gitea, Forgejo, Gogs und selbst gehosteten Git-Servern, weil ausschließlich die Git-URL verwendet wird.

```bash
gitanalytics fetch https://github.com/organisation/projekt.git \
  git@gitlab.com:gruppe/projekt.git \
  --destination ~/GitAnalytics/sources

gitanalytics analyze ~/GitAnalytics/sources --output ~/GitAnalytics/report
```

## Repositories eines Accounts importieren

`fetch-account` ergänzt die explizite URL-Liste um eine begrenzte Forge-Abfrage. Der Befehl fragt nur die Repositories eines angegebenen Benutzer- oder Organisationsaccounts ab; er crawlt keine Profile, Contributors, Follower oder transitive Fork-Beziehungen.

```bash
gitanalytics fetch-account --forge github --account name \
  --destination ~/GitAnalytics/sources --dry-run

gitanalytics fetch-account --forge gitlab --account gruppe \
  --destination ~/GitAnalytics/sources
```

Standard ist `--visibility public` ohne Forks. `--visibility private` und `--visibility all` verlangen `--token-env NAME`; der Token wird aus dieser Umgebungsvariable gelesen und erscheint daher weder in der Shell-Historie noch in Prozessargumenten. Für GitHub werden Benutzer- und Organisationsaccounts unterstützt. Bei Gitea, Forgejo und Gogs ist `--base-url https://git.example.org` verpflichtend. Verwende `--clone-protocol ssh`, wenn der Zugriff über lokale SSH-Schlüssel erfolgen soll.

Die API liefert nur die für den Token sichtbaren Repositories. Private Repositories sind trotz erfolgreichem Import weiterhin standardmäßig als `private` klassifiziert und werden nur nach einer ausdrücklichen Freigaberegel in ein öffentliches Profilpaket aufgenommen.

## Favorisierte Repositories importieren

`fetch-starred` lädt die sichtbare Liste der von einem GitHub- oder GitLab-Benutzer mit Stern markierten Repositories und übergibt nur diese URLs an den bestehenden sicheren Clone-Pfad. Es folgt keinen sozialen oder transitiven Beziehungen. Ein Stern bedeutet lediglich, dass ein Account ein Repository gespeichert oder interessant gefunden hat; er ist weder eine Mitwirkung noch eine Empfehlung oder Kollaborationskante.

```bash
gitanalytics fetch-starred --forge github --account name \
  --destination ~/GitAnalytics/sources --dry-run

gitanalytics fetch-starred --forge gitlab --account name \
  --destination ~/GitAnalytics/sources
```

Standard ist `--visibility public` ohne Forks. Die API kann nur Repositories zurückgeben, die für den angegebenen Account und gegebenenfalls Token sichtbar sind. `--visibility private` oder `--visibility all` verlangen einen Token über `--token-env NAME`; sie garantieren keinen Zugriff auf nicht sichtbare Favoriten. Für eine selbst gehostete GitLab-Instanz wird die API-Basis angegeben, beispielsweise `--base-url https://git.example.org/api/v4`.

Die bewusste Begrenzung auf explizite Quellen und ihre Folgen für Netzwerkaussagen erläutert [DECISIONS.md](DECISIONS.md).

## Besitz und Registrierung

`fetch` legt im Zielordner `.gitanalytics-sources.json` an. Nur Ziele, die dort nach einem erfolgreichen Clone registriert sind, gelten als tool-eigene Quellen. Vorhandene Repositories werden nicht übernommen; ein bereits existierendes, nicht registriertes Ziel wird abgelehnt.

Das Ziel darf nicht innerhalb eines bestehenden normalen oder Bare-Git-Repositories liegen. Dadurch kann der Befehl keine Arbeitskopie des Nutzers überschreiben.

## Synchronisieren

```bash
gitanalytics sync --destination ~/GitAnalytics/sources
```

`sync` führt ausschließlich bei den registrierten, tool-eigenen Bare-Clones `git fetch --prune --tags origin` aus. Es gibt keinen `pull`, keinen Checkout und keine Änderung an einem Repository außerhalb dieses Quellenordners. Die Registry wird bei jedem Zielpfad geprüft; manipulierte, fehlende oder nach außen verlinkte Ziele werden verweigert.

Ein beim `fetch` gesetztes `--depth` wird in der Registry gespeichert und bei der Synchronisation beibehalten. Shallow-Historien können keine vollständigen Langzeit- oder Distanzkennzahlen liefern.

## Vertrauens-Referenzen für optionale Netzwerkanalysen

Nach `fetch` und `sync` werden die vom Remote gelesenen Heads und Tags zusätzlich unter `refs/gitanalytics/trusted/*` gespeichert. Wenn die optionale Netzwerkanalyse mit `network.enabled: true` aktiviert wird, akzeptiert sie standardmäßig nur Commits, die entweder über `refs/remotes/*` oder diese verwalteten Vertrauens-Referenzen erreichbar sind.

Dadurch zählt ein lokaler, nicht gepushter Commit in einem normalen Clone nicht als neue direkte Netzwerkverbindung. Bei einem verwalteten Bare-Clone wird ein manuell erzeugter lokaler Ref ebenfalls nicht allein durch die Analyse als Remote-Evidenz behandelt.

Die Prüfung kann für Experimente mit `network.require_remote_reference: false` ausgeschaltet werden. Das erhöht aber das Risiko künstlicher Pfade erheblich und ist deshalb kein Standard.

## Grenzen der Expansion

GitAnalytics folgt nicht automatisch Contributor-Profilen, Forks oder transitive Repositories. Solches Crawling hätte unklare Datenschutz-, API-, Kosten- und Skalierungsfolgen. Weitere Knoten werden nur durch neue, vom Nutzer ausdrücklich angegebene URLs hinzugefügt. Begrenze Seeds, dokumentiere Quellen und prüfe die in [COLLABORATION.md](COLLABORATION.md) beschriebenen Messfehler.
