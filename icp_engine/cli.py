from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from .enrichment import fetch_company_evidence
from .gemini import GeminiUnavailable, classify_with_gemini
from .models import CompanyInput
from .reporting import write_dossier, write_ranked_csv
from .scoring import score_company
from .tenant import Branding


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="icp", description=Branding().cli_description)
    subparsers = parser.add_subparsers(dest="command", required=True)
    qualify = subparsers.add_parser("qualify", help="Score companies from a CSV")
    qualify.add_argument("--input", required=True, type=Path, help="Input company CSV")
    qualify.add_argument("--out", required=True, type=Path, help="Output directory")
    qualify.add_argument("--use-gemini", action="store_true", help="Use Gemini-assisted classification")
    qualify.add_argument("--no-fetch", action="store_true", help="Skip public page fetching")
    qualify.add_argument("--max-pages", type=int, default=10, help="Max pages to fetch per company")
    qualify.add_argument("--max-attempts", type=int, default=None, help="Max fetch attempts per company")
    qualify.add_argument("--max-failures", type=int, default=None, help="Max failed fetches per company")
    qualify.add_argument("--timeout", type=float, default=8.0, help="HTTP timeout in seconds")

    args = parser.parse_args(argv)
    if args.command == "qualify":
        return _qualify(args)
    return 2


def _qualify(args: argparse.Namespace) -> int:
    companies = read_companies(args.input)
    args.out.mkdir(parents=True, exist_ok=True)
    cache_dir = args.out / "cache"
    results = []
    evidence_by_company = {}

    for company in companies:
        print(f"Scoring {company.company} ({company.domain})", file=sys.stderr)
        if args.no_fetch:
            evidence = []
            fetch_warnings = ["Public fetching skipped by --no-fetch."]
        else:
            evidence, fetch_warnings = fetch_company_evidence(
                company,
                cache_dir / _safe_name(company.company),
                timeout_seconds=args.timeout,
                max_pages=args.max_pages,
                max_attempts=args.max_attempts,
                max_failures=args.max_failures,
            )

        model_classification = None
        if args.use_gemini and evidence:
            try:
                model_classification = classify_with_gemini(company, evidence)
            except GeminiUnavailable as exc:
                fetch_warnings.append(f"Gemini disabled: {exc}")
            except Exception as exc:  # Keep batch scoring resilient.
                fetch_warnings.append(f"Gemini classification failed: {exc}")

        result = score_company(
            company,
            evidence,
            model_classification=model_classification,
            fetch_warnings=fetch_warnings,
        )
        results.append(result)
        evidence_by_company[company.company] = evidence

    write_ranked_csv(results, args.out / "ranked_companies.csv")
    write_dossier(results, evidence_by_company, args.out / "dossier.md")
    print(f"Wrote {args.out / 'ranked_companies.csv'}", file=sys.stderr)
    print(f"Wrote {args.out / 'dossier.md'}", file=sys.stderr)
    return 0


def read_companies(path: Path) -> list[CompanyInput]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = {"company", "domain"} - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"Input CSV missing required columns: {', '.join(sorted(missing))}")
        return [_row_to_company(row) for row in reader if row.get("company") and row.get("domain")]


def _row_to_company(row: dict[str, str]) -> CompanyInput:
    return CompanyInput(
        company=(row.get("company") or "").strip(),
        domain=(row.get("domain") or "").strip(),
        category=(row.get("category") or "").strip(),
        founded_year=_optional_int(row.get("founded_year")),
        employee_count=_optional_int(row.get("employee_count")),
        hq=(row.get("hq") or "").strip(),
        notes=(row.get("notes") or "").strip(),
    )


def _optional_int(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    try:
        return int(value.replace(",", "").strip())
    except ValueError:
        return None


def _safe_name(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-") or "company"


if __name__ == "__main__":
    raise SystemExit(main())
