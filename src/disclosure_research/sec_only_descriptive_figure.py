"""Pure, deterministic publication-only SVG plot of audited SEC descriptives.

The plot shows a 34-issuer purposive original-filing balanced panel, not the
frozen investment universe. No hidden issuer identifiers or model outcomes.
"""

import math

STATUS = "EXPLORATORY_SEC_ONLY_DISCLOSURE_DRIFT_BALANCED_PANEL_NOT_RETURN_PREDICTION"


def render_sec_only_mean_drift_svg(summary):
    if (
        summary.get("status") != STATUS
        or summary.get("balanced_issuer_count") != 34
        or summary.get("market_returns_or_CRSP_identity_data_read") is not False
        or summary.get("model_ready") is not False
        or summary.get("final_period_opened") is not False
    ):
        raise ValueError("Cannot plot unsupported or allegedly approved empirical SEC results")
    annual = summary.get("balanced_2019_2021_year_coverage", [])
    if (
        len(annual) != 3
        or [x["year"] for x in annual] != [2019, 2020, 2021]
        or any(x["issuers"] != 34 for x in annual)
    ):
        raise ValueError("Expected complete 2019-2021 paired SEC descriptive panel")
    values = []
    for row in annual:
        value = row["jaccard_distance"]["mean"]
        if not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 0.20:
            raise ValueError("Mean Jaccard outside this figure's original source plotting domain")
        values.append(value)
    width, height = 720, 440
    left, right = 112, 645
    top, bottom = 108, 314
    x = [174, 380, 586]
    y = [bottom - v / 0.20 * (bottom - top) for v in values]
    axis = []
    for tick in range(0, 5):
        val = tick * 0.05
        pixel = bottom - val / 0.20 * (bottom - top)
        axis.append(
            f'<line x1="{left}" y1="{pixel:.1f}" x2="{right}" y2="{pixel:.1f}" stroke="#d4dce3"/>'
            f'<text x="99" y="{pixel+5:.1f}" font-size="13" text-anchor="end" fill="#506072">{val:.2f}</text>'
        )
    labels = []
    for year, val, px, py in zip((2019, 2020, 2021), values, x, y, strict=True):
        labels.append(
            f'<circle cx="{px}" cy="{py:.1f}" r="7" fill="#24384e" stroke="#ffffff" stroke-width="2"/>'
            f'<text x="{px}" y="{py-16:.1f}" font-size="14" font-weight="600" text-anchor="middle" '
            f'fill="#24384e">{val:.4f}</text>'
            f'<text x="{px}" y="{bottom+25}" font-size="15" text-anchor="middle" fill="#344b61">{year}</text>'
        )
    points = " ".join(f"{px},{py:.1f}" for px, py in zip(x, y, strict=True))
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        'viewBox="0 0 720 440" role="img" aria-labelledby="chart-title chart-description">'
        '<title id="chart-title">Original SEC Item 1A Jaccard distance, balanced 2019–2021</title>'
        '<desc id="chart-description">Average year-over-year Item 1A vocabulary turnover in the '
        'same 34 purposively selected issuers; exploratory, not representative or predictive.</desc>'
        '<rect width="720" height="440" rx="15" fill="#ffffff"/>'
        '<text x="38" y="44" font-size="21" font-weight="650" fill="#1f2f40">'
        'SEC Item 1A vocabulary turnover</text>'
        '<text x="38" y="68" font-size="14" fill="#5b6b78">'
        '34 matching issuers · 2019–2021 original filing comparisons</text>'
        + "".join(axis)
        + f'<line x1="{left}" y1="{top}" x2="{left}" y2="{bottom}" stroke="#8696a5" stroke-width="1.4"/>'
        + f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="#8696a5" stroke-width="1.4"/>'
        + f'<polyline points="{points}" fill="none" stroke="#24384e" stroke-width="3" stroke-linecap="round"/>'
        + "".join(labels)
        + '<text x="380" y="366" font-size="13" text-anchor="middle" fill="#405264">'
        'Mean Jaccard distance of consecutive original Risk Factors token sets</text>'
        + '<text x="38" y="400" font-size="11" fill="#526273">'
        'Exploratory SEC-only parser sample, not a historical investable universe.</text>'
        + '<text x="38" y="418" font-size="11" fill="#526273">'
        'No stock returns, causal claims or sealed final-evaluation results.</text>'
        + '</svg>'
    )
