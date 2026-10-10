"""Private, resumable WRDS source collection; no credentials or research approval.

The caller supplies an authenticated PyWRDS-compatible connection. Every source
field is checked against its catalog before a value query. Exports preserve
source strings and contain no normalized availability or identity assertions.
"""

import hashlib
import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .market_data import development_return_end, fingerprint, iso_dates, sha256
from .protocol import canonical_hash
from .timing import NY, calendar, event_window
from .universe import year_start_window

SOURCE_FIELDS = {
    "daily": "permno hdrcusip ticker permco dlycaldt dlydelflg dlycap dlyret dlyretmissflg dlyprc dlyvol dlyprcflg".split(),
    "names": "permno hdrprimaryexch nasdissuno hdrsiccd permco secinfostartdt secinfoenddt securitybegdt securityenddt cusip ticker issuernm shareclass usincflg issuertype securitytype securitysubtype sharetype securityactiveflg siccd primaryexch tradingsymbol naics tradingstatusflg".split(),
    "links": "gvkey liid linkprim linktype lpermno lpermco linkdt linkenddt".split(),
    "company": "gvkey cik conm tic cusip".split(),
    "market": "dlycaldt vwretd".split(),
}
DAILY_OUTPUT = {
    "permno": "PERMNO", "hdrcusip": "HdrCUSIP", "ticker": "Ticker", "permco": "PERMCO",
    "dlycaldt": "DlyCalDt", "dlydelflg": "DlyDelFlg", "dlycap": "DlyCap", "dlyret": "DlyRet",
    "dlyretmissflg": "DlyRetMissFlg", "dlyprc": "DlyPrc", "dlyvol": "DlyVol", "dlyprcflg": "DlyPrcFlg",
}
LIQUIDITY_FIELDS = "permno dlycaldt dlyprc dlyvol dlyprcflg".split()
RETURN_FIELDS = "permno hdrcusip ticker permco dlycaldt dlydelflg dlycap dlyret dlyretmissflg".split()
PARTITIONS = {"population", "development", "holdout_population", "holdout"}
PLAN_PARTITIONS = PARTITIONS | {"full_population"}
DEFAULT_LIBRARIES = ["crsp_a_stock", "crsp_a_ccm", "crsp", "comp"]
CANDIDATE_TABLES = {
    "daily": {"wrds_dsfv2_query", "dsf_v2", "stkdlysecuritydata"},
    "names": {"wrds_names_query", "stksecurityinfohist"},
    "links": {"ccmxpf_lnkhist"}, "company": {"company"},
    "market": {"wrds_dailyindexret_query", "dsi_v2"},
}
OFFICIAL_SOURCES = [
    "https://github.com/wharton/wrds",
    "https://wrds-www.wharton.upenn.edu/pages/wrds-research/macros/wrds-macro-compound-ciz/",
    "https://wrds-www.wharton.upenn.edu/pages/wrds-research/macros/wrds-macro-ccm/",
    "https://wrds-www.wharton.upenn.edu/pages/wrds-research/macros/wrds-macro-trade_date_windows-ciz/",
]


