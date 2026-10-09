UV ?= uv
.DEFAULT_GOAL := help

.PHONY: help sync check status demo reproduce ingest audit pilot-ingest pilot-audit

help:
	@printf '%s\n' \
	  'make reproduce  Sync the lockfile, lint, test, verify protocol, run the synthetic demo' \
	  'make check      Sync the lockfile, then run lint and tests' \
	  'make status     Show the current research gates' \
	  'make demo       Rebuild the synthetic engineering demonstration' \
	  'make ingest     Download/cache the SEC sample; requires SEC_USER_AGENT' \
	  'make audit      Build the offline audit packet for the five-issuer sample' \
	  'make pilot-ingest  Download/cache the 20-issuer development pilot' \
	  'make pilot-audit   Build the expanded pilot audit packet'

sync:
	$(UV) sync --locked

check: sync
	$(UV) run --locked --no-sync ruff check .
	$(UV) run --locked --no-sync pytest

status: sync
	$(UV) run --locked --no-sync disclosure status

demo: sync
	$(UV) run --locked --no-sync disclosure demo

reproduce: check
	$(UV) run --locked --no-sync disclosure status
	$(UV) run --locked --no-sync disclosure demo

ingest: sync
	$(UV) run --locked --no-sync disclosure ingest

audit: sync
	$(UV) run --locked --no-sync disclosure audit

pilot-ingest: sync
	$(UV) run --locked --no-sync disclosure ingest --companies configs/pilot_companies.json --output data/processed/pilot

pilot-audit: sync
	$(UV) run --locked --no-sync disclosure audit --filings data/processed/pilot/filings.parquet --output outputs/audit-pilot
