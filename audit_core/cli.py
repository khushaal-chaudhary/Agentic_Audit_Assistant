from __future__ import annotations

import argparse
import json

from .engine import analyze_dossier


def main() -> None:
    parser = argparse.ArgumentParser(description="Run evidence-first dossier checks")
    subparsers = parser.add_subparsers(dest="command", required=True)
    analyze = subparsers.add_parser("analyze")
    analyze.add_argument("path")
    args = parser.parse_args()
    if args.command == "analyze":
        report = analyze_dossier(args.path)
        print(json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

