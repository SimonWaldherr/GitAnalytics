PYTHON ?= python3
ROOT ?= .
OUTPUT ?= ./gitanalytics-report
DATABASE ?= $(OUTPUT)/data/gitanalytics.sqlite3
SOURCES ?= ./gitanalytics-sources
URL ?=
FORGE ?= github
ACCOUNT ?=
GITHUB_USER ?=
PROFILE_OUTPUT ?= ./gitanalytics-profile-review
CONFIG_PATH ?= gitanalytics.json
SQL ?=
FORMAT ?= table
BIND ?= 127.0.0.1
PORT ?= 8765

.PHONY: help analyze refresh report fetch fetch-account fetch-starred sync profile init-config doctor query serve test clean

help:
	@echo "make analyze ROOT=/pfad/zu/repos OUTPUT=./report"
	@echo "make refresh ROOT=/pfad/zu/repos OUTPUT=./report  # inkrementell"
	@echo "make report OUTPUT=./report                       # HTML aus SQLite"
	@echo "make fetch SOURCES=./sources URL=https://host/org/repo.git"
	@echo "make fetch-account FORGE=github ACCOUNT=name SOURCES=./sources"
	@echo "make fetch-starred FORGE=github ACCOUNT=name SOURCES=./sources"
	@echo "make sync SOURCES=./sources                        # nur registrierte Bare-Clones"
	@echo "make profile OUTPUT=./report GITHUB_USER=name PROFILE_OUTPUT=./profile-review"
	@echo "make init-config CONFIG_PATH=./gitanalytics.json  # Beispielkonfiguration schreiben"
	@echo "make doctor                                        # Python-, SQLite- und Git-Diagnose"
	@echo "make query OUTPUT=./report SQL=\"SELECT ...\" FORMAT=table"
	@echo "make serve OUTPUT=./report PORT=8765"
	@echo "make test"

analyze:
	$(PYTHON) -m gitanalytics analyze "$(ROOT)" --output "$(OUTPUT)"

refresh:
	$(PYTHON) -m gitanalytics analyze "$(ROOT)" --output "$(OUTPUT)"

report:
	$(PYTHON) -m gitanalytics report "$(DATABASE)" --output "$(OUTPUT)"

fetch:
	$(PYTHON) -m gitanalytics fetch "$(URL)" --destination "$(SOURCES)"

fetch-account:
	$(PYTHON) -m gitanalytics fetch-account --forge "$(FORGE)" --account "$(ACCOUNT)" --destination "$(SOURCES)"

fetch-starred:
	$(PYTHON) -m gitanalytics fetch-starred --forge "$(FORGE)" --account "$(ACCOUNT)" --destination "$(SOURCES)"

sync:
	$(PYTHON) -m gitanalytics sync --destination "$(SOURCES)"

profile:
	$(PYTHON) -m gitanalytics profile "$(DATABASE)" --github-user "$(GITHUB_USER)" --output "$(PROFILE_OUTPUT)"

init-config:
	$(PYTHON) -m gitanalytics init-config "$(CONFIG_PATH)"

doctor:
	$(PYTHON) -m gitanalytics doctor

query:
	$(PYTHON) -m gitanalytics query "$(DATABASE)" $(if $(SQL),"$(SQL)",) --format "$(FORMAT)"

serve:
	$(PYTHON) -m gitanalytics serve "$(OUTPUT)" --bind "$(BIND)" --port "$(PORT)"

test:
	$(PYTHON) -m unittest discover -s tests -v

clean:
	@echo "Ausgabeordner wird absichtlich nicht automatisch gelöscht."
