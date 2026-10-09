# Publication provenance

The source was developed locally in five ordered commits and published through the
connected GitHub app. The command-line environment did not have a GitHub login,
so these snapshots were replayed through the GitHub API. Published commit IDs and
commit metadata differ from the original local commits.

The original history, including author metadata and the protocol and milestone
tags, is retained in [original-history.bundle](../provenance/original-history.bundle).
The bundle contains code and research documentation, not raw SEC bodies or market data.

## Restore the original history

Run from the root of this repository:

```bash
git bundle verify provenance/original-history.bundle
git clone provenance/original-history.bundle ../disclosure-original-history
```

The restored repository is a separate copy of the original development history.
Continue normal development on this repository's `main` branch.

## Original commits

| Commit | Change |
|---|---|
| `aeeaa9a41194d9947ecfde9b692125ef09ac08e0` | docs: freeze the disclosure research protocol |
| `9bfd0385a8a564a3ce76295a846af8cbe43503d1` | feat: build SEC ingestion and chronological research components |
| `dbc8fdf9121d6d996a1287ac17c4f38eef44366e` | fix: preserve timestamp discrepancies and undefined text distances |
| `3c90d9192b7e1717172ae3a748334d5791e8737f` | test: verify research integrity and document the live filing milestone |
| `09e8ffdf689b192a90d92b65e5a99fc98522836b` | docs: prepare Disclosure Drift for GitHub publication |

The original code and protocol were co-developed with Codex. Publication is not
evidence that manual filing audits or empirical market-return evaluation are complete.
