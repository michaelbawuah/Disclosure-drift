# Secondary robustness components

The functions in `src/disclosure_research/robustness.py` implement the declared
secondary analyses. They do not change `configs/protocol.json`, select a new
primary model, grant final-data access, or establish that private source audits
have occurred. Final-period data must enter through the frozen final workflow.
All executable examples in tests use invented data.

## Run a saved primary result through the secondary reports

`robustness_run.run_robustness(final_run, freeze, output, config, repo_root='.')`
accepts the completed primary result directory, matching freeze directory/file,
and a new output directory. The corresponding shared loader
`load_authorized_final` returns verified saved predictions, the freeze and its
final summary for another explicitly frozen secondary comparison.

The runner verifies the persistent study ledger, access reservation and completion
receipt, final summary and output hashes, code and protocol freeze, source-bound
reviews and exact event clocks before decoding saved final predictions. The
original final target table is fingerprinted but **never deserialized**. It does
not grant new access or run a new development hyperparameter search. Synthetic
receipts remain synthetic throughout.

Outputs include `diagnostics.json`, `subgroups.json`, `failure_cases.json`,
`ablations.json`, and a hash-bound `robustness_summary.json`. When ablations are
available, `ablation_predictions.parquet` retains all six comparisons. Missing
methods or evidence remain unavailable with explicit reasons; independent delay,
semantic and manual descriptive work is not silently marked complete.

Before the original final freeze, the secondary specification must record:

- `subgroups.size_cutpoints_usd`, `subgroups.industry_scheme`, and
  `subgroups.selection = fixed_before_final_access`.
- `ablations.selection_artifact` containing the path and SHA-256 of the selection
  returned by `development_ablations`, alongside `selected_alphas` and the declared
  feature map, grid and pooled-development metric. That artifact must also appear
  in the freeze's resolved evidence references. The ablation choices are required
  to match both the frozen specification and the prepared development data.

An absent ablation artifact does not trigger selection after final access. Editing
one after freezing is an integrity failure. The prior final result and all earlier
secondary reports remain unchanged.

## Scores and sample stability

`prediction_diagnostics(predictions, config)` expects one row per observation with
`observation_id`, acceptance `year`, `reference_session`, `target`,
`baseline_prediction` and `text_prediction`.

It reports pooled and annual paired errors, reference-month Spearman correlations,
leave-one-year-out scores, and the frozen three- and six-month bootstrap intervals.
Year omission removes one acceptance year from the **same frozen predictions**;
it does not train on future years. Rank correlations use average ranks for ties.
Groups with fewer than three observations, constant targets or constant predictions
remain explicit with unavailable values and reasons. A zero baseline SSE produces
an undefined incremental score, never a made-up zero. Insufficient time coverage
does not shorten the prespecified bootstrap blocks.

`subgroup_diagnostics` requires exact observation-matched covariates: prior-close
`controls_asof`, `log_market_cap`, dated `industry` and `industry_scheme`. Pass
absolute `size_cutpoints_usd` and an `industry_scheme` frozen before final access.
The function does not derive size ranks or thresholds from final outcomes or use
current issuer-header industry. Empty size groups and all group counts are retained.
Tiny subgroups support descriptive inspection, not reliable statistical conclusions.

`failure_cases` links the largest text-minus-baseline squared errors to current and
previous filing URLs. These examples are explicitly selected using outcomes after
a frozen run. They are interpretation aids, not representative parser-error rates
or grounds to remove observations retrospectively. Restricted outcome-derived
values must remain private unless redistribution rights permit publication.

## Text ablations and the length-only baseline

`development_ablations(frame, config)` fits all six nonempty proper subsets of the
three text features: each individual feature and each two-feature combination.
The naive length-only comparison is included. Each subset selects its own ridge
penalty using pooled 2016–2021 development MSE over the same four-value grid, with
ties favoring the smaller penalty. This adds 24 secondary configurations; it does
not alter the eight primary baseline/augmented configurations.

All vocabulary, imputation, scaling and industry encoding are training-only.
Training labels must mature before the first prediction of each evaluation year.
The returned selection records the protocol, feature subsets, data/prediction
fingerprints, selected penalties and its own fingerprint. Bind that selection into
the final freeze manifest before accessing final outcomes.

`evaluate_ablations` is a low-level component for the already validated final-run
context. It verifies the selection and performs annual fits without retuning.
`compare_ablation_predictions` requires every ablation to contain exactly the
primary baseline observations, outcomes and event clocks. It reports all six
comparisons; choosing the best final subset would be a new exploratory analysis.

## Reference delays

Changing a date on existing predictions is not a delay sensitivity. Use
`rebuild_delay_dataset` separately for delays **1, 2 and 5 sessions**. It recalculates
the entire 20-session label and 60-session control history from normalized source
returns and dated snapshots, preserving the approved security selected upstream.
No original target, control value or source-session claim is reused.

Each delay needs explicit availability rows keyed by `observation_id` and `delay`:

| Field | Meaning |
|---|---|
| `availability_status` | `verified` or `documented_assumption` |
| `public_available_at` | Timezone-aware actual or documented conservative availability bound |
| `availability_evidence_id` | Reference to the supporting evidence or reviewed assumption |

The bound must be at or after original filing acceptance and strictly before that
delay's prediction open. A two-session proxy with no bound cannot establish
availability for a one-session forecast. Documented assumptions are counted
separately and never represented as verified dissemination. Missing evidence,
returns or snapshots produce explicit exclusions, not filling or silent omission.

The returned receipt binds the source tables, rebuilt dataset, exclusions, exact
delay and availability counts. `validate_delay_dataset` rejects changed receipts,
tables and event clocks. Fingerprints are change detectors, not signatures or proof
of source correctness. The caller still supplies audited universe, identity and
source evidence.

Use the **same frozen primary penalties** for all three variants.
`evaluate_delay_predictions` fits the rebuilt data using those supplied penalties
and the same annual mature-label/training-only preprocessing rules. Its caller
must already have passed the final-access gates. Supply the independently fitted
predictions and receipts to `compare_delay_predictions`.
Every included event in each scored year must be present. The report preserves
own-sample results, availability/exclusion counts, and the common-event comparison.
Each delay's target has a different clock, so these are timing sensitivities rather
than three forecasts of one identical return realization.

## Descriptive paragraph audit

`describe_paragraph_changes` returns candidate additions, removals, rewordings and
relocations for manual review. Blank lines delimit paragraphs. Exact matches retain
numbers and punctuation, preserve repeated-paragraph multiplicity, and use relative
order to avoid misclassifying every paragraph shifted by an insertion as moved.
Unmatched paragraphs become rewording candidates only when they are unique mutual
best token-set matches above the fixed Jaccard threshold (default 0.5). Ties remain
unmatched. Split/merged paragraphs and formatting changes still require review.

The output creates **no forecast features** and always retains a pending manual
review status. Its matching threshold is a descriptive aid; predictive construction
would require an additional frozen specification before final access. The 2020
disclosure-rule transition also remains a descriptive audit unless an exact,
development-justified exclusion sensitivity is frozen separately.
