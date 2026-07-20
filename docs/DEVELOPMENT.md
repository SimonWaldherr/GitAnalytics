# Entwicklung und Modulgrenzen

GitAnalytics trennt die Anwendung in klar abgegrenzte Schichten. Neue Funktionen sollten in die passende Schicht kommen und keine neue Querschnittslogik in CLI, Datenbank und Bericht zugleich duplizieren.

| Modul | Verantwortung |
| --- | --- |
| `cli.py` | Argumente, sichere Ausgabeorte, Befehlsorchestrierung und lokale Indizes |
| `discovery.py` | ausschließliche Repository-Erkennung im Dateisystem |
| `git_reader.py` | ausschließlich read-only Git-Aufrufe und Rohdatenerfassung |
| `database.py` | Schema, Migrationen, Transaktionen und Abfragen |
| `analytics.py` | Portfolio-, Aktivitäts-, Code- und Qualitätsaggregationen |
| `collaboration.py` | optionale bipartite Autoren-/Repository-Netzwerkanalyse |
| `privacy.py` | fail-closed Repository-Klassen und sichere Zielortprüfung |
| `profile.py` | minimale, nur aus `public`-Repos erzeugte Profilpakete |
| `forge.py` | begrenzte, explizite Account-Abfrage über Forge-APIs |
| `sources.py` | Registry und Synchronisation ausschließlich tool-eigener Bare-Clones |
| `report.py` | Offline-HTML, I18N, ARIA und clientseitige Filter |
| `exports.py` | Markdown-, JSON-, CSV-, Manifest- und Datenwörterbuch-Ausgaben |

## Regeln für Änderungen

- Discovery- und Analyse-Repositories bleiben strikt read-only. Neue Daten oder Caches gehören in den Ausgabeordner; nur `sources.py` darf ausdrücklich neu angelegte, registrierte Bare-Clones im separaten Quellenordner schreiben.
- Git-Rohdaten werden zuerst in `git_reader.py` ergänzt; normalisierte Speicherung folgt in `database.py`; Kennzahlen folgen anschließend in einem fachlichen Analytics-Modul.
- Neue optionale Netzwerklogik gehört in ein eigenes Modul, nicht in die allgemeine Analytics-Fassade.
- Das HTML bleibt absichtlich als einzelner Offline-Report ohne externe Assets. Wiederverwendbare Berechnung und Datenaufbereitung gehören jedoch nicht in den Browsercode.
- Jede neue Kennzahl benötigt eine Definition in `docs/METRICS.md`; jede neue Annahme oder Einschränkung gehört zusätzlich in die fachliche Dokumentation, etwa `docs/COLLABORATION.md`. Neue oder geänderte grundlegende Modellentscheidungen werden außerdem mit Status, Begründung und Folge in `docs/DECISIONS.md` festgehalten.
- Tests decken mindestens Datenpipeline, Datenschutz/Read-only-Verhalten und sichtbare Reportdaten ab.

## Dokumentationslandkarte

- [README](../README.md): Installation, Nutzung und Konfiguration.
- [ARCHITECTURE.md](ARCHITECTURE.md): Datenfluss und Persistenz.
- [METRICS.md](METRICS.md): präzise Kennzahlendefinitionen.
- [COLLABORATION.md](COLLABORATION.md): Annahmen und Messfehler der optionalen Netzwerkanalyse.
- [DECISIONS.md](DECISIONS.md): begründete Architektur- und Modellentscheidungen der Netzwerkanalyse.
- [PRIVACY.md](PRIVACY.md): Datenklassen und öffentliche Profilpakete.
- [SOURCES.md](SOURCES.md): explizite Quellen, Synchronisation und Vertrauens-Referenzen.
