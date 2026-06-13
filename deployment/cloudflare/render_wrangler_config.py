from __future__ import annotations

import argparse
import os
import re
import tomllib
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_BASE_CONFIG = Path(__file__).with_name("wrangler.toml")
DEFAULT_OUTPUT = Path(__file__).with_name("wrangler.generated.toml")
PLACEHOLDER_ACCOUNT_ID = "replace-with-cloudflare-account-id"
DEFAULT_ROUTE = "gtm-dev.knowledge2.ai"
CLOUDFLARE_API_TOKEN_PREFIX = "cf" + "at_"


class ConfigError(ValueError):
    pass


def render_config(
    base_config: Path = DEFAULT_BASE_CONFIG,
    *,
    account_id: str | None = None,
    route: str | None = None,
) -> str:
    config = tomllib.loads(base_config.read_text(encoding="utf-8"))
    selected_account_id = _valid_account_id(account_id or os.environ.get("CLOUDFLARE_ACCOUNT_ID", ""))
    selected_route = _valid_route(route or os.environ.get("ICP_CLOUDFLARE_ROUTE", DEFAULT_ROUTE))

    config["account_id"] = selected_account_id
    config.setdefault("vars", {})["ICP_DEPLOYMENT_MODE"] = "seeded-worker"
    routes = config.get("routes")
    if not isinstance(routes, list) or not routes:
        raise ConfigError("base wrangler config must contain at least one route")
    if not isinstance(routes[0], dict):
        raise ConfigError("base wrangler route must be a table")
    routes[0]["pattern"] = selected_route

    rendered = _to_toml(config)
    if PLACEHOLDER_ACCOUNT_ID in rendered:
        raise ConfigError("generated config still contains placeholders")
    if CLOUDFLARE_API_TOKEN_PREFIX in rendered:
        raise ConfigError("generated config must not contain Cloudflare API tokens")
    return rendered


def write_config(
    output: Path = DEFAULT_OUTPUT,
    *,
    base_config: Path = DEFAULT_BASE_CONFIG,
    account_id: str | None = None,
    route: str | None = None,
) -> Path:
    rendered = render_config(base_config, account_id=account_id, route=route)
    output.write_text(rendered, encoding="utf-8")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a sanitized Cloudflare Wrangler config from environment variables.")
    parser.add_argument("--base-config", type=Path, default=DEFAULT_BASE_CONFIG)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--account-id", default=None, help="Cloudflare account ID. Defaults to CLOUDFLARE_ACCOUNT_ID.")
    parser.add_argument("--route", default=None, help="Custom domain route. Defaults to ICP_CLOUDFLARE_ROUTE or gtm-dev.knowledge2.ai.")
    args = parser.parse_args(argv)
    path = write_config(
        args.out,
        base_config=args.base_config,
        account_id=args.account_id,
        route=args.route,
    )
    print(path)
    return 0


def _valid_account_id(value: str) -> str:
    cleaned = value.strip()
    if cleaned.startswith(CLOUDFLARE_API_TOKEN_PREFIX):
        raise ConfigError("CLOUDFLARE_ACCOUNT_ID must be an account ID, not an API token")
    if not re.fullmatch(r"[a-fA-F0-9]{32}", cleaned):
        raise ConfigError("CLOUDFLARE_ACCOUNT_ID must be a 32-character hex account ID")
    return cleaned


def _valid_route(value: str) -> str:
    cleaned = value.strip()
    parsed = urlparse(cleaned)
    if parsed.scheme or parsed.path not in {"", cleaned} or "/" in cleaned:
        raise ConfigError("ICP_CLOUDFLARE_ROUTE must be a hostname, not a URL or path")
    if not cleaned or "." not in cleaned:
        raise ConfigError("ICP_CLOUDFLARE_ROUTE must be a hostname")
    return cleaned


def _to_toml(config: dict[str, object]) -> str:
    lines = [
        f"name = {_quote(str(config['name']))}",
        f"main = {_quote(str(config['main']))}",
        f"compatibility_date = {_quote(str(config['compatibility_date']))}",
        f"account_id = {_quote(str(config['account_id']))}",
        f"workers_dev = {_bool(config.get('workers_dev', False))}",
        "",
    ]

    assets = config.get("assets", {})
    if isinstance(assets, dict):
        lines.append(
            "assets = { "
            f"directory = {_quote(str(assets.get('directory', '')))}, "
            f"binding = {_quote(str(assets.get('binding', 'ASSETS')))}"
            " }"
        )
        lines.append("")

    routes = config.get("routes", [])
    if isinstance(routes, list) and routes:
        lines.append("routes = [")
        for route in routes:
            if isinstance(route, dict):
                lines.append(
                    "  { "
                    f"pattern = {_quote(str(route.get('pattern', '')))}, "
                    f"custom_domain = {_bool(route.get('custom_domain', True))}"
                    " }"
                )
        lines.append("]")
        lines.append("")

    triggers = config.get("triggers", {})
    if isinstance(triggers, dict):
        crons = triggers.get("crons", [])
        if isinstance(crons, list) and crons:
            lines.append("[triggers]")
            lines.append("crons = [" + ", ".join(_quote(str(item)) for item in crons) + "]")
            lines.append("")

    kv_namespaces = config.get("kv_namespaces", [])
    if isinstance(kv_namespaces, list):
        for namespace in kv_namespaces:
            if isinstance(namespace, dict):
                lines.append("[[kv_namespaces]]")
                lines.append(f"binding = {_quote(str(namespace.get('binding', '')))}")
                lines.append(f"id = {_quote(str(namespace.get('id', '')))}")
                lines.append("")

    vars_config = config.get("vars", {})
    if isinstance(vars_config, dict):
        lines.append("[vars]")
        for key, value in vars_config.items():
            lines.append(f"{key} = {_quote(str(value))}")
        lines.append("")

    secrets = config.get("secrets", {})
    if isinstance(secrets, dict):
        required = secrets.get("required", [])
        if not isinstance(required, list):
            required = []
        lines.append("[secrets]")
        lines.append("required = [" + ", ".join(_quote(str(item)) for item in required) + "]")

    return "\n".join(lines).rstrip() + "\n"


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _bool(value: object) -> str:
    return "true" if bool(value) else "false"


if __name__ == "__main__":
    raise SystemExit(main())
