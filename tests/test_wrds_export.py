import json
import re
import runpy
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from disclosure_research.crsp_staging import stage_crsp
from disclosure_research.market_data import sha256
from disclosure_research.protocol import canonical_hash, load_protocol
from disclosure_research.timing import calendar
from disclosure_research.universe import year_start_window
from disclosure_research.wrds_export import (
    SOURCE_FIELDS,
    assemble_wrds_csv,
    discover_wrds_sources,
    export_wrds,
    plan_wrds_exports,
    verify_wrds_export,
)


class LocalWrds:
    """Run emitted SQL against invented DuckDB sources; never contact WRDS."""

    def __init__(self, tables):
        self.tables, self.metadata_calls, self.value_queries = tables, [], []
        self.fail_at = None
        self.db = duckdb.connect()
        for (library, table), frame in tables.items():
            self.db.execute(f'CREATE SCHEMA IF NOT EXISTS "{library}"')
            self.db.register("incoming", frame)
            self.db.execute(f'CREATE TABLE "{library}"."{table}" AS SELECT * FROM incoming')

    def list_libraries(self):
        return sorted({key[0] for key in self.tables})

    def list_tables(self, library):
        return [table for lib, table in self.tables if lib == library]

    def describe_table(self, library, table):
        self.metadata_calls.append((library, table))
        return pd.DataFrame({"name": self.tables[library, table].columns})

    def raw_sql(self, sql, *, params, coerce_float):
        assert coerce_float is False
        self.value_queries.append((sql, params))
        if len(self.value_queries) == self.fail_at:
            raise ConnectionError("Invented interrupted download")
        query = re.sub(r"%\((\w+)\)s", r"$\1", sql)
        return self.db.execute(query, params).fetchdf()

    def close(self):
        self.db.close()


@pytest.fixture
def setup_sources():
    bindings = json.loads(Path("configs/wrds_sources.template.json").read_text())
    config = {**load_protocol(), "initial_train_start": 2019, "development_end": 2019,
              "holdout_start": 2020, "holdout_end": 2020}
    dates = [session for session in calendar().sessions.strftime("%Y-%m-%d")
             if "2018-10-01" <= session <= "2021-02-15"]
    daily = []
    for permno in ["10001", "10002"]:
        for date in dates:
            if permno == "10002" and date > "2019-07-01":
                continue
            terminal = permno == "10002" and date == "2019-07-01"
            daily.append({"permno": permno, "hdrcusip": "01234567", "ticker": "" if terminal else "OLD",
                          "permco": "20001", "dlycaldt": date, "dlydelflg": "Y" if terminal else "N",
                          "dlycap": None if terminal else "125.50", "dlyret": "0.0123456789012345",
                          "dlyretmissflg": "NA", "dlyprc": "0" if terminal else "125.50", "dlyvol": "10000",
                          "dlyprcflg": "DA" if terminal else "T"})
    names = []
    for permno in ["10001", "10002"]:
        row = {column: "source-code" for column in SOURCE_FIELDS["names"]}
        row.update(permno=permno, permco="20001", secinfostartdt="2000-01-01", secinfoenddt="2030-12-31",
                   securitybegdt="2000-01-01", securityenddt="2019-07-01" if permno == "10002" else "2030-12-31",
                   securityactiveflg="N" if permno == "10002" else "Y", siccd="1234")
        names.append(row)
    links = [{"gvkey": "000001", "liid": "01", "linkprim": "P", "linktype": "LC", "lpermno": "10001",
              "lpermco": "20001", "linkdt": "1990-01-01", "linkenddt": "E"},
             {"gvkey": "000002", "liid": "01", "linkprim": "P", "linktype": "NR", "lpermno": None,
              "lpermco": None, "linkdt": "1990-01-01", "linkenddt": "E"}]
    frames = {"daily": pd.DataFrame(daily), "names": pd.DataFrame(names), "links": pd.DataFrame(links),
              "company": pd.DataFrame([{"gvkey": "000001", "cik": "0002115436", "conm": "Invented header",
                                         "tic": "HEADER", "cusip": "01234567"}]),
              "market": pd.DataFrame({"dlycaldt": dates, "vwretd": ["0.001"] * len(dates)})}
    tables = {(source["library"], source["table"]): frames[role]
              for role, source in bindings["sources"].items()}
    client = LocalWrds(tables)
    yield bindings, config, client
    client.close()


