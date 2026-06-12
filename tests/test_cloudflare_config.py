from __future__ import annotations

import importlib.util
import sys
import tomllib
import unittest
from pathlib import Path


class CloudflareConfigTest(unittest.TestCase):
    def test_worker_config_declares_assets_and_secret_names_only(self) -> None:
        path = Path("deployment/cloudflare/wrangler.toml")
        config = tomllib.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(config["assets"]["directory"], "../../icp_engine/web_assets")
        self.assertEqual(config["assets"]["binding"], "ASSETS")
        self.assertIn("K2_API_KEY", config["secrets"]["required"])
        self.assertIn("APOLLO_API_KEY", config["secrets"]["required"])
        self.assertIn("ICP_ADMIN_TOKEN", config["secrets"]["required"])
        self.assertEqual(config["vars"]["ICP_DEPLOYMENT_MODE"], "seeded-worker")
        self.assertEqual(config["vars"]["K2_BASE_URL"], "https://api-dev.knowledge2.ai")

        raw = path.read_text(encoding="utf-8")
        worker = Path("deployment/cloudflare/worker.js").read_text(encoding="utf-8")
        cloudflare_token_prefix = "cf" + "at_"
        self.assertNotRegex(raw, rf"{cloudflare_token_prefix}[A-Za-z0-9_-]+")
        self.assertNotRegex(worker, rf"{cloudflare_token_prefix}[A-Za-z0-9_-]+")
        self.assertNotRegex(raw, r"(K2_API_KEY|APOLLO_API_KEY|ICP_ADMIN_TOKEN)\s*=\s*[\"'][A-Za-z0-9_-]{12,}[\"']")
        self.assertIn('url.pathname === "/healthz"', worker)
        self.assertIn("authorizeApiRequest", worker)
        self.assertIn("ICP_ADMIN_TOKEN is required for K2 apply sync.", worker)
        self.assertIn("K2 apply token required.", worker)
        self.assertNotIn("Admin token required.", worker)
        self.assertIn("SEED_PROMPTS", worker)
        self.assertIn("handleApiRequest", worker)
        self.assertNotIn("proxyApiRequest", worker)
        self.assertIn("replace-with-cloudflare-account-id", raw)

    def test_generated_worker_config_uses_environment_values_without_committing_secrets(self) -> None:
        renderer = _load_renderer()
        rendered = renderer.render_config(
            account_id="0" * 32,
            route="gtm-dev.knowledge2.ai",
        )
        config = tomllib.loads(rendered)

        self.assertEqual(config["account_id"], "0" * 32)
        self.assertEqual(config["vars"]["ICP_DEPLOYMENT_MODE"], "seeded-worker")
        self.assertEqual(config["vars"]["K2_BASE_URL"], "https://api-dev.knowledge2.ai")
        self.assertEqual(config["routes"][0]["pattern"], "gtm-dev.knowledge2.ai")
        self.assertNotIn("replace-with-cloudflare-account-id", rendered)
        self.assertNotIn("ICP_API_ORIGIN", rendered)
        self.assertNotIn("cf" + "at_", rendered)

    def test_generated_worker_config_rejects_token_as_account_id(self) -> None:
        renderer = _load_renderer()

        with self.assertRaises(renderer.ConfigError):
            renderer.render_config(
                account_id="cf" + "at_not-an-account-id",
            )

    def test_deploy_preflight_validates_env_without_printing_secret_values(self) -> None:
        preflight = _load_preflight()
        env = {
            "CLOUDFLARE_ACCOUNT_ID": "0" * 32,
            "CLOUDFLARE_API_TOKEN": "cf" + "at_secret_value",
            "ICP_CLOUDFLARE_ROUTE": "gtm-dev.knowledge2.ai",
            "ICP_ADMIN_TOKEN": "admin-secret",
            "K2_API_KEY": "k2-secret",
            "APOLLO_API_KEY": "apollo-secret",
        }

        checks = preflight.run_preflight(env, check_wrangler=False)
        output = preflight.format_checks(checks)

        self.assertFalse(any(check.status == "fail" for check in checks))
        self.assertIn("CLOUDFLARE_API_TOKEN is set", output)
        self.assertNotIn("cf" + "at_secret_value", output)
        self.assertNotIn("admin-secret", output)
        self.assertNotIn("k2-secret", output)
        self.assertNotIn("apollo-secret", output)

    def test_deploy_preflight_fails_missing_required_env(self) -> None:
        preflight = _load_preflight()

        checks = preflight.run_preflight({}, check_wrangler=False)

        self.assertTrue(any(check.status == "fail" and check.name == "CLOUDFLARE_ACCOUNT_ID" for check in checks))
        self.assertTrue(any(check.status == "fail" and check.name == "cloudflare_api_token" for check in checks))

def _load_renderer():
    path = Path("deployment/cloudflare/render_wrangler_config.py")
    spec = importlib.util.spec_from_file_location("render_wrangler_config", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_preflight():
    path = Path("deployment/cloudflare/preflight.py")
    spec = importlib.util.spec_from_file_location("cloudflare_preflight", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    unittest.main()
