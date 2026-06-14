"""Config cluster: prompts, settings, lists, query profiles, and saved lead views."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from ._helpers import (
    _bounded_int,
    _clean_profile_filters,
    _coerce_bool,
    _deep_merge_provider_limits,
    _load_json_file,
    _normalize_provider_limits,
    now_iso,
    stable_hash,
)


class ConfigMixin:
    def load_prompts(self) -> list[dict[str, Any]]:
        self.ensure()
        value = _load_json_file(self.prompts_path, list)
        if value is None:
            return [dict(item) for item in self.tenant_config.prompts]
        return [item for item in value if isinstance(item, dict)]

    def load_settings(self) -> dict[str, Any]:
        self.ensure()
        seeded_settings = self.tenant_config.default_settings
        value = _load_json_file(self.settings_path, dict)
        if value is None:
            return dict(seeded_settings)
        settings = {**seeded_settings, **value}
        settings["provider_limits"] = _deep_merge_provider_limits(
            seeded_settings.get("provider_limits", {}),
            settings.get("provider_limits", {}),
        )
        return settings

    def save_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.ensure()
        if not isinstance(payload, dict):
            raise ValueError("Settings payload must be an object.")
        current = self.load_settings()
        next_settings = deepcopy(current)
        for key in ("default_query", "employee_range"):
            if key in payload:
                next_settings[key] = " ".join(str(payload.get(key) or "").split())
        if "qualifier" in payload:
            qualifier = str(payload.get("qualifier") or "").strip().lower()
            if qualifier not in {"rules", "claude"}:
                raise ValueError("qualifier must be 'rules' or 'claude'.")
            next_settings["qualifier"] = qualifier
        if "discovery_provider" in payload:
            provider = str(payload.get("discovery_provider") or "").strip().lower()
            if provider not in {"auto", "perplexity", "serper", "duckduckgo"}:
                raise ValueError("discovery_provider must be 'auto', 'perplexity', 'serper', or 'duckduckgo'.")
            next_settings["discovery_provider"] = provider
        if "outreach_mode" in payload:
            outreach_mode = str(payload.get("outreach_mode") or "").strip().lower()
            if outreach_mode not in {"template", "claude"}:
                raise ValueError("outreach_mode must be 'template' or 'claude'.")
            next_settings["outreach_mode"] = outreach_mode
        if "mining_corpus" in payload:
            mining_corpus = str(payload.get("mining_corpus") or "").strip().lower()
            if mining_corpus not in {"auto", "candidate", "evidence", "prospect", "source", "criteria"}:
                raise ValueError("mining_corpus must be 'auto', 'candidate', 'evidence', 'prospect', 'source', or 'criteria'.")
            next_settings["mining_corpus"] = mining_corpus
        for key in ("fetch_website_evidence", "include_github_metadata", "use_apollo_enrichment", "use_serp_discovery"):
            if key in payload:
                next_settings[key] = _coerce_bool(payload[key], bool(current.get(key, False)))
        int_fields = {
            "max_companies": (1, 1000),
            "max_pages": (0, 100),
            "tier_a_threshold": (0, 100),
            "tier_b_threshold": (0, 100),
        }
        for key, (minimum, maximum) in int_fields.items():
            if key in payload:
                next_settings[key] = _bounded_int(payload[key], int(current.get(key) or minimum), minimum, maximum)
        if isinstance(payload.get("provider_limits"), dict):
            next_settings["provider_limits"] = _normalize_provider_limits(
                payload["provider_limits"],
                current.get("provider_limits", {}),
                self.tenant_config.default_settings.get("provider_limits", {}),
            )
        self.settings_path.write_text(json.dumps(next_settings, indent=2, sort_keys=True), encoding="utf-8")
        self.append_audit_event(
            "settings.saved",
            subject_type="settings",
            subject_id="workspace",
            details={"keys": sorted(payload.keys())},
        )
        return self.load_settings()

    def load_lists(self) -> dict[str, Any]:
        self.ensure()
        seeded_lists = deepcopy(self.tenant_config.lists)
        value = _load_json_file(self.lists_path, dict)
        if value is None:
            return seeded_lists
        return {**seeded_lists, **value}

    def list_query_profiles(self) -> list[dict[str, Any]]:
        self.ensure()
        value = _load_json_file(self.query_profiles_path, list)
        if value is None:
            return [deepcopy(item) for item in self.tenant_config.query_profiles]
        return [item for item in value if isinstance(item, dict)]

    def save_query_profile(self, profile: dict[str, Any]) -> dict[str, Any]:
        self.ensure()
        if not isinstance(profile, dict):
            raise ValueError("Query profile payload must be an object.")
        name = " ".join(str(profile.get("name") or "").split())
        if not name:
            raise ValueError("Query profile name is required.")
        queries = [" ".join(str(item).split()) for item in profile.get("queries") or [] if str(item).strip()]
        filters = _clean_profile_filters(profile.get("filters"))
        now = now_iso()
        profile_id = str(profile.get("id") or "").strip() or stable_hash(f"{now}:{name.lower()}")
        existing = next((item for item in self.list_query_profiles() if item.get("id") == profile_id), {})
        record = {
            "id": profile_id,
            "name": name,
            "description": " ".join(str(profile.get("description") or "").split()),
            "queries": queries,
            "filters": filters,
            "created_at": str(existing.get("created_at") or now),
            "updated_at": now,
        }
        profiles = [item for item in self.list_query_profiles() if item.get("id") != profile_id]
        profiles.append(record)
        self.query_profiles_path.write_text(
            json.dumps(sorted(profiles, key=lambda item: str(item.get("name"))), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        self.append_audit_event(
            "query_profile.saved",
            subject_type="query_profile",
            subject_id=profile_id,
            details={"name": name, "filter_count": len(filters), "query_count": len(queries)},
        )
        return record

    def delete_query_profile(self, profile_id: str) -> None:
        self.ensure()
        clean_id = str(profile_id or "").strip()
        if not clean_id:
            raise ValueError("Query profile id is required.")
        profiles = [item for item in self.list_query_profiles() if item.get("id") != clean_id]
        self.query_profiles_path.write_text(
            json.dumps(sorted(profiles, key=lambda item: str(item.get("name"))), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        self.append_audit_event(
            "query_profile.deleted",
            subject_type="query_profile",
            subject_id=clean_id,
            details={},
        )

    def list_lead_views(self) -> list[dict[str, Any]]:
        self.ensure()
        value = _load_json_file(self.lead_views_path, list)
        return [item for item in value or [] if isinstance(item, dict) and item.get("name")]

    def save_lead_view(
        self,
        name: str,
        *,
        filters: dict[str, Any] | None = None,
        sort: dict[str, Any] | None = None,
        page_size: int | None = None,
    ) -> dict[str, Any]:
        self.ensure()
        clean_name = " ".join(name.strip().split())
        if not clean_name:
            raise ValueError("View name is required.")
        now = now_iso()
        views = self.list_lead_views()
        view_id = stable_hash(clean_name.lower())
        previous = next((item for item in views if item.get("id") == view_id), {})
        view = {
            "id": view_id,
            "name": clean_name,
            "filters": filters if isinstance(filters, dict) else {},
            "sort": sort if isinstance(sort, dict) else {"field": "score", "direction": "desc"},
            "page_size": max(10, min(int(page_size or previous.get("page_size") or 50), 500)),
            "created_at": str(previous.get("created_at") or now),
            "updated_at": now,
        }
        next_views = [item for item in views if item.get("id") != view_id]
        next_views.append(view)
        self.lead_views_path.write_text(json.dumps(sorted(next_views, key=lambda item: str(item.get("name"))), indent=2, sort_keys=True), encoding="utf-8")
        self.append_audit_event(
            "lead_view.saved",
            subject_type="lead_view",
            subject_id=view_id,
            details={"name": clean_name, "filters": view["filters"], "sort": view["sort"]},
        )
        return view