def _identifier(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", value):
        raise ValueError("WRDS source names must be plain SQL identifiers")
    return '"' + value + '"'


def _source(source: dict) -> str:
    return f'{_identifier(source["library"])}.{_identifier(source["table"])}'


def _private_output(output, repo_root) -> Path:
    out, repo = Path(output).resolve(), Path(repo_root).resolve()
    if out == repo or (out.is_relative_to(repo) and not any(
            out.is_relative_to(repo / folder) for folder in ["data", "outputs"])):
        raise ValueError("Licensed exports inside the repository must stay under ignored data/ or outputs/")
    return out


def _gate(partition: str, config: dict, authorization) -> dict | None:
    if partition not in PARTITIONS:
        raise ValueError("Partition must be population, development, holdout_population or holdout; full_population is plan-only")
    if partition not in {"holdout_population", "holdout"}:
        return None
    if not callable(authorization):
        raise ValueError("Holdout exports require freshly verified development prerequisites")
    receipt = authorization()
    if (not isinstance(receipt, dict) or receipt.get("prerequisites_verified") is not True
            or receipt.get("protocol_sha256") != canonical_hash(config)):
        raise ValueError("Holdout exports remain blocked by development prerequisites")
    return receipt


def _catalog_columns(connection, source: dict) -> dict[str, str]:
    _source(source)
    described = connection.describe_table(library=source["library"], table=source["table"])
    if not isinstance(described, pd.DataFrame) or "name" not in described:
        raise ValueError("WRDS describe_table must return its documented name column")
    names = described["name"].tolist()
    if not all(isinstance(name, str) for name in names) or len({name.lower() for name in names}) != len(names):
        raise ValueError("WRDS source column names are invalid or ambiguous")
    for name in names:
        _identifier(name)
    return {name.lower(): name for name in names}


def discover_wrds_sources(connection, *, libraries=None) -> dict:
    """Inspect metadata only. Candidate tables are suggestions, never entitlements."""
    available = set(connection.list_libraries())
    requested = DEFAULT_LIBRARIES if libraries is None else list(libraries)
    result = {"schema_version": 1, "cataloged_at": datetime.now(timezone.utc).isoformat(),
              "requested_libraries": requested, "available_requested_libraries": [],
              "unavailable_requested_libraries": [], "candidates": {role: [] for role in SOURCE_FIELDS},
              "values_queried": False, "account_credentials_recorded": False}
    for library in requested:
        _identifier(library)
        if library not in available:
            result["unavailable_requested_libraries"].append(library)
            continue
        result["available_requested_libraries"].append(library)
        tables = connection.list_tables(library=library)
        for table in sorted(tables):
            roles = [role for role, candidates in CANDIDATE_TABLES.items() if table.lower() in candidates]
            if not roles:
                continue
            source = {"library": library, "table": table}
            columns = _catalog_columns(connection, source)
            for role in roles:
                result["candidates"][role].append({**source,
                    "observed_columns": sorted(columns.values()),
                    "missing_required_columns": sorted(set(SOURCE_FIELDS[role]) - set(columns)),
                    "source_release": None})
    result["catalog_id"] = fingerprint(result)
    return result


def _validate_bindings(bindings: dict) -> dict:
    if bindings.get("schema_version") != 1 or not isinstance(bindings.get("sources"), dict):
        raise ValueError("Use a version-1 WRDS source-binding file")
    if set(bindings["sources"]) != set(SOURCE_FIELDS):
        raise ValueError("Source bindings must declare daily, names, links, company and market")
    for role, source in bindings["sources"].items():
        if not isinstance(source, dict) or set(source) - {"library", "table", "source_release", "release_evidence"}:
            raise ValueError(f"Unsupported source binding fields: {role}")
        _source(source)
        for field in ["source_release", "release_evidence"]:
            value = source.get(field)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{role}.{field} must be documented text or null")
    return bindings["sources"]


def _sessions(start: str, end: str) -> list[str]:
    return [date for date in calendar().sessions.strftime("%Y-%m-%d") if start <= date <= end]


def _monthly(sessions: list[str]):
    for month in sorted({session[:7] for session in sessions}):
        yield month, [session for session in sessions if session.startswith(month)]


def _population(partition: str) -> bool:
    return partition in {"population", "holdout_population", "full_population"}


def _population_years(config: dict, partition: str) -> range:
    first = config["holdout_start"] if partition == "holdout_population" else config["initial_train_start"]
    last = config["development_end"] if partition == "population" else config["holdout_end"]
    return range(first, last + 1)


def _bounds(config: dict, partition: str) -> tuple[str, str]:
    if _population(partition):
        years = _population_years(config, partition)
        return year_start_window(years.start, config)["liquidity_start"], f'{years.stop - 1}-12-31'
    if partition == "development":
        return year_start_window(config["initial_train_start"], config)["liquidity_start"], development_return_end(config)
    first = year_start_window(config["holdout_start"], config)["liquidity_start"]
    last = event_window(datetime(config["holdout_end"], 12, 31, 23, 59, tzinfo=NY),
                        config["reference_session_offset"], config["horizon_sessions"]).label_end
    return first, last


def plan_wrds_exports(bindings: dict, config: dict, partition="population", *, resolved_columns=None) -> dict:
    """Compile explicit projected queries offline; this function never opens data."""
    if partition not in PLAN_PARTITIONS:
        raise ValueError("Unknown WRDS partition")
    sources = _validate_bindings(bindings)
    columns = resolved_columns or {role: {name: name for name in fields}
                                   for role, fields in SOURCE_FIELDS.items()}
    start, end = _bounds(config, partition)
    jobs = []

    def add(job_id, role, fields, sessions=None):
        source = sources[role]
        output_names = [DAILY_OUTPUT[field] if role == "daily" else field for field in fields]
        selected = [f'CAST(s.{_identifier(columns[role][field])} AS text) AS {_identifier(output)}'
                    for field, output in zip(fields, output_names, strict=True)]
        joined = {}
        if role == "daily" and not _population(partition):
            selected.append(f'CAST(m.{_identifier(columns["market"]["vwretd"])} AS text) AS "vwretd"')
            output_names.append("vwretd")
            joined = {"market": sources["market"]}
        sql = "SELECT " + ",\n       ".join(selected) + f"\nFROM {_source(source)} AS s"
        if joined:
            sql += (f'\nLEFT JOIN {_source(sources["market"])} AS m ON '
                    f's.{_identifier(columns["daily"]["dlycaldt"])} = '
                    f'm.{_identifier(columns["market"]["dlycaldt"])}')
        params = {}
        if sessions is not None:
            params = {f"session_{i}": date for i, date in enumerate(sessions)}
            placeholders = ", ".join(f"%({key})s" for key in params)
            sql += f'\nWHERE s.{_identifier(columns[role]["dlycaldt"])} IN ({placeholders})'
            order = ["dlycaldt"] + (["permno"] if role == "daily" else [])
        elif role == "names":
            left, right = [_identifier(columns[role][field]) for field in ["secinfostartdt", "secinfoenddt"]]
            sql += f"\nWHERE (s.{left} <= %(end)s OR s.{left} IS NULL) AND (s.{right} >= %(start)s OR s.{right} IS NULL)"
            params, order = {"start": start, "end": end}, ["permno", "secinfostartdt", "secinfoenddt"]
        else:
            # Keep all link types, null identifiers, open-bound markers and header
            # histories. Source acquisition makes no historical CIK assignment.
            order = ["gvkey", "lpermno", "linkdt", "linkenddt"] if role == "links" else ["gvkey"]
        sql += "\nORDER BY " + ", ".join(f's.{_identifier(columns[role][field])}' for field in order) + "\n"
        jobs.append({"job_id": job_id, "role": role, "columns": output_names, "sql": sql,
                     "params": params, "expected_sessions": sessions, "source": source,
                     "joined_sources": joined})

    add("names", "names", SOURCE_FIELDS["names"])
    if _population(partition):
        add("ccm-link-history", "links", SOURCE_FIELDS["links"])
        add("company-header-candidates", "company", SOURCE_FIELDS["company"])
        windows = []
        for year in _population_years(config, partition):
            window = year_start_window(year, config)
            windows.append({"universe_year": year, **window})
            for month, sessions in _monthly(list(window["sessions"])):
                add(f"liquidity-{year}-{month}", "daily", LIQUIDITY_FIELDS, sessions)
    else:
        windows = None
        for month, sessions in _monthly(_sessions(start, end)):
            add(f"daily-{month}", "daily", RETURN_FIELDS, sessions)
            # Independent index queries continue even after a selected security
            # delists; the benchmark is never forward-filled from surviving rows.
            add(f"market-{month}", "market", SOURCE_FIELDS["market"], sessions)
    plan = {"schema_version": 1, "partition": partition, "protocol_sha256": canonical_hash(config),
            "bindings_sha256": fingerprint(bindings), "request_start": start, "request_end": end,
            "annual_liquidity_windows": windows, "jobs": jobs,
            "value_queries_performed_to_build_plan": False, "live_catalog_validated": resolved_columns is not None,
            "observed_source_columns": resolved_columns,
            "source_selection": "all securities; no current constituent, ticker, survival or link-type filter",
            "data_kind": "WRDS_RAW_SOURCE_EXPORT_NOT_AUDIT_APPROVED",
            "code_sha256": sha256(Path(__file__).read_bytes())}
    plan["plan_id"] = fingerprint(plan)
    return plan


def _metadata(connection, bindings: dict, partition: str) -> dict:
    sources = _validate_bindings(bindings)
    roles = ["daily", "names", "links", "company"] if _population(partition) else ["daily", "names", "market"]
    required_daily = LIQUIDITY_FIELDS if _population(partition) else RETURN_FIELDS
    resolved = {}
    for role in roles:
        columns = _catalog_columns(connection, sources[role])
        required = required_daily if role == "daily" else SOURCE_FIELDS[role]
        missing = sorted(set(required) - set(columns))
        if missing:
            raise ValueError(f"WRDS {role} source lacks required columns: {missing}; inspect catalog before export")
        resolved[role] = columns
    return resolved


def _write_json(path: Path, value: dict) -> None:
    raw = json.dumps(value, indent=2, allow_nan=False) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(raw)
    temporary.replace(path)


def _file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _validate_frame(frame, job: dict) -> dict:
    if not isinstance(frame, pd.DataFrame) or frame.empty or frame.columns.tolist() != job["columns"]:
        raise ValueError(f'{job["job_id"]}: empty result or SQL projection differs from the requested columns')
    # SQL casts every field to text. Preserve nulls and literal NA/E source codes.
    if not frame.map(lambda value: value is None or value is pd.NA or
                     isinstance(value, str)).all().all():
        raise ValueError("WRDS export must preserve source strings; no silent numeric coercion")
    sessions = job["expected_sessions"]
    result = {"rows": len(frame), "columns": frame.columns.tolist()}
    if sessions is not None:
        column = "DlyCalDt" if job["role"] == "daily" else "dlycaldt"
        iso_dates(frame[column], f'{job["job_id"]}.{column}', sessions=True)
        if set(frame[column]) != set(sessions):
            raise ValueError(f'{job["job_id"]}: source dates do not exactly cover requested sessions')
        keys = ["PERMNO", column] if job["role"] == "daily" else [column]
        if frame[keys].isna().any().any() or frame.duplicated(keys).any():
            raise ValueError(f'{job["job_id"]}: missing or duplicate source keys')
        result.update(first_session=min(sessions), last_session=max(sessions),
                      distinct_sessions=len(sessions))
    return result


def _verify_part(folder: Path, job: dict, plan_id: str) -> dict:
    receipt = json.loads((folder / "receipt.json").read_text())
    signed = {key: value for key, value in receipt.items() if key != "receipt_id"}
    if (receipt.get("receipt_id") != fingerprint(signed) or receipt.get("plan_id") != plan_id
            or receipt.get("job_sha256") != fingerprint(job)
            or receipt.get("columns") != job["columns"]):
        raise ValueError(f'{job["job_id"]}: export receipt changed or belongs to a different request')
    if set(receipt.get("files", {})) != {"data.csv", "query.sql", "parameters.json"}:
        raise ValueError("Export receipt has an invalid file inventory")
    for filename, expected in receipt["files"].items():
        if _file_sha256(folder / filename) != expected:
            raise ValueError(f'{job["job_id"]}: checkpoint file changed: {filename}')
    if ((folder / "query.sql").read_text() != job["sql"] or
            json.loads((folder / "parameters.json").read_text()) != job["params"]):
        raise ValueError("Export query no longer matches its plan")
    return receipt


def _summary(plan: dict, parts: dict, authorization: dict | None) -> dict:
    returns = not _population(plan["partition"]) and any(
        job["job_id"] in parts and job["role"] in {"daily", "market"} for job in plan["jobs"])
    result = {"schema_version": 1, "plan_id": plan["plan_id"], "protocol_sha256": plan["protocol_sha256"],
              "partition": plan["partition"], "data_kind": plan["data_kind"],
              "expected_jobs": len(plan["jobs"]), "completed_jobs": len(parts),
              "source_export_complete": len(parts) == len(plan["jobs"]),
              "parts": parts, "model_ready": False, "human_reviews_completed": 0,
              "source_release_verified": False, "historical_availability_verified": False,
              "historical_cik_mapping_approved": False, "terminal_coverage_approved": False,
              "final_return_values_queried": plan["partition"] == "holdout" and returns,
              "final_price_volume_queried": plan["partition"] == "holdout_population" and any(
                  job["job_id"] in parts and job["role"] == "daily" for job in plan["jobs"]),
              "returns_queried": returns,
              "authorization_sha256": fingerprint(authorization) if authorization is not None else None,
              "remaining": ["source release and units evidence", "historical classification/availability review",
                            "finite historical CIK/security mapping evidence", "delisting and terminal coverage review",
                            "normalization and source-bound filing/label/control audits"],
              "license": "Private licensed source files; do not commit or redistribute raw rows"}
    result["checkpoint_id"] = fingerprint(result)
    return result


def export_wrds(connection, bindings: dict, output, config: dict, *, partition="population",
                resume=False, authorization=None, repo_root=".") -> dict:
    """Execute metadata-checked queries with atomic, hash-bound per-query checkpoints.

    Holdout authorization runs before any connection method or export-file read.
    A failed query leaves completed parts intact; --resume verifies them before
    requesting only missing parts. A changed query, binding, protocol or code
    requires a new output directory.
    """
    gate = _gate(partition, config, authorization)
    out = _private_output(output, repo_root)
    if out.exists() and not resume:
        raise ValueError("WRDS export output exists; use --resume for the identical request or a new path")
    resolved = _metadata(connection, bindings, partition)
    plan = plan_wrds_exports(bindings, config, partition, resolved_columns=resolved)
    if out.exists():
        existing = json.loads((out / "export_plan.json").read_text())
        if existing.get("plan_id") != fingerprint({key: value for key, value in existing.items() if key != "plan_id"}):
            raise ValueError("WRDS export plan fingerprint changed")
        # JSON round-trip canonicalizes tuple liquidity session lists.
        if fingerprint(existing) != fingerprint(plan):
            raise ValueError("WRDS resume request differs from its saved protocol, bindings, code or catalog")
    else:
        out.mkdir(parents=True)
        _write_json(out / "export_plan.json", plan)
        _write_json(out / "source_bindings.json", bindings)
    if fingerprint(json.loads((out / "source_bindings.json").read_text())) != plan["bindings_sha256"]:
        raise ValueError("WRDS saved source bindings changed")
    parts_root = out / "parts"
    parts_root.mkdir(exist_ok=True)
    expected = {job["job_id"] for job in plan["jobs"]}
    if {path.name for path in parts_root.iterdir()} - expected:
        raise ValueError("WRDS export contains unknown checkpoint parts")
    parts = {}
    # Validate every completed part before issuing any new value queries.
    for job in plan["jobs"]:
        folder = parts_root / job["job_id"]
        if folder.exists():
            parts[job["job_id"]] = _verify_part(folder, job, plan["plan_id"])
    checkpoint_path = out / "checkpoint.json"
    if checkpoint_path.exists():
        checkpoint = json.loads(checkpoint_path.read_text())
        if (checkpoint.get("checkpoint_id") != fingerprint({key: value for key, value in checkpoint.items()
                                                            if key != "checkpoint_id"})
                or checkpoint.get("plan_id") != plan["plan_id"]
                or any(parts.get(key) != value for key, value in checkpoint.get("parts", {}).items())):
            raise ValueError("WRDS checkpoint receipt changed")
    _write_json(out / "checkpoint.json", _summary(plan, parts, gate))
    for job in plan["jobs"]:
        if job["job_id"] in parts:
            continue
        frame = connection.raw_sql(job["sql"], params=job["params"], coerce_float=False)
        observed = _validate_frame(frame, job)
        with tempfile.TemporaryDirectory(prefix=".wrds-query-", dir=out) as temporary:
            stage = Path(temporary) / "part"
            stage.mkdir()
            frame.to_csv(stage / "data.csv", index=False)
            (stage / "query.sql").write_text(job["sql"])
            _write_json(stage / "parameters.json", job["params"])
            receipt = {"schema_version": 1, "plan_id": plan["plan_id"], "job_sha256": fingerprint(job),
                       "exported_at": datetime.now(timezone.utc).isoformat(), **observed,
                       "source": job["source"], "joined_sources": job["joined_sources"],
                       "source_release_verified": False,
                       "files": {name: _file_sha256(stage / name)
                                 for name in ["data.csv", "query.sql", "parameters.json"]}}
            receipt["receipt_id"] = fingerprint(receipt)
            _write_json(stage / "receipt.json", receipt)
            stage.rename(parts_root / job["job_id"])
        parts[job["job_id"]] = receipt
        _write_json(out / "checkpoint.json", _summary(plan, parts, gate))
    return _summary(plan, parts, gate)


def verify_wrds_export(output, config: dict, *, partition="population", authorization=None) -> dict:
    """Verify a transferred/private checkpoint without connecting to WRDS."""
    gate = _gate(partition, config, authorization)
    out = Path(output)
    plan = json.loads((out / "export_plan.json").read_text())
    if (plan.get("plan_id") != fingerprint({key: value for key, value in plan.items() if key != "plan_id"})
            or plan.get("protocol_sha256") != canonical_hash(config) or plan.get("partition") != partition):
        raise ValueError("WRDS checkpoint plan or partition/protocol differs")
    if fingerprint(json.loads((out / "source_bindings.json").read_text())) != plan["bindings_sha256"]:
        raise ValueError("WRDS saved source bindings changed")
    checkpoint = json.loads((out / "checkpoint.json").read_text())
    if checkpoint.get("checkpoint_id") != fingerprint({key: value for key, value in checkpoint.items() if key != "checkpoint_id"}):
        raise ValueError("WRDS checkpoint receipt changed")
    expected = {job["job_id"] for job in plan["jobs"]}
    if {path.name for path in (out / "parts").iterdir()} - expected:
        raise ValueError("WRDS export contains unknown checkpoint parts")
    parts = {job["job_id"]: _verify_part(out / "parts" / job["job_id"], job, plan["plan_id"])
             for job in plan["jobs"] if (out / "parts" / job["job_id"]).exists()}
    if checkpoint.get("parts") != parts:
        raise ValueError("WRDS checkpoint part inventory differs from verified files; resume to reconcile an interrupted write")
    return _summary(plan, parts, gate)


def assemble_wrds_csv(bundle, output, config: dict, *, partition="development",
                      authorization=None, repo_root=".") -> dict:
    """Concatenate verified monthly CSV parts, retaining source strings and order.

    Development daily/Names fields match stage-crsp's source contract. The
    separate benchmark file is retained for independent post-delisting coverage.
    This is file assembly, not approved market/universe normalization.
    """
    receipt = verify_wrds_export(bundle, config, partition=partition, authorization=authorization)
    if receipt["source_export_complete"] is not True:
        raise ValueError("Finish or resume every requested export before assembling CSVs")
    out = _private_output(output, repo_root)
    if out.exists():
        raise ValueError("WRDS CSV assembly output exists; preserve the prior files")
    bundle = Path(bundle)
    plan = json.loads((bundle / "export_plan.json").read_text())
    names = {"names": "crsp_names.csv", "links": "crsp_ccm_link_history.csv",
             "company": "compustat_company_headers.csv", "market": "crsp_market.csv",
             "daily": "crsp_liquidity.csv" if _population(partition) else "crsp_daily.csv"}
    result = {"schema_version": 1, "partition": partition, "protocol_sha256": canonical_hash(config),
              "plan_id": plan["plan_id"], "source_checkpoint_sha256": _file_sha256(bundle / "checkpoint.json"),
              "data_kind": plan["data_kind"], "model_ready": False, "files": {}, "rows": {}}
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".wrds-assemble-", dir=out.parent) as temporary:
        stage = Path(temporary) / "csv"
        stage.mkdir()
        for role, filename in names.items():
            jobs = [job for job in plan["jobs"] if job["role"] == role]
            if not jobs:
                continue
            expected_header = None
            with (stage / filename).open("wb") as target:
                for job in jobs:
                    path = bundle / "parts" / job["job_id"] / "data.csv"
                    # Hash the same bytes being copied, including the source
                    # header, so a concurrent source edit cannot escape checks.
                    digest = hashlib.sha256()
                    with path.open("rb") as source:
                        header = source.readline()
                        digest.update(header)
                        if expected_header is None:
                            expected_header = header
                            target.write(header)
                        elif header != expected_header:
                            raise ValueError("WRDS monthly CSV headers differ")
                        while chunk := source.read(1024 * 1024):
                            digest.update(chunk)
                            target.write(chunk)
                    if digest.hexdigest() != receipt["parts"][job["job_id"]]["files"]["data.csv"]:
                        raise ValueError("WRDS source part changed during CSV assembly")
            result["files"][filename] = _file_sha256(stage / filename)
            result["rows"][filename] = sum(receipt["parts"][job["job_id"]]["rows"] for job in jobs)
        result["assembly_id"] = fingerprint(result)
        _write_json(stage / "assembly_receipt.json", result)
        stage.rename(out)
    return result
