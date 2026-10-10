"""Reproducible figures and an explicitly unfinished empirical-study report."""

import hashlib
import json
from pathlib import Path
from xml.sax.saxutils import escape

import pandas as pd

REPO = "https://github.com/michaelbawuah/Disclosure-drift"


def make_figures(checkpoint, output) -> list[Path]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    root, out = Path(checkpoint), Path(output)
    out.mkdir(parents=True, exist_ok=True)
    frame = pd.read_csv(root / "text_features.csv")
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False})
    counts = frame.groupby("year").size()
    fig, ax = plt.subplots(figsize=(8.1, 3.0), layout="constrained")
    ax.bar(counts.index.astype(str), counts.values, color="#087e8b", width=.6)
    for i, value in enumerate(counts):
        ax.text(i, value + .3, str(value), ha="center", fontsize=10)
    ax.set(ylim=(0, max(counts) + 4), ylabel="Original annual filing pairs", xlabel="Acceptance year (New York)")
    ax.set_title("Observed SEC parser-pilot coverage", loc="left", fontweight="bold")
    fig.savefig(out / "pilot_coverage.png", dpi=190)
    plt.close(fig)
    fig, axes = plt.subplots(1, 3, figsize=(9, 3.0), layout="constrained")
    labels = {"log_length_change": "Log length change", "jaccard_distance": "Jaccard distance",
              "tfidf_cosine_distance": "TF-IDF cosine distance"}
    for ax, (column, label) in zip(axes, labels.items(), strict=True):
        values = frame[column].dropna()
        ax.hist(values, bins=18, color="#087e8b", edgecolor="white")
        ax.set_title(f"{label}\nn = {len(values)}", fontsize=10)
        ax.set_xlabel("Observed feature value")
    axes[0].set_ylabel("Filing pairs")
    fig.savefig(out / "text_distributions.png", dpi=190)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(8.1, 3.0), layout="constrained")
    limits = [(2010, 2015, "Initial training", "#9bc3ca"),
              (2016, 2021, "Development / selection", "#087e8b"),
              (2022, 2025, "Final evaluation / still sealed", "#d3aa55")]
    for start, end, label, color in limits:
        ax.barh(label, end - start + 1, left=start - .5, color=color, height=.45)
    ax.set_xticks(range(2010, 2026, 2))
    ax.set(xlim=(2009.5, 2025.5), xlabel="Acceptance year")
    ax.invert_yaxis()
    ax.set_title("Frozen chronological design", loc="left", fontweight="bold")
    fig.savefig(out / "research_periods.png", dpi=190)
    plt.close(fig)
    return [out / name for name in ["pilot_coverage.png", "text_distributions.png", "research_periods.png"]]


