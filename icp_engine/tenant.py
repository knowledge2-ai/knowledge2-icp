"""Tenant configuration object.

Everything tenant-specific (ICP criteria, default settings, prompts, query
profiles, seed lists, K2 workspace identity, and branding) is collected here so
the engine can serve more than one tenant. ``TenantConfig.default()`` reproduces
the original Knowledge2/K2 values by sourcing the existing ``seed_defaults``
constants, so the default path is behavior-preserving — code that reads
``store.tenant_config.*`` instead of importing ``SEEDED_*`` directly behaves
identically until a non-default tenant is supplied.
"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import seed_defaults


TENANTS_DIR = Path(__file__).parent / "tenants"


@dataclass(frozen=True)
class Branding:
    """User-facing identity strings (wired through the web/CLI layers)."""

    service_name: str = "Knowledge2 ICP"
    # enrichment
    user_agent: str = "Knowledge2ICP/0.1 (+https://knowledge2.ai)"
    # perplexity, discovery
    discovery_user_agent: str = "Knowledge2ICPDiscovery/0.1 (+https://knowledge2.ai)"
    # apollo, github, k2_client
    api_user_agent: str = "Knowledge2ICP/0.1"
    server_version: str = "Knowledge2ICPWeb/0.1"
    auth_realm: str = "knowledge2-icp"
    cli_description: str = "Knowledge2 ICP qualification CLI"


@dataclass(frozen=True)
class K2Settings:
    """K2 workspace identity for corpus sync and provisioning."""

    project_name: str = "Knowledge2 ICP GTM"
    workspace_namespace: str = "knowledge2-icp"
    base_url: str = "https://api.knowledge2.ai"
    source_uri_prefix: str = "inline://knowledge2-icp"


@dataclass(frozen=True)
class TenantConfig:
    """All tenant-specific configuration, injected at ``AppStore`` construction.

    Heavy data fields default (via factories) to the seeded Knowledge2 values so
    ``TenantConfig()`` is the original single-tenant behavior.
    """

    tenant_id: str = "knowledge2"
    criteria_markdown: str = seed_defaults.SEEDED_CRITERIA_MARKDOWN
    default_settings: dict[str, Any] = field(
        default_factory=lambda: deepcopy(seed_defaults.SEEDED_SETTINGS)
    )
    prompts: list[dict[str, Any]] = field(
        default_factory=lambda: deepcopy(seed_defaults.SEEDED_PROMPTS)
    )
    query_profiles: list[dict[str, Any]] = field(
        default_factory=lambda: deepcopy(seed_defaults.SEEDED_QUERY_PROFILES)
    )
    lists: dict[str, Any] = field(
        default_factory=lambda: deepcopy(seed_defaults.SEEDED_LISTS)
    )
    branding: Branding = field(default_factory=Branding)
    k2: K2Settings = field(default_factory=K2Settings)

    @classmethod
    def default(cls) -> "TenantConfig":
        """The built-in Knowledge2 tenant — preserves original behavior."""
        return cls()

    @classmethod
    def from_tenant_dir(cls, tenant_dir: Path) -> "TenantConfig":
        """Build a tenant config from a directory of data files + a tenant.json manifest."""
        manifest = json.loads((tenant_dir / "tenant.json").read_text(encoding="utf-8"))
        return cls(
            tenant_id=str(manifest["tenant_id"]),
            criteria_markdown=(tenant_dir / "criteria.md").read_text(encoding="utf-8"),
            default_settings=json.loads((tenant_dir / "settings.json").read_text(encoding="utf-8")),
            prompts=json.loads((tenant_dir / "prompts.json").read_text(encoding="utf-8")),
            query_profiles=json.loads((tenant_dir / "query_profiles.json").read_text(encoding="utf-8")),
            lists=json.loads((tenant_dir / "lists.json").read_text(encoding="utf-8")),
            branding=Branding(**manifest.get("branding", {})),
            k2=K2Settings(**manifest.get("k2", {})),
        )

    @classmethod
    def load(cls, tenant_id: str) -> "TenantConfig":
        """Resolve a tenant by id. knowledge2 keeps its built-in (worker-bundled account) path."""
        clean = (tenant_id or "knowledge2").strip() or "knowledge2"
        # knowledge2 is special-cased: its account universe lives in the worker-bundled
        # web_assets/seed-companies.json (merged in seed_defaults), not in its tenant dir,
        # so it routes through default() rather than the generic file loader.
        if clean == "knowledge2":
            return cls.default()
        return cls.from_tenant_dir(TENANTS_DIR / clean)
