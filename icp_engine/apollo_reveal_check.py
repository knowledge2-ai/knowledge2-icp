"""Smoke test: does Apollo actually return real PII on this plan?

The prospect pipeline shows empty name/email until Apollo People-Match reveals a
real personal email (`reveal_personal_emails=true`, see `apollo.py`). Earlier live
validation found the people search returned no PII (plan-gated). This CLI answers
the question with one small, credit-cheap call so we know before promising filled
contacts behind the SSO wall.

    APOLLO_API_KEY=... python -m icp_engine.apollo_reveal_check --domain stripe.com \
        --title "chief product officer" --limit 3

By default it MASKS the returned names/emails (presence is what we're testing, and
the output may scroll into logs); pass --reveal to print them in full.
"""

from __future__ import annotations

import argparse
import os
from typing import Any

from .apollo import ApolloClient


def mask_email(email: str) -> str:
    if not email or "@" not in email:
        return email or ""
    local, _, domain = email.partition("@")
    head = local[0] if local else ""
    return f"{head}***@{domain}"


def mask_name(name: str) -> str:
    parts = [p for p in (name or "").split() if p]
    return ".".join(p[0].upper() for p in parts) + ("." if parts else "")


def summarize(people: list[dict[str, Any]], *, reveal: bool) -> dict[str, Any]:
    """Reduce Apollo people records to a privacy-aware reveal report (no network)."""
    rows = []
    revealed = 0
    for person in people:
        email = str(person.get("email") or "")
        name = str(person.get("name") or "")
        has_email = bool(email)
        revealed += 1 if has_email else 0
        rows.append(
            {
                "name": (name if reveal else mask_name(name)) or "(no name)",
                "title": person.get("title") or "",
                "email": (email if reveal else mask_email(email)) or "(none)",
                "email_status": person.get("email_status") or "",
                "revealed": has_email,
            }
        )
    return {"total": len(people), "revealed": revealed, "rows": rows}


def _verdict(total: int, revealed: int) -> str:
    if total == 0:
        return "NO RESULTS: the people search returned 0 contacts — widen the title or check the domain."
    if revealed == 0:
        return (
            f"NO PII: {total} contacts returned, 0 with a real email. People-Match did not "
            "reveal anything — the plan almost certainly gates personal-email reveal."
        )
    return (
        f"REVEAL WORKS: {revealed}/{total} contacts came back with a real personal email. "
        "PII reveal is viable on this plan."
    )


def run(*, domain: str, title: str | None, limit: int, reveal: bool) -> int:
    client = ApolloClient.from_env()
    if not client.configured:
        print("APOLLO_API_KEY is not set — export it and re-run. No call was made.")
        return 2
    titles = [title] if title else None
    result = client.search_people(domain=domain, titles=titles, per_page=limit)
    if result.get("status") != "ok":
        print(f"Apollo call did not succeed: {result.get('reason') or result.get('status')}")
        return 1
    people = result.get("people") or []
    report = summarize(people, reveal=reveal)
    print(f"\nApollo People-Match reveal check — domain={domain} title={title or 'default set'}")
    print(f"~credits spent: {min(report['total'], 10)} (one per matched contact)\n")
    for row in report["rows"]:
        flag = "✓" if row["revealed"] else "·"
        print(f"  [{flag}] {row['name']:<14} {row['title']:<28} {row['email']:<28} {row['email_status']}")
    print(f"\n{_verdict(report['total'], report['revealed'])}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check whether Apollo returns real PII on this plan.")
    parser.add_argument("--domain", required=True, help="Company domain to search, e.g. stripe.com")
    parser.add_argument("--title", default=None, help="A single person title to target (default: the persona title set).")
    parser.add_argument("--limit", type=int, default=3, help="Max contacts to match/reveal (default 3 — keeps credit cost low).")
    parser.add_argument("--reveal", action="store_true", help="Print full names/emails instead of masked.")
    args = parser.parse_args(argv)
    return run(domain=args.domain, title=args.title, limit=args.limit, reveal=args.reveal)


if __name__ == "__main__":
    raise SystemExit(main())
