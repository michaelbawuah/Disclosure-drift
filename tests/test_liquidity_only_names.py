"""Research regressions for explaining annual snapshot absences."""

import hashlib
import json
import runpy
from pathlib import Path

import pytest
import test_historical_foundation as foundation_fixtures

from disclosure_research import historical_foundation as foundation
from test_historical_foundation import _ccm, _daily, _name, _window

make_inputs = foundation_fixtures.make_inputs

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_liquidity_only_names.py"
API = runpy.run_path(str(SCRIPT))


def _row(start, end, *, life_start=None, life_end=None):
    return {"info_start": start, "info_end": end,
            "life_start": life_start or start, "life_end": life_end or end}


@pytest.mark.parametrize("records,expected", [
    ([], "NO_SAVED_NAMES_HISTORY"),
    ([_row("2019-01-01", "2020-01-01")], "DESCRIPTOR_COVERS_SELECTION"),
    ([_row("2020-01-01", "2021-01-01")], "DESCRIPTOR_COVERS_SELECTION"),
    ([_row("2018-01-01", "2019-12-31")],
     "ALL_RECORDED_SECURITY_LIFETIMES_END_BEFORE_SELECTION"),
    ([_row("2020-01-02", "2021-01-01")],
     "ALL_RECORDED_SECURITY_LIFETIMES_BEGIN_AFTER_SELECTION"),
    ([_row("2018-01-01", "2019-12-31", life_end="2020-01-01")],
     "DESCRIPTOR_GAP_INSIDE_RECORDED_SECURITY_LIFETIME"),
    ([_row("2018-01-01", "2019-12-31"), _row("2020-01-02", "2021-01-01")],
     "BETWEEN_RECORDED_SECURITY_LIFETIMES"),
])
def test_endpoints_and_history_gaps_are_distinct(records, expected):
    assert API["interval_geometry"](records, "2020-01-01") == expected


def _inputs(make_inputs):
    names = [_name("10"), _name("20", secinfostartdt="2020-01-01", secinfoenddt="2020-12-31",
                               securitybegdt="2020-01-01", securityenddt="2020-12-31")]
    daily = [_daily(day, security=security) for security in ("10", "20", "30")
             for day in _window()["sessions"][:40]]
    args = make_inputs(names=names, ccm=[_ccm("10")], daily=daily)
    foundation.build_historical_foundation_review(**args)
    identity = json.loads((args["identity_directory"] / "receipt.json").read_text())
    listing = Path(identity["inputs"]["listing_candidates_directory"])
    listing_receipt = json.loads((listing / "receipt.json").read_text())
    return {"foundation_directory": args["output"],
            "foundation_sha256": hashlib.sha256((args["output"] / "receipt.json").read_bytes()).hexdigest(),
            "listing_directory": listing,
            "names_inventory": listing_receipt["source"]["inventory_directory"],
            "names_inventory_sha256": listing_receipt["source"]["inventory_receipt_sha256"],
            "output": args["repo_root"] / "data/geometry",
            "config": args["config"], "repo_root": args["repo_root"]}


def test_complete_source_check_distinguishes_ended_and_missing_and_preserves_inputs(make_inputs):
    args = _inputs(make_inputs)
    original = (args["foundation_directory"] / "receipt.json").read_bytes()
    report = API["check_saved_coverage"](**args)
    assert report["liquidity_only_annual_records"] == 2
    assert report["geometry_counts"] == {
        "ALL_RECORDED_SECURITY_LIFETIMES_END_BEFORE_SELECTION": 1, "NO_SAVED_NAMES_HISTORY": 1}
    assert report["numeric_minimum_pass_geometry_counts"] == report["geometry_counts"]
    assert report["numeric_minimum_fail_geometry_counts"] == {}
    assert report["names_source_rows_preflighted"] == 2
    assert report["source_interval_occurrences_retained"] == 1
    rows = [json.loads(line) for line in (args["output"] / "observations.jsonl").read_text().splitlines()]
    assert {row["original_annual_observation"]["security_id"] for row in rows} == {"20", "30"}
    assert all(row["exclusion_approved"] is False and row["known_at"] is None for row in rows)
    assert (args["foundation_directory"] / "receipt.json").read_bytes() == original
    assert report["exclusions_approved"] == 0 and report["model_ready"] is False
    assert report["market_outcomes_read"] is False and report["final_period_opened"] is False
    for path in args["output"].rglob("*"):
        assert path.stat().st_mode & 0o777 == (0o700 if path.is_dir() else 0o400)
    with pytest.raises(ValueError, match="exists"):
        API["check_saved_coverage"](**args)


def test_stale_source_receipt_and_mutated_original_are_rejected(make_inputs):
    args = _inputs(make_inputs)
    expected = args["names_inventory_sha256"]
    args["names_inventory_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="inventory pin"):
        API["check_saved_coverage"](**args)
    assert not args["output"].exists()
    args["names_inventory_sha256"] = expected
    source = Path(args["names_inventory"]) / "source.csv"
    source.chmod(0o600)
    source.write_bytes(source.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="byte count|hash"):
        API["check_saved_coverage"](**args)
    assert not args["output"].exists()
