from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_wrangler_config import ConfigError, DEFAULT_ROUTE, render_config


REQUIRED_ENV = [
    "CLOUDFLARE_ACCOUNT_ID",
    "ICP_ADMIN_TOKEN",
    "K2_API_KEY",
    "APOLLO_API_KEY",
]
CLOUDFLARE_TOKEN_ENV = ["CLOUDFLARE_API_TOKEN", "CF_API_TOKEN"]


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    status: str
    message: str

    @property
    def ok(self) -> bool:
        return self.status in {"ok", "warn"}


def run_preflight(env: Mapping[str, str] | None = None, *, check_wrangler: bool = True) -> list[PreflightCheck]:
    selected_env = env or os.environ
    checks: list[PreflightCheck] = []

    for name in REQUIRED_ENV:
        checks.append(_required_env_check(selected_env, name))

    token_name = next((name for name in CLOUDFLARE_TOKEN_ENV if selected_env.get(name, "").strip()), "")
    if token_name:
        checks.append(PreflightCheck("cloudflare_api_token", "ok", f"{token_name} is set."))
    else:
        checks.append(PreflightCheck("cloudflare_api_token", "fail", "Set CLOUDFLARE_API_TOKEN or CF_API_TOKEN for Wrangler deploys."))

    if selected_env.get("ICP_CLOUDFLARE_ROUTE", "").strip():
        checks.append(PreflightCheck("ICP_CLOUDFLARE_ROUTE", "ok", "Custom domain route is set."))
    else:
        checks.append(PreflightCheck("ICP_CLOUDFLARE_ROUTE", "warn", f"Route not set; generated config will use {DEFAULT_ROUTE}."))

    if check_wrangler:
        checks.append(
            PreflightCheck("wrangler", "ok", "Wrangler CLI found.")
            if shutil.which("wrangler")
            else PreflightCheck("wrangler", "fail", "Wrangler CLI is required for Cloudflare deploys.")
        )

    account_id = selected_env.get("CLOUDFLARE_ACCOUNT_ID", "")
    route = selected_env.get("ICP_CLOUDFLARE_ROUTE", DEFAULT_ROUTE)
    if account_id.strip():
        try:
            render_config(account_id=account_id, route=route)
        except ConfigError as exc:
            checks.append(PreflightCheck("wrangler_config", "fail", str(exc)))
        else:
            checks.append(PreflightCheck("wrangler_config", "ok", "Generated Wrangler config validates without embedding secrets."))
    else:
        checks.append(PreflightCheck("wrangler_config", "fail", "CLOUDFLARE_ACCOUNT_ID is required to render config."))

    return checks


def format_checks(checks: list[PreflightCheck]) -> str:
    lines = ["Cloudflare/K2/Apollo deploy preflight:"]
    for check in checks:
        marker = {"ok": "OK", "warn": "WARN", "fail": "FAIL"}.get(check.status, check.status.upper())
        lines.append(f"- [{marker}] {check.name}: {check.message}")
    if any(check.status == "fail" for check in checks):
        lines.append("Result: blocked until failed preflight items are fixed.")
    else:
        lines.append("Result: preflight passed.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate deploy prerequisites without printing secret values.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument("--skip-wrangler", action="store_true", help="Skip local Wrangler CLI lookup.")
    args = parser.parse_args(argv)

    checks = run_preflight(check_wrangler=not args.skip_wrangler)
    if args.json:
        print(json.dumps([asdict(check) for check in checks], indent=2, sort_keys=True))
    else:
        print(format_checks(checks))
    return 1 if any(check.status == "fail" for check in checks) else 0


def _required_env_check(env: Mapping[str, str], name: str) -> PreflightCheck:
    if env.get(name, "").strip():
        return PreflightCheck(name, "ok", "Set.")
    return PreflightCheck(name, "fail", "Missing.")


if __name__ == "__main__":
    raise SystemExit(main())
