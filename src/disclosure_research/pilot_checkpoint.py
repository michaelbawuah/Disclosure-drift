"""Rebuild the public text-only pilot checkpoint without opening market outcomes."""

import hashlib
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.api.types import is_bool_dtype

from .extraction import TOKEN
from .features import FEATURE_NAMES, TextChangeFeatures
from .market_data import sha256, strings
from .modeling import NUMERIC_CONTROLS, pipeline, validate_dataset
from .protocol import canonical_hash, eligible_training, guard_development


def describe_pairs(pairs: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Descriptive changes; each TF-IDF vocabulary uses strictly earlier years."""
    guard_development(pairs, config)
    if pairs.empty or pairs.accession.duplicated().any():
        raise ValueError("Pilot pairs must be nonempty and uniquely identified")
    TextChangeFeatures._validate(pairs)
    years = pd.to_datetime(pairs.acceptance_date).dt.year
    rows = []
    for year in sorted(years.unique()):
        test = pairs.loc[years == year]
        train = pairs.loc[years < year]
        features = TextChangeFeatures(config["tfidf_max_features"])
        transformed = features.fit(train).transform(test) if len(train) else None
        for index, pair in test.iterrows():
            old, new = TOKEN.findall(pair.previous_text.lower()), TOKEN.findall(pair.current_text.lower())
            a, b = set(old), set(new)
            rows.append({"observation_id": pair.accession, "cik": pair.cik, "year": int(year),
                         "previous_tokens": len(old), "current_tokens": len(new),
                         "log_length_change": float(np.log1p(len(new)) - np.log1p(len(old))),
                         "jaccard_distance": 1 - len(a & b) / len(a | b),
                         "tfidf_cosine_distance": (float(transformed.loc[index, "tfidf_cosine_distance"])
                                                   if transformed is not None else np.nan),
                         "vocabulary_training_pairs": len(train),
                         "source_url": pair.source_url,
                         "previous_source_url": pair.previous_source_url})
    return pd.DataFrame(rows).sort_values(["year", "observation_id"]).reset_index(drop=True)


def _pilot_evidence(raw: bytes, audit: dict, pairs: pd.DataFrame, filings: pd.DataFrame) -> dict:
    """Derive audit claims from the exact evidence rows bound to the source audit."""
    if sha256(raw) != audit.get("evidence_table_sha256"):
        raise ValueError("Pilot filing evidence lacks a matching source-audit fingerprint")
    flags = ["automated_evidence_ok", "human_review_complete", "assistant_review_complete",
             "verified_source", "verified_header", "verified_risk_source"]
    columns = ["accession", "cik", "risk_text_sha256", "source_url", "acceptance_timestamp",
               "blocking_issues", "cautions", "resolution_method", *flags]
    evidence = pd.read_parquet(io.BytesIO(raw), columns=columns)
    strings(evidence.accession, "filing_evidence.accession")
    strings(evidence.cik, "filing_evidence.cik")
    if (evidence.empty or evidence.accession.duplicated().any() or filings.accessionNumber.duplicated().any()
            or set(evidence.accession) != set(filings.accessionNumber)):
        raise ValueError("Pilot filing evidence must match unique original source accessions exactly")
    for name in flags:
        if not is_bool_dtype(evidence[name]) or evidence[name].isna().any():
            raise ValueError(f"Filing audit {name} requires explicit boolean values")
    for name in ("blocking_issues", "cautions"):
        if not evidence[name].map(lambda value: isinstance(value, (list, tuple, np.ndarray))).all():
            raise ValueError("Filing audit issues and cautions require explicit lists")
    blocked = evidence.blocking_issues.map(len).gt(0)
    counts = {"filings": len(evidence), "issuers": int(evidence.cik.nunique()), "annual_pairs": len(pairs),
              "automated_evidence_ok": int(evidence.automated_evidence_ok.sum()),
              "filings_with_blocking_issues": int(blocked.sum()),
              "human_reviews_complete": int(evidence.human_review_complete.sum()),
              "assistant_reviews_complete": int(evidence.assistant_review_complete.sum()),
              "timestamp_disagreements": int(evidence.cautions.map(
                  lambda values: "api_header_timestamp_disagreement" in values).sum()),
              "reference_resolutions": int(evidence.resolution_method.ne("numbered_item1a").sum())}
    for name, value in counts.items():
        if audit.get(name) != value or isinstance(audit.get(name), bool):
            raise ValueError(f"Pilot source-audit summary differs from evidence rows: {name}")
    if (blocked.any() or not evidence.automated_evidence_ok.all() or
            not evidence[["verified_source", "verified_header", "verified_risk_source"]].all().all()):
        raise ValueError("Pilot source evidence has blocking or unverified filings")
    indexed = evidence.set_index("accession")
    for pair in pairs.itertuples():
        for accession, text, url in [(pair.accession, pair.current_text, pair.source_url),
                                     (pair.previous_accession, pair.previous_text, pair.previous_source_url)]:
            row = indexed.loc[accession]
            if row.cik != pair.cik or row.risk_text_sha256 != sha256(text.encode()) or row.source_url != url:
                raise ValueError("Pilot pair identity, text or source differs from its filing evidence")
        accepted = pd.Timestamp(indexed.loc[pair.accession, "acceptance_timestamp"])
        if accepted.tzinfo is None or accepted.tz_convert("America/New_York").date().isoformat() != pair.acceptance_date:
            raise ValueError("Pilot pair acceptance differs from its filing evidence")
    return counts


def build_pilot_checkpoint(pairs_path, filings_path, audit_path, output, config) -> dict:
    """Publish SEC-derived counts/features only; this does not certify M5 or M6."""
    out = Path(output)
    if out.exists():
        raise ValueError("Output exists; preserve the prior pilot checkpoint")
    pair_raw, filing_raw = Path(pairs_path).read_bytes(), Path(filings_path).read_bytes()
    audit_raw = (Path(audit_path) / "audit_summary.json").read_bytes()
    audit = json.loads(audit_raw)
    if (audit.get("pair_table_sha256") != sha256(pair_raw)
            or audit.get("source_table_sha256") != sha256(filing_raw)
            or audit.get("filings_with_blocking_issues") != 0):
        raise ValueError("Pilot tables lack a matching successful source audit")
    # Check the date column before loading any text. No market table is accepted here.
    dates = pd.read_parquet(io.BytesIO(pair_raw), columns=["acceptance_date"])
    guard_development(dates, config)
    pairs = pd.read_parquet(io.BytesIO(pair_raw), columns=[
        "accession", "previous_accession", "cik", "acceptance_date",
        "previous_text", "current_text", "source_url", "previous_source_url",
    ])
    filings = pd.read_parquet(io.BytesIO(filing_raw), columns=["accessionNumber"])
    if not set(pairs.accession).union(pairs.previous_accession).issubset(set(filings.accessionNumber)):
        raise ValueError("Pilot pair contains an unknown original filing")
    evidence_raw = (Path(audit_path) / "filing_evidence.parquet").read_bytes()
    audit_counts = _pilot_evidence(evidence_raw, audit, pairs, filings)
    features = describe_pairs(pairs, config)
    coverage = features.groupby("year").agg(pairs=("observation_id", "size"), issuers=("cik", "nunique"))
    summaries = {}
    for column in ["previous_tokens", "current_tokens"] + FEATURE_NAMES:
        values = features[column].dropna()
        summaries[column] = {"observations": len(values), "missing": int(features[column].isna().sum()),
                             "minimum": float(values.min()) if len(values) else None,
                             "median": float(values.median()) if len(values) else None,
                             "p10": float(values.quantile(.1)) if len(values) else None,
                             "p90": float(values.quantile(.9)) if len(values) else None,
                             "maximum": float(values.max()) if len(values) else None}
    # Outcome-free example selection. Only links and short section openings are public.
    examples = []
    for year, group in pairs.assign(year=pd.to_datetime(pairs.acceptance_date).dt.year).groupby("year"):
        index = min(group.index, key=lambda i: hashlib.sha256(
            f'{config["seed"]}:{pairs.loc[i, "accession"]}'.encode()).hexdigest())
        pair = pairs.loc[index]
        examples.append({"year": int(year), "accession": pair.accession, "source_url": pair.source_url,
                         "opening_12_words": " ".join(pair.current_text.split()[:12]),
                         "selection": "smallest SHA256(seed:accession) within acceptance year"})
    receipt = {"schema_version": 1, "data_kind": "REAL_SEC_TEXT_DESCRIPTIVE_PILOT",
               "protocol_sha256": canonical_hash(config), "filings": len(filings), "pairs": len(pairs),
               "issuers": int(pairs.cik.nunique()), "year_coverage": coverage.reset_index().to_dict("records"),
               "pilot_2019_2021_pairs": int(features.year.between(2019, 2021).sum()),
               "feature_summaries": summaries, "timestamp_disagreements": audit_counts["timestamp_disagreements"],
               "source_audit_passes": audit_counts["automated_evidence_ok"],
               "human_filing_reviews": audit_counts["human_reviews_complete"],
               "reference_resolutions": audit_counts["reference_resolutions"],
               "vocabulary_policy": "strictly earlier acceptance years; first year TF-IDF unavailable",
               "returns_read": False, "predictive_performance_claim": False,
               "controls_baseline_smoke": "blocked_until_audited_model_dataset",
               "milestone_06_complete": False,
               "sources": {"filings": sha256(filing_raw), "pairs": sha256(pair_raw),
                           "audit": sha256(audit_raw), "filing_evidence": sha256(evidence_raw)},
               "limitations": ["Purposive parser sample is not the historical investment universe",
                               "Pilot coverage is reported by acceptance year; it is not the planned full study",
                               "filing and market source reviews remain pending",
                               "text distributions are descriptive, not predictive evidence"]}
    out.mkdir(parents=True)
    features.to_csv(out / "text_features.csv", index=False)
    coverage.to_csv(out / "coverage_by_year.csv")
    (out / "examples.json").write_text(json.dumps(examples, indent=2) + "\n")
    receipt["files"] = {p.name: sha256(p.read_bytes()) for p in sorted(out.iterdir())}
    (out / "pilot_checkpoint.json").write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n")
    return receipt


def pilot_baseline(frame: pd.DataFrame, config: dict, *, evidence: dict) -> tuple[pd.DataFrame, dict]:
    """Fixed-alpha 2019 -> 2020/2021 controls smoke; never a performance estimate."""
    if evidence.get("model_ready") is not True:
        raise ValueError("Pilot baseline requires a verified, model-ready dataset receipt")
    guard_development(frame, config)
    validate_dataset(frame)
    years = pd.to_datetime(frame.acceptance_date).dt.year
    if not set(years).issubset({2019, 2020, 2021}) or set(years) != {2019, 2020, 2021}:
        raise ValueError("Pilot baseline requires exactly acceptance years 2019-2021")
    outputs = []
    for year in [2020, 2021]:
        test = frame.loc[years == year]
        train = eligible_training(frame, year, str(test.reference_session.min()))
        if len(train) < 10:
            raise ValueError("Insufficient matured pilot training observations")
        model = pipeline(alpha=1.0, text=False)
        columns = NUMERIC_CONTROLS + ["industry"]
        model.fit(train[columns], train.target)
        pred = model.predict(test[columns])
        for identifier, target, value in zip(test.observation_id, test.target, pred, strict=True):
            outputs.append({"observation_id": identifier, "year": year,
                            "target": float(target), "prediction": float(value), "train_rows": len(train)})
    result = pd.DataFrame(outputs)
    return result, {"status": "controls_only_pipeline_smoke", "alpha": 1.0,
                    "alpha_selection": "fixed_before_smoke_no_tuning", "predictions": len(result),
                    "data_kind": evidence["data_kind"], "predictive_performance_claim": False}