def test_full_request_has_exact_liquidity_and_final_tail_without_population_returns():
    bindings = json.loads(Path("configs/wrds_sources.template.json").read_text())
    config = load_protocol()
    population = plan_wrds_exports(bindings, config, "full_population")
    assert population["request_start"] == "2009-10-07"
    assert len(population["annual_liquidity_windows"]) == 16
    default = plan_wrds_exports(bindings, config)
    heldout = plan_wrds_exports(bindings, config, "holdout_population")
    assert [window["universe_year"] for window in default["annual_liquidity_windows"]] == list(range(2010, 2022))
    assert [window["universe_year"] for window in heldout["annual_liquidity_windows"]] == list(range(2022, 2026))
    assert max(date for job in default["jobs"] for date in (job["expected_sessions"] or [])) == "2020-12-31"
    for year in range(2010, 2026):
        parts = [job for job in population["jobs"] if job["job_id"].startswith(f"liquidity-{year}-")]
        dates = [date for job in parts for date in job["expected_sessions"]]
        assert dates == list(year_start_window(year, config)["sessions"])
        assert len(dates) == len(set(dates)) == 60
    for job in population["jobs"]:
        assert not re.search(r"dlyret|dlycap|dlydelflg|vwretd|\bLIMIT\b|\bDISTINCT\b", job["sql"], re.I)
        assert "s.*" not in job["sql"] and " IN ('" not in job["sql"]
    development = plan_wrds_exports(bindings, config, "development")
    holdout = plan_wrds_exports(bindings, config, "holdout")
    assert development["request_end"] == "2022-02-02"
    assert holdout["request_start"] == "2021-10-07"
    assert holdout["request_end"] == "2026-02-03"
    for plan in [development, holdout]:
        dates = [date for job in plan["jobs"] if job["role"] == "market" for date in job["expected_sessions"]]
        assert max(dates) == plan["request_end"]
        assert len(dates) == len(set(dates))
        assert all("LEFT JOIN" in job["sql"] for job in plan["jobs"] if job["role"] == "daily")


def test_catalog_is_metadata_only_and_does_not_assert_entitlement(setup_sources):
    _, _, client = setup_sources
    receipt = discover_wrds_sources(client, libraries=["crsp_a_stock", "missing_vendor", "crsp", "comp"])
    assert client.value_queries == []
    assert receipt["unavailable_requested_libraries"] == ["missing_vendor"]
    assert all(candidates for candidates in receipt["candidates"].values())
    assert all(not candidate["missing_required_columns"]
               for candidates in receipt["candidates"].values() for candidate in candidates)
    assert receipt["values_queried"] is receipt["account_credentials_recorded"] is False


def test_metadata_mismatch_blocks_before_values_or_checkpoint(setup_sources, tmp_path):
    bindings, config, client = setup_sources
    source = bindings["sources"]["daily"]
    key = source["library"], source["table"]
    client.tables[key] = client.tables[key].drop(columns="dlyvol")
    with pytest.raises(ValueError, match="lacks required columns.*dlyvol"):
        export_wrds(client, bindings, tmp_path / "export", config)
    assert not (tmp_path / "export").exists()
    assert client.value_queries == []