def build_progress_report(checkpoint, output, *, verification=None, repository=REPO) -> dict:
    """Build public SEC-only exhibits; never invent empirical result-table entries."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    root, out = Path(checkpoint), Path(output)
    if out.exists():
        raise ValueError("Report output exists; preserve the previous report")
    pilot = json.loads((root / "pilot_checkpoint.json").read_text())
    if (pilot.get("data_kind") != "REAL_SEC_TEXT_DESCRIPTIVE_PILOT"
            or pilot.get("returns_read") is not False
            or pilot.get("predictive_performance_claim") is not False):
        raise ValueError("This progress report requires the SEC-only descriptive checkpoint")
    for name in ["text_features.csv", "coverage_by_year.csv", "examples.json"]:
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != pilot.get("files", {}).get(name):
            raise ValueError(f"Pilot checkpoint artifact changed: {name}")
    arithmetic_path = Path("reports/pilot_arithmetic_summary.json")
    followup_path = Path("reports/review_followup_summary.json")
    arithmetic_raw, followup_raw = arithmetic_path.read_bytes(), followup_path.read_bytes()
    arithmetic, followup = json.loads(arithmetic_raw), json.loads(followup_raw)
    if (arithmetic.get("source_hashes", {}).get("filings") != pilot["sources"]["filings"]
            or arithmetic.get("source_hashes", {}).get("filing_pairs") != pilot["sources"]["pairs"]
            or arithmetic.get("source_hashes", {}).get("protocol") != pilot["protocol_sha256"]
            or followup.get("original_arithmetic_receipt_sha256") != hashlib.sha256(arithmetic_raw).hexdigest()):
        raise ValueError("Saved arithmetic/review receipts do not match this pilot checkpoint")
    verified = json.loads(Path(verification).read_text()) if verification else {}
    out.mkdir(parents=True)
    figures = make_figures(root, out / "figures")
    navy, teal = colors.HexColor("#183042"), colors.HexColor("#087e8b")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("TitleCustom", fontName="Helvetica-Bold", fontSize=27, leading=31,
                              textColor=navy, spaceAfter=18))
    styles.add(ParagraphStyle("SectionCustom", fontName="Helvetica-Bold", fontSize=18, leading=23,
                              textColor=navy, spaceAfter=13))
    styles.add(ParagraphStyle("SubCustom", fontName="Helvetica-Bold", fontSize=11.5, leading=16,
                              textColor=teal, spaceBefore=12, spaceAfter=6))
    styles.add(ParagraphStyle("BodyCustom", fontName="Helvetica", fontSize=10, leading=14.5,
                              alignment=TA_LEFT, textColor=navy, spaceAfter=9))
    styles.add(ParagraphStyle("SmallCustom", parent=styles["BodyCustom"], fontSize=8.5, leading=11.7))
    styles.add(ParagraphStyle("TableCustom", parent=styles["BodyCustom"], fontSize=8.7, leading=12, spaceAfter=0))

    def p(text, style="BodyCustom"):
        return Paragraph(text, styles[style])

    def table(rows, widths):
        cells = [[p(escape(str(value)), "TableCustom") for value in row] for row in rows]
        result = Table(cells, colWidths=widths, hAlign="LEFT", repeatRows=1)
        result.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e3eff1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 8), ("LINEBELOW", (0, 0), (-1, 0), .8, teal),
            ("LINEBELOW", (0, 1), (-1, -1), .3, colors.HexColor("#dbe3e8"))]))
        return result

    def img(path, width=510):
        w, h = ImageReader(str(path)).getSize()
        return Image(str(path), width=width, height=width*h/w)

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#d5dfe5"))
        canvas.line(42, 39, 570, 39)
        canvas.setFillColor(navy)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(42, 26, "DISCLOSURE DRIFT  |  Research progress - empirical result pending")
        canvas.drawRightString(570, 26, str(doc.page))
        canvas.restoreState()

    pages = []
    pages.append([
        p("DISCLOSURE DRIFT", "SubCustom"),
        p("Risk disclosures and<br/>return forecasting", "TitleCustom"),
        p("Research progress report | 10 October 2026<br/>Michael Baffour Awuah | Cornell University", "BodyCustom"),
        table([["Primary empirical result", "Not estimated"], ["Study status", "Pipeline implementation and pilot evidence; empirical completion gates remain open"]], [155, 373]),
        Spacer(1, 14),
        p("Research question", "SubCustom"),
        p("Do changes in an issuer's annual Risk Factors disclosures improve forecasts of its next 20-session market-adjusted return beyond momentum, volatility, size and historical industry controls?"),
        p("This study is inspired by Cohen, Malloy and Nguyen's <i>Lazy Prices</i> [1]. It narrows the document input to original annual Item 1A sections and fixes a 20-session forecast comparison. It is a new investigation; the source paper's findings are not results for this sample."),
        p("Evidence available now", "SubCustom"),
        p(f"The recovered SEC checkpoint contains <b>{pilot['filings']} original filings, {pilot['pairs']} annual pairs and {pilot['issuers']} issuers</b>. The original sources pass the automated audit. Candidate market arithmetic also reproduces, while historical identity, availability, and human reviews remain pending [3-5]."),
        p("The final 2022-2025 empirical evaluation has not been opened. Figures in this report describe observed SEC text or the frozen method. Any full-pipeline demonstration uses invented data and provides software evidence only."),
        p(f'<link href="{repository}" color="#087e8b">Public code and audit trail</link>', "SmallCustom"),
    ])
    coverage_rows = [["Acceptance year", "Annual pairs", "Issuers"]] + [
        [row["year"], row["pairs"], row["issuers"]] for row in pilot["year_coverage"]]
    pages.append([
        p("1. Pilot scope and coverage", "SectionCustom"),
        p("The existing sample was selected to exercise document formats, reference exhibits and time conventions. It has no claim to be a representative investment universe. Pair coverage is shown by acceptance year below. The pairing rule preserves issuer identity and consecutive annual filings; predecessor issuers are not silently spliced into the record."),
        img(figures[0]), Spacer(1, 5), table(coverage_rows, [176, 176, 176]),
        p(f"The pilot spans {min(row['year'] for row in pilot['year_coverage'])}-{max(row['year'] for row in pilot['year_coverage'])}; <b>{pilot['pilot_2019_2021_pairs']}</b> pairs are from 2019-2021. The original plan requested 100-150 pairs in 2019-2021. Coverage over a longer date range does not satisfy that same criterion.", "SmallCustom"),
        p("The full study requires a fresh historical population at every year start. The implemented selector uses prior 60-session mean dollar volume, at least 40 valid observations, one most-liquid security per issuer and up to 500 issuers. Later delistings stay in the selected cohort [3].", "SmallCustom"),
    ])
    feature_rows = [["Text measure", "Observed n", "Median", "10th / 90th percentile"]]
    for key, title in [("current_tokens", "Current section tokens"), ("log_length_change", "Log length change"),
                       ("jaccard_distance", "Jaccard distance"), ("tfidf_cosine_distance", "TF-IDF cosine distance")]:
        s = pilot["feature_summaries"][key]
        feature_rows.append([title, s["observations"], f"{s['median']:.4g}", f"{s['p10']:.4g} / {s['p90']:.4g}"])
    pages.append([
        p("2. What changed in the text?", "SectionCustom"),
        p("Length change measures expansion or contraction in the number of alphabetic tokens. Jaccard distance measures turnover in distinct words. TF-IDF cosine distance weights changes using vocabulary fitted on strictly earlier acceptance years. None is a risk forecast by itself."),
        img(figures[1], 528), Spacer(1, 8), table(feature_rows, [172, 67, 90, 199]),
        p(f"The first {pilot['feature_summaries']['tfidf_cosine_distance']['missing']} pairs have no prior pilot year from which to fit vocabulary, so their TF-IDF values are explicitly unavailable. The remaining {pilot['feature_summaries']['tfidf_cosine_distance']['observations']} distances use earlier years only. This descriptive vocabulary policy does not substitute for the final model's label-maturity filter.", "SmallCustom"),
        p("Interpretation limits", "SubCustom"),
        p("Small cosine distances can coexist with meaningful additions to a long section. Token-set distances ignore word order; length does not distinguish a new hazard from added explanation. These summaries justify checking individual passages, not claiming that a model predicts returns."),
        p("Example selection is independent of outcomes: the checkpoint selects the smallest SHA-256 of seed and accession within each year, then exposes the source link and a 12-word opening. No largest-return or best-performing example was selected."),
    ])
    pages.append([
        p("3. Timing and audit evidence", "SectionCustom"),
        p("For an accepted filing, convert the SEC timestamp to New York time. The reference session is the second XNYS session strictly after its acceptance date. Controls end at the preceding close; the forecast is made before the reference open. Returns begin after the reference close, so the reference day's daily return is excluded [3]."),
        table([["Stage", "Evidence and rule"], ["Prior controls", "60 exact sessions ending at the preceding close; 20/60 momentum, sample 20-session volatility, log USD capitalization and dated industry"],
               ["Return label", "Product of 1 + daily stock return over the next 20 sessions, minus the same compounded value-weighted market return"],
               ["Terminal events", "Dividends and delisting included once; cash proceeds earn zero after the terminal day while benchmark returns continue"],
               ["Missing inputs", "Unexplained missing sessions, ambiguous security IDs and absent historical snapshots are exclusions or errors; they are never filled with zero"]], [117, 411]),
        p("Rebuilt evidence", "SubCustom"),
        p(f"The source audit records {pilot['source_audit_passes']} passing filings and {pilot['reference_resolutions']} registered reference resolutions. It preserves {pilot['timestamp_disagreements']} differences between the API-encoded timestamp and original SGML header. The header controls the event date; dissemination time remains an explicit unverified assumption [4]."),
        p(f"The matching saved arithmetic receipt records {arithmetic['qa_cases_calculated']} calculated cases and {arithmetic['qa_cases_blocked']} blocked cases, independently reconciled within {arithmetic['arithmetic_tolerance']:.0e}; the maximum absolute difference is {arithmetic['independent_arithmetic_max_abs_error']:.3g}. The fixed {arithmetic['selected_trace_cases']}-trace packet and WFM cash-continuation case remain available. These checks establish arithmetic consistency for candidate mappings, not approval of those mappings [5]."),
        p(f"The matched receipts record {pilot['human_filing_reviews']} completed human filing reviews and {arithmetic['human_trace_reviews_passed']} passing human trace reviews. There are {arithmetic['candidate_cases_with_header_cik_difference']} candidate events with a header-CIK difference and {arithmetic['candidate_cases_with_unresolved_open_end']} links with unresolved open-end markers. These remain M5/M6 completion requirements [5].", "SmallCustom"),
    ])
    pages.append([
        p("4. Model selection and final access", "SectionCustom"),
        img(figures[2]),
        p("The primary comparison is ridge regression with market controls versus the same regression with all three text-change measures. Each model selects its penalty from 0.1, 1, 10 and 100 by pooled development MSE over six expanding annual folds. This is eight primary configurations, with identical validation observations [3]."),
        p("The freeze binds development data, predictions, selected penalties, exclusions, source and review evidence, preprocessing code, the Git commit and secondary specifications. Final features and final targets occupy separate files. Final targets are parsed only after the prerequisite and fingerprint checks pass."),
        p("For each 2022-2025 acceptance year, the final evaluator refits using earlier events whose label ends strictly precede that year's first prediction. Earlier final-year labels may enter later annual refits automatically under the frozen procedure. Human retuning after final access is prohibited."),
        p("Primary score and uncertainty", "SubCustom"),
        p("The score is 1 - SSE(controls + text) / SSE(controls), computed on identical observations. A positive value means lower squared error for the augmented model. The paired bootstrap resamples consecutive three-month reference-month blocks, preserving all firms within a month, with 2,000 draws and a six-month sensitivity."),
        p("Four final years contain limited independent time information. The interval is approximate and conditional on the frozen fitted procedure. An undefined zero-baseline-error case is reported explicitly. Forecast accuracy does not establish profitable trading."),
    ])
    pages.append([
        p("5. Robustness and failure analysis", "SectionCustom"),
        table([["Check", "Frozen implementation / interpretation"],
          ["Year and month", "Acceptance-year scores and reference-month Spearman correlations, with missing, small and constant groups reported"],
          ["Leave one year out", "Omit each year from the same frozen predictions; do not retrain using later years"],
          ["Feature ablations", "Six nonempty proper subsets of the three text features, with penalties selected on development data only; length-only is included"],
          ["Reference delays", "Rebuild 1-, 2- and 5-session controls and labels independently from sources; check availability separately; report both own and common event sets"],
          ["Size and industry", "Prior-close covariates and predeclared USD size cutpoints; display small-group limitations"],
          ["Largest errors", "Source-linked descriptive case review; no post-result feature selection"],
          ["Paragraph changes", "Conservative additions, removals, rewording and relocation categories; descriptive until a separate forecast rule is frozen"]], [125, 403]),
        p("The 2020 disclosure-rule transition", "SubCustom"),
        p("The SEC's 2020 amendments added a summary requirement for long risk-factor sections and relevant-heading requirements [2]. Changes in structure can change text metrics without equivalent changes in economic risk. The declared sensitivity inspects transition-period examples on development data and reports diagnostics without choosing a new primary specification."),
        p("No empirical robustness conclusion exists yet. The software reports negative, undefined and unavailable checks as such. Empty sections in the final results are not evidence of a null finding.", "SmallCustom"),
    ])
    test_count = verified.get("tests_passed", "See verification receipt")
    pages.append([
        p("6. Reproduction and build verification", "SectionCustom"),
        p("The public package contains the locked Python environment, tests, an invented full-study demonstration, source-derived aggregate pilot exhibits, and explicit evidence contracts. Licensed market records and their event-level return values remain private."),
        table([["Evidence", "Recorded status"], ["Original test baseline", "196 passing tests before this implementation"],
               ["Current test run", test_count], ["Recovered SEC audit", f"{pilot['source_audit_passes']} / {pilot['filings']} automated checks; no blocking source differences"],
               ["Recovered candidate arithmetic", f"{arithmetic['qa_cases_calculated']} / {arithmetic['events']} independently reconciled; no identity approval inferred"],
               ["End-to-end demonstration", verified.get("full_demo_status", "Available through make reproduce-full; see run receipt")],
               ["Empirical final outcomes", "Not opened; no final score or confidence interval estimated"]], [178, 350]),
        p("Reproduction commands", "SubCustom"),
        p("<font face='Courier'>make reproduce-full</font><br/>Runs the frozen-protocol checks, integrity tests and the synthetic historical-universe-to-final-evaluation demonstration. Every generated fixture is marked synthetic."),
        p("<font face='Courier'>make pilot-checkpoint</font><br/>Rebuilds the SEC-only descriptive pilot from the private source checkpoint and a matching source audit."),
        p("<font face='Courier'>make research-report</font><br/>Rebuilds the figures and this progress report from saved public aggregate pilot evidence and the verification receipt."),
        p("Code and drafting were co-developed with Codex. Automated and assistant checks remain distinct from a person's review and an independent reproduction. A reviewer should challenge timestamp assumptions, exclusion mechanisms, and the interpretation of every reported quantity."),
    ])
    pages.append([
        p("7. Completion criteria and sources", "SectionCustom"),
        table([["Milestone", "Remaining empirical completion requirement"],
          ["6 - Pilot checkpoint", "Reviewed source/identity evidence, controls-only smoke on approved 2019-2021 rows, and another person's reproduction"],
          ["7 - Full dataset", "Full historical listing/liquidity/link/return exports and filing ingestion; second 30-pair audit; explained coverage by year"],
          ["8 - Model freeze", "Run development on the approved full dataset; freeze exact evidence, penalties, code and secondary specification"],
          ["9 - Final evaluation", "Execute the frozen 2022-2025 evaluation once after all access gates pass"],
          ["10 - Robustness", "Execute declared checks on the frozen empirical predictions and audit failure cases"],
          ["11 - Public research package", "Replace pending results with actual estimates, complete independent reproduction, and publish the final interpretation"]], [147, 381]),
        p("Semantic secondary comparator", "SubCustom"),
        p("A separate MiniLM checkpoint is pinned by revision and weight hash. Its observed revision is dated 2026, so the comparator is explicitly retrospective. Verified pretraining and fine-tuning cutoffs are unavailable. The encoder processes every token in non-overlapping chunks and records zero truncation; manual unchanged/reworded/new-risk checks remain pending [6].", "SmallCustom"),
        p("Sources and audit trail", "SubCustom"),
        p('[1] Cohen, Malloy and Nguyen (2020), <i>Lazy Prices</i>, Journal of Finance 75(3). <link href="https://doi.org/10.1111/jofi.12885">doi.org/10.1111/jofi.12885</link><br/>'
          '[2] SEC (26 August 2020), Regulation S-K amendments. <link href="https://www.sec.gov/newsroom/press-releases/2020-192">sec.gov/newsroom/press-releases/2020-192</link><br/>'
          f'[3] <link href="{repository}/blob/main/protocol.md">Frozen protocol v1.0.0</link> and configs/protocol.json.<br/>'
          f'[4] <link href="{repository}/blob/main/reports/milestone_04.json">Milestone 04 source audit</link>; pilot_checkpoint/pilot_checkpoint.json.<br/>'
          f'[5] <link href="{repository}/blob/main/reports/pilot_arithmetic_summary.json">Pilot arithmetic receipt</link>; review_followup_summary.json.<br/>'
          '[6] <link href="https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/tree/1110a243fdf4706b3f48f1d95db1a4f5529b4d41">Pinned MiniLM checkpoint</link>; configs/semantic_retrospective.json.', "SmallCustom"),
    ])
    def build(filename, selected):
        story = []
        for i, page in enumerate(selected):
            if i:
                story.append(PageBreak())
            story.extend(page)
        doc = SimpleDocTemplate(str(out / filename), pagesize=(612, 792), rightMargin=42,
                                leftMargin=42, topMargin=43, bottomMargin=51,
                                title="Disclosure Drift - Research Progress", author="Michael Baffour Awuah")
        doc.build(story, onFirstPage=footer, onLaterPages=footer)
    # Flowables are rebuilt on each invocation; each PDF uses its own copies.
    import copy
    build("Research_Progress_Report.pdf", copy.deepcopy(pages))
    build("Pilot_Checkpoint_Report.pdf", copy.deepcopy(pages[:4]))
    result = {"report_type": "research_progress_not_final_empirical_result", "empirical_result_estimated": False,
              "figures": [str(path.relative_to(out)) for path in figures],
              "reports": ["Research_Progress_Report.pdf", "Pilot_Checkpoint_Report.pdf"],
              "input_sha256": {"pilot_checkpoint": hashlib.sha256((root / "pilot_checkpoint.json").read_bytes()).hexdigest(),
                  "pilot_arithmetic_summary": hashlib.sha256(arithmetic_raw).hexdigest(),
                  "review_followup_summary": hashlib.sha256(followup_raw).hexdigest()},
              "verification_sha256": hashlib.sha256(Path(verification).read_bytes()).hexdigest() if verification else None}
    result["report_sha256"] = {name: hashlib.sha256((out / name).read_bytes()).hexdigest() for name in result["reports"]}
    (out / "report_receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
