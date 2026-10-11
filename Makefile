UV ?= uv
RUN_ID := $(shell date -u +%Y%m%dT%H%M%SZ)
FULL_OUTPUT ?= outputs/full-demo-$(RUN_ID)
CHECKPOINT_OUTPUT ?= outputs/pilot-checkpoint-$(RUN_ID)
EXPANDED_CHECKPOINT_OUTPUT ?= outputs/pilot-expanded-checkpoint-$(RUN_ID)
REPORT_OUTPUT ?= outputs/research-report-$(RUN_ID)
.DEFAULT_GOAL := help

.PHONY: help sync check status demo market-demo reproduce reproduce-full full-demo pilot-checkpoint pilot-expand research-report ingest audit pilot-ingest pilot-audit reference-reproduce pilot-resolved-reproduce

help:
	@printf '%s\n' \
	  'make reproduce  Sync the lockfile, lint, test, verify protocol, run the synthetic demo' \
	  'make reproduce-full  Verify all code and the complete synthetic study pipeline' \
	  'make full-demo  Historical selection, frozen evaluation and robustness on invented inputs' \
	  'make pilot-checkpoint  Rebuild SEC-only descriptive pilot exhibits from restored evidence' \
	  'make pilot-expand  Collect 15 additional issuers and audit the combined SEC text pilot' \
	  'make research-report  Build progress PDFs and figures from public pilot exhibits' \
	  'make check      Sync the lockfile, then run lint and tests' \
	  'make status     Show the published progress checklist, not local bundle validation' \
	  'make demo       Rebuild the synthetic engineering demonstration' \
	  'make market-demo  Verify invented market imports, delisting labels and missing-data exclusions' \
	  'make ingest     Download/cache the SEC sample; requires SEC_USER_AGENT' \
	  'make audit      Build the offline audit packet for the five-issuer sample' \
	  'make pilot-ingest  Download/cache the 20-issuer development pilot' \
	  'make pilot-audit   Build the expanded pilot audit packet' \
	  'make reference-reproduce  Rebuild and compare the 24-filing reference-resolution pilot' \
	  'make pilot-resolved-reproduce  Rebuild and verify the complete 155-filing pilot with reference rules'

sync:
	$(UV) sync --locked

check: sync
	$(UV) run --locked --no-sync ruff check .
	$(UV) run --locked --no-sync pytest

status: sync
	$(UV) run --locked --no-sync disclosure status

demo: sync
	$(UV) run --locked --no-sync disclosure demo

market-demo: sync
	$(UV) run --locked --no-sync disclosure market-demo

reproduce: check
	$(UV) run --locked --no-sync disclosure status
	$(UV) run --locked --no-sync disclosure demo
	$(UV) run --locked --no-sync disclosure market-demo

full-demo: sync
	$(UV) run --locked --no-sync disclosure full-demo --output "$(FULL_OUTPUT)"

reproduce-full: reproduce
	$(UV) run --locked --no-sync disclosure full-demo --output "$(FULL_OUTPUT)"

pilot-checkpoint: sync
	$(UV) run --locked --no-sync disclosure pilot-checkpoint --output "$(CHECKPOINT_OUTPUT)"

pilot-expand: sync
	$(UV) run --locked --no-sync disclosure ingest --companies configs/pilot_expansion_2019_2021.json --resolutions configs/pilot_expansion_resolutions.json --output data/processed/pilot-expansion-2019-2021-resolved
	$(UV) run --locked --no-sync python scripts/build_pilot_expansion.py --output "$(EXPANDED_CHECKPOINT_OUTPUT)"

research-report:
	$(UV) run --locked --extra report disclosure research-report --output "$(REPORT_OUTPUT)"

ingest: sync
	$(UV) run --locked --no-sync disclosure ingest

audit: sync
	$(UV) run --locked --no-sync disclosure audit

pilot-ingest: sync
	$(UV) run --locked --no-sync disclosure ingest --companies configs/pilot_companies.json --output data/processed/pilot

pilot-audit: sync
	$(UV) run --locked --no-sync disclosure audit --filings data/processed/pilot/filings.parquet --output outputs/audit-pilot

reference-reproduce: sync
	$(UV) run --locked --no-sync disclosure ingest --companies configs/reference_companies.json --no-resolutions --output data/processed/references-baseline
	$(UV) run --locked --no-sync disclosure ingest --companies configs/reference_companies.json --output data/processed/references
	$(UV) run --locked --no-sync disclosure audit --filings data/processed/references/filings.parquet --output outputs/audit-references
	$(UV) run --locked --no-sync python scripts/verify_reference_pilot.py

pilot-resolved-reproduce: sync
	$(UV) run --locked --no-sync disclosure ingest --companies configs/pilot_companies.json --output data/processed/pilot-resolved
	$(UV) run --locked --no-sync disclosure audit --filings data/processed/pilot-resolved/filings.parquet --output outputs/audit-pilot-resolved
	$(UV) run --locked --no-sync python scripts/verify_expanded_pilot.py