def test_population_retains_later_delisted_security_and_unresolved_identity_codes(setup_sources, tmp_path):
    bindings, config, client = setup_sources
    receipt = export_wrds(client, bindings, tmp_path / "population", config)
    assembled = assemble_wrds_csv(tmp_path / "population", tmp_path / "csv", config, partition="population")
    names = pd.read_csv(tmp_path / "csv/crsp_names.csv", dtype=str, keep_default_na=False)
    links = pd.read_csv(tmp_path / "csv/crsp_ccm_link_history.csv", dtype=str, keep_default_na=False)
    liquidity = pd.read_csv(tmp_path / "csv/crsp_liquidity.csv", dtype=str, keep_default_na=False)
    assert set(names.permno) == {"10001", "10002"}
    assert "10002" in set(liquidity.loc[liquidity.DlyCalDt.str.startswith("2018"), "PERMNO"])
    assert set(links.linktype) == {"LC", "NR"}
    assert set(links.linkenddt) == {"E"}
    assert links.loc[links.linktype == "NR", "lpermno"].iloc[0] == ""
    assert receipt["source_export_complete"] is True
    assert receipt["returns_queried"] is receipt["model_ready"] is False
    assert receipt["historical_cik_mapping_approved"] is receipt["historical_availability_verified"] is False
    assert assembled["files"]["crsp_liquidity.csv"] == sha256((tmp_path / "csv/crsp_liquidity.csv").read_bytes())


def test_development_keeps_blank_terminal_ticker_exact_returns_and_separate_benchmark(setup_sources, tmp_path):
    bindings, config, client = setup_sources
    receipt = export_wrds(client, bindings, tmp_path / "development", config, partition="development")
    assemble_wrds_csv(tmp_path / "development", tmp_path / "csv", config)
    daily = pd.read_csv(tmp_path / "csv/crsp_daily.csv", dtype=str, keep_default_na=False)
    market = pd.read_csv(tmp_path / "csv/crsp_market.csv", dtype=str, keep_default_na=False)
    terminal = daily.loc[(daily.PERMNO == "10002") & (daily.DlyCalDt == "2019-07-01")].iloc[0]
    assert terminal.Ticker == "" and terminal.DlyDelFlg == "Y" and terminal.DlyCap == ""
    assert terminal.DlyRet == "0.0123456789012345" and terminal.DlyRetMissFlg == "NA"
    assert market.dlycaldt.max() > daily.loc[daily.PERMNO == "10002", "DlyCalDt"].max()
    assert daily.DlyCalDt.max() == market.dlycaldt.max() == "2020-02-03"
    assert receipt["returns_queried"] is True and receipt["final_return_values_queried"] is False
    assert receipt["model_ready"] is False
    staged = stage_crsp(tmp_path / "csv/crsp_daily.csv", tmp_path / "csv/crsp_names.csv",
                        tmp_path / "source-staging", config, "2018-10-04", "2020-02-03")
    assert staged["coverage"]["terminal_rows"] == 1
    assert staged["coverage"]["missing_benchmark_sessions"] == 0
    assert staged["model_ready"] is False


def test_interrupted_export_resumes_only_missing_parts_and_preserves_completed_bytes(setup_sources, tmp_path):
    bindings, config, client = setup_sources
    client.fail_at = 4
    output = tmp_path / "export"
    with pytest.raises(ConnectionError, match="interrupted"):
        export_wrds(client, bindings, output, config)
    checkpoint = verify_wrds_export(output, config)
    assert checkpoint["completed_jobs"] == 3 and checkpoint["source_export_complete"] is False
    saved = (output / "parts/names/data.csv").read_bytes()
    client.fail_at = None
    calls_before = len(client.value_queries)
    complete = export_wrds(client, bindings, output, config, resume=True)
    assert len(client.value_queries) - calls_before == complete["expected_jobs"] - 3
    assert (output / "parts/names/data.csv").read_bytes() == saved
    assert verify_wrds_export(output, config)["source_export_complete"] is True
    calls_before = len(client.value_queries)
    export_wrds(client, bindings, output, config, resume=True)
    assert len(client.value_queries) == calls_before
    with pytest.raises(ValueError, match="output exists"):
        export_wrds(client, bindings, output, config)


