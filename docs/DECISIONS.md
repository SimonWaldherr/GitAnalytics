# Architekturentscheidungen zur optionalen Netzwerkanalyse

Dieses Dokument hält fachliche Entscheidungen fest, die das Verhalten der optionalen Netzwerkanalyse prägen. Es unterscheidet bewusst zwischen **heute umgesetzt** und **Zielbild**. So werden Annahmen nicht nachträglich als technische Tatsachen oder geplante Funktionen als vorhandene Eigenschaften dargestellt.

Die Analyse untersucht einen ausgewählten, unvollständigen Ausschnitt öffentlicher und lokal bereitgestellter Git-Historien. Sie ist kein Personenranking und keine Aussage über Kompetenz, Bekanntschaft, Einfluss oder die Qualität einer Zusammenarbeit.

## ADR-001: Netzwerkanalyse ist ein explizites Opt-in

**Status:** umgesetzt

Sie ist standardmäßig deaktiviert (`network.enabled: false`). Aktivität, Churn, Sprachen, Kommentar-Dichte, CI, Lizenzen und Hotspots sind die normalen Kennzahlen von GitAnalytics.

**Begründung:** Eine Repository-Distanz beruht auf Modellannahmen und kann leicht missverstanden werden. Als Standard-KPI würde sie eine Genauigkeit suggerieren, die reine Git-Historien nicht bieten.

**Folge:** Der Bericht zeigt die Netzwerkseite erst nach ausdrücklicher Aktivierung. Das Opt-in hält die Analyse als Experiment klar von regulären Repository-Kennzahlen getrennt.

## ADR-002: Gemeinsames Repository heißt Repository-Verbindung, nicht Zusammenarbeit

**Status:** umgesetzt

Das aktuelle Basismodell verbindet Autoren über ein Repository nur bei konfigurierter Mindestzahl von Beiträgen und begrenztem zeitlichem Abstand. Es bezeichnet diese Kante als *Repository-Verbindung*.

**Begründung:** Zwei Personen können in einem großen oder langlebigen Projekt völlig unabhängig voneinander arbeiten. Ein gemeinsames Repository ist daher höchstens ein schwaches Nähe-Signal, kein Nachweis persönlicher Interaktion.

**Folge:** Pull Requests, Reviews, Merges fremder Beiträge, Co-Authorship und Maintainer-Beziehungen werden nicht als bereits vorhandene direkte Kollaboration behauptet. Ihre spätere Erfassung ist ein Zielbild, kein Ersatz für diese präzise Sprache.

## ADR-003: Lokale, nicht veröffentlichte Commits sind keine Remote-Evidenz

**Status:** umgesetzt

Standardmäßig akzeptiert die Netzwerkanalyse nur Commits, die über `refs/remotes/*` oder verwaltete `refs/gitanalytics/trusted/*` erreichbar sind (`network.require_remote_reference: true`).

**Begründung:** Andernfalls könnte ein lokaler Commit in einem heruntergeladenen Repository unmittelbar eine künstliche Verbindung erzeugen. Ein von Git erreichbarer Commit ist allerdings ebenfalls kein Beweis für menschliche Zusammenarbeit oder Identität.

**Folge:** Die Schutzregel reduziert eine offensichtliche Manipulationsmöglichkeit. Sie kann für Experimente abgeschaltet werden, muss dann aber im Ergebnis als schwächere Evidenz verstanden werden.

## ADR-004: Bots und Service-Accounts werden standardmäßig ausgeschlossen

**Status:** umgesetzt

Die Netzwerkanalyse schließt bekannte Muster für Dependency-Updater, KI-Assistenten und andere Service-Accounts standardmäßig aus; die Muster sind konfigurierbar.

**Begründung:** CI-, Merge-, Release- und Dependency-Bots wirken sonst als Superknoten, die viele fachlich unabhängige Projekte künstlich verbinden. Eine Namensheuristik bleibt fehleranfällig: Nicht jeder Bot ist erkennbar, und nicht jedes passende Muster beschreibt einen Bot.

