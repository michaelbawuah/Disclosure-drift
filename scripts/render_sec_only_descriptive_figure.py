"""Render the published SEC-only balanced descriptive means as an SVG."""

import argparse
import json
from pathlib import Path

from disclosure_research.sec_only_descriptive_figure import render_sec_only_mean_drift_svg


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--summary", required=True)
    cli.add_argument("--output", required=True)
    args = cli.parse_args(argv)
    dst = Path(args.output)
    if dst.exists():
        raise ValueError("Cannot overwrite an existing SEC descriptive figure")
    summary = json.loads(Path(args.summary).read_text())
    svg = render_sec_only_mean_drift_svg(summary)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(svg + "\n", encoding="utf-8")
    print(f"Written {dst} ({dst.stat().st_size} bytes)")


if __name__ == "__main__":
    raise SystemExit(main())