@pytest.mark.parametrize("changed", ["data", "query", "receipt", "checkpoint", "bindings"])
def test_resume_rejects_mutation_before_new_value_queries(setup_sources, tmp_path, changed):
    bindings, config, client = setup_sources
    output = tmp_path / "export"
    client.fail_at = 2
    with pytest.raises(ConnectionError):
        export_wrds(client, bindings, output, config)
    paths = {"data": "parts/names/data.csv", "query": "parts/names/query.sql",
             "receipt": "parts/names/receipt.json", "checkpoint": "checkpoint.json",
             "bindings": "source_bindings.json"}
    path = output / paths[changed]
    if changed in {"receipt", "checkpoint", "bindings"}:
        value = json.loads(path.read_text())
        value["changed"] = True
        path.write_text(json.dumps(value))
    else:
        path.write_bytes(path.read_bytes() + b"changed")
    calls_before = len(client.value_queries)
    with pytest.raises(ValueError, match="changed"):
        export_wrds(client, bindings, output, config, resume=True)
    assert len(client.value_queries) == calls_before


@pytest.mark.parametrize("partition", ["holdout", "holdout_population"])
@pytest.mark.parametrize("authorization", [None, lambda: True, lambda: {"prerequisites_verified": False},
                                           lambda: {"prerequisites_verified": True, "protocol_sha256": "wrong"}])
def test_holdout_denied_before_connection_methods_or_saved_files(setup_sources, tmp_path, authorization, partition):
    bindings, config, client = setup_sources
    with pytest.raises(ValueError, match="prerequisites"):
        export_wrds(client, bindings, tmp_path / "holdout", config, partition=partition, authorization=authorization)
    with pytest.raises(ValueError, match="prerequisites"):
        verify_wrds_export(tmp_path / "does-not-exist", config, partition=partition, authorization=authorization)
    assert client.metadata_calls == client.value_queries == []
    assert not (tmp_path / "holdout").exists()


def test_holdout_exports_stay_separate_and_never_claim_audit_approval(setup_sources, tmp_path):
    bindings, config, client = setup_sources
    def authorization():
        return {"prerequisites_verified": True, "protocol_sha256": canonical_hash(config)}
    receipt = export_wrds(client, bindings, tmp_path / "holdout", config, partition="holdout", authorization=authorization)
    assert receipt["final_return_values_queried"] is True
    assert receipt["model_ready"] is False and receipt["human_reviews_completed"] == 0
    with pytest.raises(ValueError, match="differs"):
        export_wrds(client, bindings, tmp_path / "holdout", config, partition="development", resume=True)


@pytest.mark.parametrize("partition", ["holdout", "holdout_population"])
def test_cli_holdout_gate_precedes_even_the_local_credential_prompt(tmp_path, partition):
    main = runpy.run_path("scripts/wrds_full_export.py")["main"]
    calls = []
    with pytest.raises(ValueError, match="prerequisite request"):
        main(["export", "--partition", partition, "--output", str(tmp_path / "holdout")],
             connection_factory=lambda: calls.append("credentials requested"))
    assert calls == []


def test_raw_exports_refuse_public_repository_paths(setup_sources, tmp_path):
    bindings, config, client = setup_sources
    with pytest.raises(ValueError, match="ignored data"):
        export_wrds(client, bindings, tmp_path / "reports/licensed", config, repo_root=tmp_path)
    assert client.metadata_calls == client.value_queries == []


def test_missing_sessions_do_not_produce_completed_export(setup_sources, tmp_path):
    bindings, config, client = setup_sources
    source = bindings["sources"]["daily"]
    client.db.execute(f'DELETE FROM "{source["library"]}"."{source["table"]}" WHERE dlycaldt=\'2018-10-05\'')
    with pytest.raises(ValueError, match="exactly cover requested sessions"):
        export_wrds(client, bindings, tmp_path / "export", config)
    assert verify_wrds_export(tmp_path / "export", config)["source_export_complete"] is False