**Folge:** Ausschlussregeln sind sichtbar, veränderbar und Teil der Konfiguration. Sie sind keine endgültige Identitätsklassifikation. Künftige Modelle sollen Accounttyp, Ereigniskontext und Vertrauensniveau getrennt ausweisen.

## ADR-005: Signaturen sind ein Vertrauenssignal, kein Kollaborationsbeweis

**Status:** Zielbild

Eine gültige GPG-, SSH-, S/MIME- oder Forge-Signatur kann die Zuordnung zu einem Schlüssel oder Konto stützen. Sie beweist weder, dass ein Mensch den Code selbst schrieb, noch eine persönliche Zusammenarbeit; auch Automatisierung kann signieren.

**Begründung:** Eine Regel „nur signierte Commits zählen“ würde ältere Historien, kleine Projekte und Communities ohne etablierte Signaturpraxis systematisch benachteiligen.

**Folge:** Falls Signaturen erfasst werden, gehören sie als erklärtes Vertrauensmerkmal an eine Kante, nicht als pauschaler Ausschlussmechanismus. GitAnalytics wertet sie im aktuellen Netzwerkmodell noch nicht aus.

## ADR-006: Quellen werden ausdrücklich gewählt, nicht automatisch expandiert

**Status:** umgesetzt

`fetch` und `fetch-account` beziehen nur vom Nutzer angegebene URLs oder die direkte Repository-Liste eines angegebenen Forge-Accounts. Es gibt kein automatisches Folgen von Contributors, Followern, Profilen oder Fork-Netzwerken.

**Begründung:** Transitives Crawling hätte unklare Datenschutz-, API-, Kosten- und Skalierungsfolgen. Es würde außerdem die Datenbasis einer Berechnung unkontrollierbar erweitern.

**Folge:** Eine Distanz gilt immer nur für die dokumentierte Quellenmenge. Der Import erfolgt ausschließlich in registrierte, tool-eigene Bare-Clones; bestehende Arbeits-Repositories bleiben unverändert.

## ADR-007: Identitäten werden konservativ behandelt

**Status:** teilweise umgesetzt

GitAnalytics nutzt rohe Git-Identitäten, optional `.mailmap` und explizit konfigurierte Aliasregeln. Namen allein führen nicht zu einer automatischen Zusammenführung.

**Begründung:** Eine Person kann mehrere Accounts, Namen und E-Mail-Adressen verwenden; umgekehrt können Team-, Bot- oder Service-Accounts von mehreren Personen genutzt werden. Aggressive Zusammenführung erzeugt falsche Knoten und damit falsche Pfade.

**Folge:** Nicht aufgelöste Aliase können eine Person mehrfach darstellen. Das ist gegenüber einer unbelegten Gleichsetzung die bewusst konservativere Fehlerrichtung. Verifizierte Forge-Zuordnungen und Confidence-Level sind Zielbild.

## ADR-008: Repository- und Ereigniskontext sollen erhalten bleiben

**Status:** teilweise umgesetzt

Das aktuelle Modell führt Autoren und Repositories als getrennte Knoten; Pfade nennen die vermittelnden Repositories.

**Begründung:** Eine direkte Projektion „jede Person mit jeder Person“ verwischt, warum eine Verbindung besteht, und erzeugt in großen Repositories sehr viele bedeutungsarme Kanten. Forks, Mirrors, importierte Historien und global identische Commits verstärken dieses Problem zusätzlich.

**Folge:** Ein späteres Ereignismodell soll neben Repository, Quelle und Zeitraum auch Interaktionstyp, Fork-/Mirror-Provenienz, Identitätsvertrauen und Bot-Klassifikation speichern. Alternative Versionsverwaltungssysteme wie SVN, CVS, Mercurial, Bazaar oder Perforce sowie Mailinglisten und Gerrit bleiben bis zu einer expliziten Import- und Provenienzstrategie außerhalb des aktuellen Modells.

## ADR-009: Ergebnisse müssen reproduzierbar und erklärbar sein

**Status:** Zielbild; Konfiguration und Quellenregister sind bereits vorhanden

