from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from icp_engine import seed_defaults
from icp_engine.app_store import AppStore
from icp_engine.tenant import Branding, K2Settings, TenantConfig


class TenantConfigTest(unittest.TestCase):
    def test_default_tenant_reproduces_seeded_values(self) -> None:
        config = TenantConfig.default()
        self.assertEqual(config.tenant_id, "knowledge2")
        self.assertEqual(config.criteria_markdown, seed_defaults.SEEDED_CRITERIA_MARKDOWN)
        self.assertEqual(config.default_settings, seed_defaults.SEEDED_SETTINGS)
        self.assertEqual(config.prompts, seed_defaults.SEEDED_PROMPTS)
        self.assertEqual(config.query_profiles, seed_defaults.SEEDED_QUERY_PROFILES)
        self.assertEqual(config.k2.project_name, "Knowledge2 ICP GTM")
        self.assertEqual(config.branding.service_name, "Knowledge2 ICP")

    def test_default_tenant_data_is_isolated_from_seed_constants(self) -> None:
        # Mutating a tenant's copy must not leak back into the shared seed defaults.
        config = TenantConfig.default()
        config.default_settings["max_companies"] = 9999
        config.prompts.append({"id": "scratch"})
        self.assertEqual(seed_defaults.SEEDED_SETTINGS["max_companies"], 50)
        self.assertTrue(all(item.get("id") != "scratch" for item in seed_defaults.SEEDED_PROMPTS))

    def test_appstore_defaults_to_knowledge2_tenant(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp) / "state", Path(tmp) / "missing-icp.md")
            self.assertEqual(store.tenant_config.tenant_id, "knowledge2")
            self.assertIn("Seeded ICP Criteria", store.load_criteria()["markdown"])
            self.assertEqual(store.load_settings()["max_companies"], 50)

    def test_custom_tenant_overrides_criteria_settings_and_prompts(self) -> None:
        custom = TenantConfig(
            tenant_id="acme",
            criteria_markdown="# Acme ICP\n\nMid-market logistics platforms.\n",
            default_settings={**seed_defaults.SEEDED_SETTINGS, "max_companies": 12, "default_query": "acme logistics"},
            prompts=[{"id": "acme-discovery", "label": "Discovery", "kind": "search", "text": "acme query"}],
            branding=Branding(service_name="Acme GTM", user_agent="AcmeGTM/0.1"),
            k2=K2Settings(project_name="Acme GTM", workspace_namespace="acme-gtm"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp) / "state", Path(tmp) / "missing-icp.md", tenant_config=custom)

            self.assertEqual(store.tenant_config.tenant_id, "acme")
            self.assertIn("Acme ICP", store.load_criteria()["markdown"])
            self.assertNotIn("Seeded ICP Criteria", store.load_criteria()["markdown"])
            self.assertEqual(store.load_settings()["max_companies"], 12)
            self.assertEqual(store.load_settings()["default_query"], "acme logistics")
            self.assertEqual([item["id"] for item in store.load_prompts()], ["acme-discovery"])
            self.assertEqual(store.tenant_config.branding.service_name, "Acme GTM")
            self.assertEqual(store.tenant_config.k2.workspace_namespace, "acme-gtm")

    def test_custom_provider_limits_drive_policy(self) -> None:
        custom_settings = {
            **seed_defaults.SEEDED_SETTINGS,
            "provider_limits": {
                **seed_defaults.SEEDED_SETTINGS["provider_limits"],
                "daily": {**seed_defaults.SEEDED_SETTINGS["provider_limits"]["daily"], "research": 7},
            },
        }
        custom = TenantConfig(tenant_id="acme", default_settings=custom_settings)
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp) / "state", Path(tmp) / "missing-icp.md", tenant_config=custom)
            self.assertEqual(store.provider_policy()["daily"]["research"], 7)


if __name__ == "__main__":
    unittest.main()
