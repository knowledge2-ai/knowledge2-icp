from __future__ import annotations

import os
import subprocess
import textwrap
import unittest


class CloudflareWorkerRuntimeTest(unittest.TestCase):
    def test_worker_state_survives_fresh_module_import_via_kv(self) -> None:
        script = textwrap.dedent(
            r"""
            import assert from "node:assert/strict";
            import { pathToFileURL } from "node:url";

            const workerUrl = pathToFileURL(`${process.cwd()}/deployment/cloudflare/worker.js`).href;

            class FakeKV {
              constructor() {
                this.values = new Map();
              }
              async get(key, type) {
                const raw = this.values.has(key) ? this.values.get(key) : null;
                if (raw === null || raw === undefined) return null;
                return type === "json" ? JSON.parse(raw) : raw;
              }
              async put(key, value) {
                this.values.set(key, String(value));
              }
            }

            async function loadWorker(tag) {
              return (await import(`${workerUrl}?fresh=${tag}`)).default;
            }

            async function request(worker, env, path, payload) {
              const init = payload === undefined
                ? {}
                : { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(payload) };
              const response = await worker.fetch(new Request(`https://worker.test${path}`, init), env);
              const body = await response.json();
              if (!response.ok) throw new Error(`${path} failed ${response.status}: ${JSON.stringify(body)}`);
              return body;
            }

            const kv = new FakeKV();
            const env = { ICP_STATE: kv };
            const workerOne = await loadWorker("one");
            await request(workerOne, env, "/api/settings", { max_companies: 77, default_query: "durable state query" });
            await request(workerOne, env, "/api/sources", {
              name: "Durable source",
              type: "manual_seed",
              value: "Durable Fleet, durable.example",
              source_group: "durability-test",
              schedule: "weekly",
            });
            const run = await request(workerOne, env, "/api/runs", {
              query: "durable state run",
              candidates: [{ company: "Durable Fleet", domain: "durable.example" }],
              fetch: false,
              include_github: false,
            });

            const workerTwo = await loadWorker("two");
            const settings = await request(workerTwo, env, "/api/settings");
            const sources = await request(workerTwo, env, "/api/sources");
            const state = await request(workerTwo, env, "/api/state");
            const workspaceState = await request(workerTwo, env, "/api/workspace-state");

            assert.equal(settings.settings.max_companies, 77);
            assert.equal(settings.settings.default_query, "durable state query");
            assert.ok(sources.sources.some((source) => source.name === "Durable source"));
            assert.ok(state.runs.some((item) => item.id === run.id));
            assert.equal(workspaceState.durable, true);
            assert.equal(workspaceState.store, "cloudflare-kv");
            const collectionCounts = Object.fromEntries(workspaceState.collections.map((item) => [item.key, item]));
            assert.equal(collectionCounts.settings.persisted, true);
            assert.equal(collectionCounts.sources.persisted, true);
            assert.equal(collectionCounts.runs.persisted, true);
            assert.equal(collectionCounts.runs.count, 1);
            """
        )
        env = {**os.environ, "NODE_NO_WARNINGS": "1"}
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            check=False,
            cwd=os.getcwd(),
            env=env,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            self.fail(f"Worker runtime durability check failed.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")


if __name__ == "__main__":
    unittest.main()