Eine belastbare Ausgabe sollte Referenzperson, vollständigen Pfad, Ereignisse, Zeitraum, Quellenmenge, Bot- und Identitätsregeln, Modellversion sowie Vertrauensniveau mitliefern. „Kein Pfad gefunden“ bedeutet nur: Im gewählten Datensatz und unter der gewählten Modellversion wurde kein Pfad gefunden.

**Begründung:** Kürzeste Pfade können oberflächliche Kontakte gegenüber langjähriger Zusammenarbeit bevorzugen. API-Limits, gelöschte oder private Repositories, Plattformgrenzen und Modellparameter verändern das Ergebnis.

**Folge:** Zukünftige Distanzvarianten müssen getrennt benannt und versioniert werden, etwa historische Repository-Nähe, zeitgewichtete Nähe oder direkte, belegte Kollaboration. Keine Variante darf als universelle oder objektive „Zahl“ ausgegeben werden.

## ADR-010: Kennzahlen sind Hinweise, keine Leistungsziele

**Status:** umgesetzt

GitAnalytics behandelt Commit-Zahlen, Churn, Codezeilen, Aktivität, Konzentration, Kommentar-Dichte und Netzwerkdistanzen als beschreibende Signale. Sie dürfen weder als unmittelbare Produktivitäts- oder Qualitätswerte bezeichnet noch ohne fachlichen Kontext für Ranglisten oder automatisierte Personalentscheidungen verwendet werden.

**Begründung:** Sobald eine gut zählbare Größe zum Ziel wird, kann sie das Verhalten stärker steuern als das eigentliche Ergebnis. Viele Commits, viele geänderte Zeilen oder hohe Aktivität können durch sinnvolle Arbeit entstehen, aber auch durch künstliche Aufteilung, Codegenerierung, ungeeignetes Tooling oder fehlende Bereinigung. Umgekehrt kann wertvolle Arbeit aus Löschen, Review, Design, Betrieb, Dokumentation, Gesprächen oder der Entscheidung bestehen, nichts zu ändern.

**Folge:** Der Bericht und die Dokumentation benennen die Messgrenzen. Auffällige Werte sollen Rückfragen auslösen und mit Qualität, Sicherheit, Wartbarkeit, Nutzerwirkung, Kosten, Datenabdeckung und Teamkontext gemeinsam beurteilt werden. Besonders Konzentrationswerte sind keine Ersatzmessung für personelle Resilienz oder Bus-Faktoren.

## ADR-011: Favorisierte Repositories sind eine Quellenliste, keine Beziehung

**Status:** umgesetzt für GitHub und GitLab

`fetch-starred` kann die sichtbaren, von einem ausdrücklich angegebenen Account mit Stern markierten Repositories importieren. Ein Stern wird ausschließlich als bewusste Auswahl einer Analysequelle behandelt.

**Begründung:** Sterne drücken je nach Person Lesezeichen, Interesse, spätere Prüfung oder eine historische Momentaufnahme aus. Sie belegen weder Mitarbeit noch Zustimmung, Qualität oder eine Kollaborationsbeziehung. Eine automatische Übernahme in den Netzwerkgraphen oder in Kennzahlen wäre deshalb irreführend.

**Folge:** Der Befehl folgt nur der direkten Sternliste, unterstützt eine Vorschau und nutzt anschließend denselben registrierten, separaten Clone-Pfad wie alle anderen Quellen. Sichtbarkeit bleibt durch API-Berechtigungen begrenzt; private Favoriten werden nicht als öffentlich freigegeben behandelt.

## Dokumentierte Grenzen

Die vollständige Liste der Messfehler und Datenlücken steht in [COLLABORATION.md](COLLABORATION.md). Dazu gehören große Repositories, triviale Beiträge, Manipulation, unvollständige Plattformdaten, private Repositories, alternative Versionsverwaltungssysteme und nicht in Git sichtbare Kollaborationsformen. Datenschutz- und Veröffentlichungsgrenzen stehen in [PRIVACY.md](PRIVACY.md), die Herkunft verwalteter Quellen in [SOURCES.md](SOURCES.md).
