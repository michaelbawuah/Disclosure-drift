"""Revalidate five assistant-inspected expansion scopes against original SEC bytes.

The scope decisions were inspected independently of the range-rule generator.
This verifies those recorded decisions; it does not produce human sign-off.
"""

import argparse
import json
import re
from pathlib import Path

from disclosure_research.audit import cached_body
from disclosure_research.extraction import TOKEN, VERSION, clean_html, extract_risk_factors
from disclosure_research.market_data import sha256
from disclosure_research.pilot_audit import require


INSPECTED = {
    "0001141391-20-000032": (62233, 132708, "a85c2757de45ef8fdb158e02f7e8ad974f2777ea03d608c7f984840eb5a0c6a8"),
    "0001141391-21-000018": (72750, 145779, "8073841dd23f652546deacb8aeed644e5181c22ec5008218145f18aea222dbf6"),
    "0000063908-20-000022": (99035, 137490, "0f9d982ecb46fdc162bbb584c9283e5603e5b71656b7f451792855b81c89a359"),
    "0000063908-21-000013": (104736, 144832, "43a55a570bbb0bbb94f59af6975350513609c9d737f4f46111986bc5eb48f019"),
    "0000773840-21-000015": (58673, 100641, "8263bd8ba266dbe0f360aa78c55c11a8bb0f885a4ca43b07e89b80900358bb76"),
}


def verify(root, output):
    root, output = Path(root), Path(output)
    require(not output.exists(), "Preserve the earlier scope-review receipt")
    rules_path = root / "configs/pilot_expansion_resolutions.json"
    raw_rules = rules_path.read_bytes()
    document = json.loads(raw_rules)
    require(document["normalizer_version"] == VERSION, "Inspected source normalizer changed")
    rules = {r["accession"]: r for r in document["rules"]}
    rows = []
    for accession, (start, end, source_hash) in INSPECTED.items():
        rule = rules[accession]
        require((rule["start_offset"], rule["end_offset"], rule["source_sha256"]) ==
                (start, end, source_hash), "Registered rule differs from independently inspected scope")
        require(rule["primary_sha256"] == source_hash and rule["primary_url"] == rule["source_url"],
                "Inspected source must remain the original primary filing")
        source = cached_body(root / "data/raw/sec_cache", rule["source_url"], source_hash)
        normalized = clean_html(source)
        initial = extract_risk_factors(source)
        require(sha256(initial.text.encode()) == rule["primary_reference_sha256"],
                "Initial numbered Item 1A evidence changed")
        section = normalized[start:end].strip(" .:-\n")
        require(sha256(section.encode()) == rule["text_sha256"] and
                len(TOKEN.findall(section)) == rule["token_count"], "Inspected section text differs")
        item = {"accession": accession, "source_url": rule["source_url"], "source_sha256": source_hash,
                "start_offset": start, "end_offset": end, "text_sha256": sha256(section.encode()),
                "token_count": len(TOKEN.findall(section)), "reviewer_type": "assistant",
                "boundary_verdict": "pass_for_described_risk_factors_scope", "human_review_complete": False,
                "next_section": normalized[end:end + 70].splitlines()[0],
                "normalizer_version": VERSION,
                "scope_decision": "Complete continuous labeled Risk Factors block; page furniture retained"}
        if accession.startswith("0001141391"):
            require(section.startswith("RISK HIGHLIGHTS"), "Mastercard risk highlights omitted")
            require(normalized[end:].startswith("Item 1B."), "Mastercard end is not substantive Item 1B")
            item["running_item1a_headings_retained"] = len(re.findall(
                r"(?im)^item\s+1a\.\s+risk factors\b", section))
            require(item["running_item1a_headings_retained"] > 1, "Risk-section pages were truncated")
            item["risk_highlights_included"] = True
        elif accession.startswith("0000063908"):
            require(normalized[end:].startswith("LEGAL PROCEEDINGS"), "McDonald's range includes the next section")
            caution_start = normalized.index("FORWARD-LOOKING STATEMENTS")
            caution_end = normalized.index("ABOUT McDONALD'S", caution_start)
            caution = normalized[caution_start:caution_end].strip()
            require(caution_end < start and '"Risk Factors" section' in caution,
                    "Separate cautionary statement or its Risk Factors reference differs")
            item["separate_cautionary_statement"] = {
                "start_offset": caution_start, "end_offset": caution_end,
                "text_sha256": sha256(caution.encode()), "token_count": len(TOKEN.findall(caution)),
                "included_in_risk_comparison": False,
                "inspection": "General statement identification, non-guarantee and no-update caution; refers back to the separately labeled Risk Factors section"}
            item["scope_limitation"] = "Item 1A cross-reference also includes page 3 cautionary text; this comparison is the labeled risk block, not all material cross-referenced under Item 1A"
        else:
            require(initial.text == "24", "Honeywell Item 1A index reference changed")
            require(normalized[58661:start] == "RISK FACTORS" and
                    normalized[end:].startswith("QUANTITATIVE AND QUALITATIVE DISCLOSURES ABOUT MARKET RISKS"),
                    "Honeywell standalone heading boundaries changed")
            require(section.startswith("Our business, operating results, cash flows and financial condition") and
                    all(label in section for label in ["MACROECONOMIC AND INDUSTRY RISKS",
                                                       "OPERATIONAL RISKS", "LEGAL AND REGULATORY RISKS"]) and
                    normalized[start:end].rstrip().endswith("cash flows, liquidity and financial condition."),
                    "Honeywell inspected beginning, risk categories or final paragraph changed")
            item["item1a_index_page"] = 24
            item["last_risk_page"] = 32
            item["scope_decision"] = "Continuous substantive Risk Factors block pointed to by the Item 1A index; includes final litigation/insurance paragraph and excludes following Item 7A market-risk material"
            item["risk_categories_included"] = ["macroeconomic_and_industry", "operational", "legal_and_regulatory"]
            item["boundary_reason"] = "Numbered Item 1A is only a cross-reference; later Item 1B would incorrectly include intervening market-risk and liquidity discussion"
        rows.append(item)
    result = {"status": "five_source_bound_assistant_scope_reviews_completed",
              "reviewer_type": "assistant", "source_files_reviewed": len(rows), "human_reviews_added": 0,
              "source_based_selection": True, "market_returns_used": False, "final_period_opened": False,
              "rule_file_sha256": sha256(raw_rules), "review_script_sha256": sha256(Path(__file__).read_bytes()),
              "cases": rows}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    summary = verify(args.root, args.output)
    print(json.dumps({k: v for k, v in summary.items() if k != "cases"}, indent=2))
