# Technology choices

The study uses Python for ingestion, parsing, features, evaluation and figures.
SQL runs through DuckDB over local Parquet files. Research logic belongs in
`src/disclosure_research/`; notebooks are for exploration only.

These implementation choices do not change the frozen statistical protocol.

| Layer | Decision | State |
|---|---|---|
| Python | Python 3.12 for the verified environment; exact dependencies in `uv.lock` | Implemented |
| Storage and SQL | Parquet and DuckDB | Implemented |
| Tabular processing | pandas as the single DataFrame library | Implemented |
| EDGAR client | Small synchronous `httpx` client; identifying User-Agent, bounded requests, cache hashes, streaming size limit | Implemented |
| Parsing | lxml and bounded Item 1A heading rules | Implemented; human boundary audit pending |
| Text and primary model | scikit-learn TF-IDF and ridge regression | Implemented |
| Statistics | NumPy for scores and the paired moving-month bootstrap; SciPy is locked through scikit-learn | Implemented |
| Additional statistical diagnostics | statsmodels only when a specified diagnostic needs it | Deferred |
| Validation | Custom expanding chronological folds with training-label maturity checks | Implemented |
| Reproduction | uv lockfile and Makefile | Implemented for the current engineering milestone |
| Tests and quality | pytest, ruff, Git and GitHub Actions | Implemented |
| Figures and report | Matplotlib and ReportLab; PDF rendering verified with Poppler | Progress-report builder implemented; final empirical report pending |
| Semantic changes | Pinned MiniLM safetensors through transformers; separate ridge secondary | Implemented; actual encoder execution and human example/chronology review pending |
| Optional trees | LightGBM as a separately specified secondary comparison | Deferred; outside the primary ridge comparison |

## Runtime and dependency changes

Keep the verified Python 3.12 runtime for this checkpoint. The package currently
declares Python 3.11-3.13 compatibility, but only 3.12 has been exercised in CI.
Changing the runtime requires a deliberate dependency and verification update.
Do not silently regenerate the lockfile during an experiment.

The Makefile starts with `uv sync --locked`, which fails if the dependency
declarations and lockfile disagree. Subsequent commands use the synchronized
environment without another automatic sync. Optional libraries enter the lockfile
when their actual research stage is implemented. Optional `report` and `semantic`
extras are now locked. ReportLab keeps the report builder inside the Python
environment, avoiding an additional document-build CLI. This implementation
choice does not alter the frozen statistical protocol.

HTTPX includes its SOCKS extra so configured proxy environments work without an
untracked installation. The transport honors the environment's proxy settings.

## What one command currently reproduces

```bash
make reproduce-full
```

This synchronizes the environment, runs lint and the research-integrity tests,
verifies the protocol fingerprint, prints the outstanding research gates, and
rebuilds the original demos and the full **synthetic** study: 192 selected annual
memberships, 144 development observations and 48 final observations. GitHub
Actions runs the same command. It does not download SEC documents, access a
WRDS account, open the empirical final holdout, or produce a market finding.

After setting `SEC_USER_AGENT`, use `make ingest` for the development-year SEC
sample. Actual study reproduction will additionally require the audited source
snapshots, dated security links, historical universe, normalized returns and final
report pipeline described in the protocol and market-data contract.

## Statistical details to keep precise

- Bootstrap **reference-month blocks**, not independent filing weeks. Keep all
  issuers and both models' errors together; use three-month blocks as primary and
  six months as the declared sensitivity.
- Each annual expanding training set uses only earlier events whose 20-session
  labels have matured before that year's first prediction. Fit TF-IDF, imputation,
  scaling and industry encoding on those training observations only.
- Keep 2022-2025 out of development and require an audited checkpoint, training
  cutoff and chunking specification before unlocking the embedding comparison.
- Test CPU runtime on a small text sample before selecting an embedding model.
  Model training chronology remains a separate requirement from speed.

## Implementation references

- [Python version status](https://devguide.python.org/versions/)
- [HTTPX streaming, headers, status errors and timeouts](https://www.python-httpx.org/quickstart/)
- [uv locking and syncing](https://docs.astral.sh/uv/concepts/projects/sync/)
- [ReportLab documentation](https://docs.reportlab.com/)
