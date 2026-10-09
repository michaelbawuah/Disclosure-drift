"""Validate an explicitly normalized, development-only market-data bundle.

This is not a vendor adapter. Provenance declarations are recorded, not certified.
"""

import hashlib
import io
import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype

from .timing import NY, calendar, event_window

SCHEMAS = {
    "daily_returns": ["security_id", "session", "total_return", "terminal_event"],
    "market_returns": ["session", "total_return"],
    "security_links": ["cik", "security_id", "valid_from", "valid_to",
                       "mapping_source", "class_selection_rule"],
}
SYNTHETIC = "SYNTHETIC_ENGINEERING_FIXTURE"
NORMALIZED = "NORMALIZED_MARKET_DATA"


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def fingerprint(value: dict) -> str:
    return sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode())


def required_text(value, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be an explicit nonempty string")


def strings(series: pd.Series, label: str) -> None:
    if not series.map(lambda x: isinstance(x, str) and bool(x.strip())).all():
        raise ValueError(f"{label} must contain nonempty strings; identifiers are never coerced")


def iso_dates(series: pd.Series, label: str, sessions: bool = False) -> None:
    strings(series, label)
    if not series.str.fullmatch(r"\d{4}-\d{2}-\d{2}").all():
        raise ValueError(f"{label} requires ISO dates without time or timezone")
    pd.to_datetime(series, format="%Y-%m-%d", errors="raise")
    if sessions:
        valid = set(calendar().sessions.strftime("%Y-%m-%d"))
        if not series.isin(valid).all():
            raise ValueError(f"{label} contains a non-XNYS session or is outside calendar coverage")


def development_return_end(config: dict) -> str:
    """Late-2021 filings may legitimately need early-2022 label returns."""
    accepted = datetime(config["development_end"], 12, 31, 23, 59, tzinfo=NY)
    return event_window(accepted, config["reference_session_offset"],
                        config["horizon_sessions"]).label_end


def validate_tables(tables: dict[str, pd.DataFrame], config: dict) -> dict:
    if set(tables) != set(SCHEMAS):
        raise ValueError("Supply exactly daily_returns, market_returns and security_links")
    coverage = {}
    for name, columns in SCHEMAS.items():
        frame = tables[name]
        if frame.empty or set(columns) - set(frame.columns):
            raise ValueError(f"{name} is empty or missing required columns: {columns}")
        if frame[columns].isna().any().any():
            raise ValueError(f"{name} has missing required values; missing is not zero")
        if "security_id" in frame:
            strings(frame.security_id, f"{name}.security_id")
        coverage[name] = {"rows": len(frame)}
        if name == "security_links":
            continue
        iso_dates(frame.session, f"{name}.session", sessions=True)
        if frame.session.max() > development_return_end(config):
            raise ValueError("Return data extend beyond the development label window; holdout blocked")
        values = frame.total_return
        if (not is_numeric_dtype(values) or is_bool_dtype(values) or
                not np.isfinite(values.to_numpy(dtype=float)).all() or (values < -1).any()):
            raise ValueError(f"{name}.total_return must be numeric, finite and at least -1")
        keys = ["security_id", "session"] if name == "daily_returns" else ["session"]
        if frame.duplicated(keys).any():
            raise ValueError(f"{name} has duplicate return keys")
        coverage[name].update(first_session=frame.session.min(), last_session=frame.session.max())

    stock = tables["daily_returns"]
    if not is_bool_dtype(stock.terminal_event):
        raise ValueError("terminal_event must be a boolean column, not flags or strings")
    for security_id, group in stock.groupby("security_id", sort=False):
        terminal = group.loc[group.terminal_event, "session"]
        if len(terminal) > 1 or (len(terminal) and group.session.max() > terminal.iloc[0]):
            raise ValueError(f"Multiple terminal events or post-terminal records: {security_id}")

    links = tables["security_links"]
    strings(links.cik, "security_links.cik")
    if not links.cik.str.fullmatch(r"\d{10}").all() or (links.cik == "0000000000").any():
        raise ValueError("CIK must be a nonzero, zero-padded 10-digit string")
    for column in ["mapping_source", "class_selection_rule"]:
        strings(links[column], f"security_links.{column}")
    for column in ["valid_from", "valid_to"]:
        iso_dates(links[column], f"security_links.{column}")
    if (links.valid_from > links.valid_to).any():
        raise ValueError("Historical links have reversed validity dates")
    # Input links must already select one eligible share class at each date.
    # Reject duplicate/overlapping intervals even if both rows name the same ID.
    for key in ["cik", "security_id"]:
        for _, group in links.sort_values("valid_from").groupby(key, sort=False):
            prior_end = None
            for row in group.itertuples():
                if prior_end is not None and row.valid_from <= prior_end:
                    raise ValueError(f"Overlapping historical links by {key}; resolve class/issuer identity")
                prior_end = row.valid_to
    coverage["daily_returns"]["securities"] = int(stock.security_id.nunique())
    coverage["security_links"]["issuers"] = int(links.cik.nunique())
    return coverage


def validate_manifest(manifest: dict) -> None:
    if manifest.get("schema_version") != 1 or manifest.get("data_kind") not in {SYNTHETIC, NORMALIZED}:
        raise ValueError("Unknown manifest version or data kind")
    for key in ["provider", "dataset", "release", "exported_at", "source_documentation",
                "normalization_notes"]:
        required_text(manifest.get(key), key)
    stamp = datetime.fromisoformat(manifest["exported_at"].replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("exported_at requires a timezone")
    if manifest.get("stock_return_convention") != "dividends_and_delisting_exactly_once":
        raise ValueError("Declare verified dividends/delisting handling before import")
    if manifest.get("benchmark_convention") != "value_weighted_total_return":
        raise ValueError("Declare a value-weighted total-return benchmark")
    required_text(manifest.get("benchmark_description"), "benchmark_description")
    if not re.fullmatch(r"[0-9a-f]{64}", manifest.get("normalization_code_sha256", "")):
        raise ValueError("Record the normalization code SHA-256")
    exports = manifest.get("raw_exports")
    if not isinstance(exports, list) or not exports:
        raise ValueError("Record raw export identifiers and SHA-256 hashes")
    for export in exports:
        required_text(export.get("source_table"), "raw export source_table")
        if not re.fullmatch(r"[0-9a-f]{64}", export.get("sha256", "")):
            raise ValueError("Invalid raw export SHA-256")
    if set(manifest.get("tables", {})) != set(SCHEMAS):
        raise ValueError("Manifest must describe all three normalized tables")
    for name, columns in SCHEMAS.items():
        spec = manifest["tables"][name]
        required_text(spec.get("path"), f"{name}.path")
        if not re.fullmatch(r"[0-9a-f]{64}", spec.get("sha256", "")):
            raise ValueError(f"Missing or invalid {name} SHA-256")
        if set(spec.get("field_mapping", {})) != set(columns):
            raise ValueError(f"Record a source field or derivation for every {name} column")
        for value in spec["field_mapping"].values():
            required_text(value, f"{name} field mapping")


def import_market(manifest_path: str | Path, output: str | Path, config: dict) -> dict:
    """Validate all inputs before atomically publishing a new local bundle."""
    path, output = Path(manifest_path), Path(output)
    if output.exists():
        raise ValueError("Output already exists; choose a new import directory to preserve provenance")
    manifest_bytes = path.read_bytes()
    manifest = json.loads(manifest_bytes)
    validate_manifest(manifest)
    tables, bodies = {}, {}
    for name, spec in manifest["tables"].items():
        relative = Path(spec["path"])
        source = (path.parent / relative).resolve()
        if relative.is_absolute() or not source.is_relative_to(path.parent.resolve()):
            raise ValueError("Table paths must stay inside the manifest directory")
        raw = source.read_bytes()
        if sha256(raw) != spec["sha256"]:
            raise ValueError(f"Input hash mismatch: {name}")
        if name != "security_links":
            # Check dates before loading return values; never silently trim holdout rows.
            dates = pd.read_parquet(io.BytesIO(raw), columns=["session"]).session
            iso_dates(dates, f"{name}.session", sessions=True)
            if len(dates) and dates.max() > development_return_end(config):
                raise ValueError("Return data extend beyond the development label window; holdout blocked")
        bodies[name], tables[name] = raw, pd.read_parquet(io.BytesIO(raw))
    coverage = validate_tables(tables, config)
    receipt = {"schema_version": 1, "data_kind": manifest["data_kind"],
               "created_at": datetime.now(timezone.utc).isoformat(),
               "source_manifest_sha256": sha256(manifest_bytes), "coverage": coverage,
               "development_end": config["development_end"],
               "last_permitted_return_session": development_return_end(config),
               "table_sha256": {name: sha256(raw) for name, raw in bodies.items()},
               "provenance_status": "recorded declarations; vendor mapping and entitlements not independently verified",
               "research_status": "engineering staging only; universe and human audits still required"}
    receipt["bundle_id"] = fingerprint(receipt)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".market-import-", dir=output.parent) as temp:
        stage = Path(temp) / "bundle"
        stage.mkdir()
        (stage / "source_manifest.json").write_bytes(manifest_bytes)
        for name, raw in bodies.items():
            (stage / f"{name}.parquet").write_bytes(raw)
        with duckdb.connect(str(stage / "market.duckdb")) as con:
            for name, frame in tables.items():
                con.register("input_frame", frame)
                con.execute(f"CREATE TABLE {name} AS SELECT * FROM input_frame")
        (stage / "import_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        stage.rename(output)
    return receipt


def load_market(bundle: str | Path, config: dict) -> tuple[dict, dict]:
    bundle = Path(bundle)
    receipt = json.loads((bundle / "import_receipt.json").read_text())
    signed = {k: v for k, v in receipt.items() if k != "bundle_id"}
    if receipt.get("bundle_id") != fingerprint(signed):
        raise ValueError("Import receipt changed")
    raw_manifest = (bundle / "source_manifest.json").read_bytes()
    if sha256(raw_manifest) != receipt["source_manifest_sha256"]:
        raise ValueError("Source manifest changed")
    manifest = json.loads(raw_manifest)
    validate_manifest(manifest)
    if (receipt["development_end"] != config["development_end"] or
            receipt["last_permitted_return_session"] != development_return_end(config) or
            receipt["data_kind"] != manifest["data_kind"]):
        raise ValueError("Bundle research period or data kind changed")
    tables = {}
    for name in SCHEMAS:
        raw = (bundle / f"{name}.parquet").read_bytes()
        if sha256(raw) != receipt["table_sha256"][name] or sha256(raw) != manifest["tables"][name]["sha256"]:
            raise ValueError(f"Imported table changed: {name}")
        tables[name] = pd.read_parquet(io.BytesIO(raw))
    validate_tables(tables, config)
    return tables, receipt
