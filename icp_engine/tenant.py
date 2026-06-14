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

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from . import seed_defaults


@dataclass(frozen=True)
class Branding:
    """User-facing identity strings (wired through the web/CLI layers)."""

    service_name: str = "Knowledge2 ICP"
    user_agent: str = "Knowledge2ICP/0.1 (+https://knowledge2.ai)"
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
