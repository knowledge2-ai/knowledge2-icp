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

            async function request(worker, env, path, payload, token) {
              const headers = { "content-type": "application/json" };
              if (token) headers.authorization = `Bearer ${token}`;
              const init = payload === undefined
                ? { headers }
                : { method: "POST", headers, body: JSON.stringify(payload) };
              const response = await worker.fetch(new Request(`https://worker.test${path}`, init), env);
              const body = await response.json();
              if (!response.ok) throw new Error(`${path} failed ${response.status}: ${JSON.stringify(body)}`);
              return body;
            }

            const kv = new FakeKV();
            const env = { ICP_STATE: kv, ICP_ADMIN_TOKEN: "admin-secret" };
            const workerOne = await loadWorker("one");
            // Read-only demo endpoints are public (see deployment/cloudflare/README.md
            // "Auth scope matrix"); mutating actions still require a token.
            const publicState = await workerOne.fetch(new Request("https://worker.test/api/state"), env);
            assert.equal(publicState.status, 200);
            const blockedMutation = await workerOne.fetch(new Request("https://worker.test/api/settings", {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({ max_companies: 5 }),
            }), env);
            assert.equal(blockedMutation.status, 401);
            const badSession = await workerOne.fetch(new Request("https://worker.test/api/auth/session", {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({ token: "wrong" }),
            }), env);
            assert.equal(badSession.status, 401);

            const publicHealth = await request(workerOne, env, "/api/health");
            assert.equal(publicHealth.auth_required, true);
            assert.equal(publicHealth.authenticated, false);
            const session = await request(workerOne, env, "/api/auth/session", { token: "admin-secret" });
            assert.ok(session.session_token);
            const token = session.session_token;
            const authenticatedHealth = await request(workerOne, env, "/api/health", undefined, token);
            assert.equal(authenticatedHealth.authenticated, true);

            await request(workerOne, env, "/api/settings", { max_companies: 77, default_query: "durable state query" }, token);
            await request(workerOne, env, "/api/sources", {
              name: "Durable source",
              type: "manual_seed",
              value: "Durable Fleet, durable.example",
              source_group: "durability-test",
              schedule: "weekly",
            }, token);
            const run = await request(workerOne, env, "/api/runs", {
              query: "durable state run",
              candidates: [{ company: "Durable Fleet", domain: "durable.example" }],
              fetch: false,
              include_github: false,
            }, token);

            // A substantive run (>= 3 leads) whose candidates exercise the ported
            // vertical-focus moat scoring: a vertical-market incumbent, an
            // explicitly horizontal platform, and an unrecognized niche.
            const moatRun = await request(workerOne, env, "/api/runs", {
              query: "vertical focus moat",
              candidates: [
                { company: "Vertical VMS", domain: "vert.example", notes: "Construction compliance permitting workflow software for field service crews" },
                { company: "Horizontal SaaS", domain: "horiz.example", notes: "Workflow automation software for businesses of all sizes across industries" },
                { company: "Niche Ops", domain: "niche.example", notes: "Funeral home management records platform" },
              ],
              fetch: false,
              include_github: false,
            }, token);

            const workerTwo = await loadWorker("two");
            const settings = await request(workerTwo, env, "/api/settings", undefined, token);
            const sources = await request(workerTwo, env, "/api/sources", undefined, token);
            const state = await request(workerTwo, env, "/api/state", undefined, token);
            const workspaceState = await request(workerTwo, env, "/api/workspace-state", undefined, token);

            assert.equal(settings.settings.max_companies, 77);
            assert.equal(settings.settings.default_query, "durable state query");
            assert.ok(sources.sources.some((source) => source.name === "Durable source"));
            assert.ok(state.runs.some((item) => item.id === run.id));

            // Ported #19: the seeded showcase is pinned first in the run list and
            // is the default landing run until a substantive user run exists; the
            // dashboard then lands on the most recent substantive run.
            assert.equal(state.runs[0].id, "run-seeded-icp");
            assert.equal(state.latest_run.id, moatRun.id);

            // Ported #18: vertical-market focus deepens the moat, explicit
            // horizontal-audience language caps it, and an unrecognized niche
            // stays neutral (vertical > niche > horizontal).
            const byCompany = Object.fromEntries(state.latest_run.leads.map((lead) => [lead.score.company.company, lead.score]));
            assert.equal(byCompany["Vertical VMS"].data_workflow_score, 25);
            assert.equal(byCompany["Horizontal SaaS"].data_workflow_score, 15);
            assert.ok(byCompany["Vertical VMS"].total_score > byCompany["Niche Ops"].total_score);
            assert.ok(byCompany["Niche Ops"].total_score > byCompany["Horizontal SaaS"].total_score);

            assert.equal(workspaceState.durable, true);
            assert.equal(workspaceState.store, "cloudflare-kv");
            const collectionCounts = Object.fromEntries(workspaceState.collections.map((item) => [item.key, item]));
            assert.equal(collectionCounts.settings.persisted, true);
            assert.equal(collectionCounts.sources.persisted, true);
            assert.equal(collectionCounts.runs.persisted, true);
            assert.equal(collectionCounts.runs.count, 2);
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

    def test_apollo_people_match_reveals_real_email(self) -> None:
        # Ported from the gtm-icp plugin: People Match runs with
        # reveal_personal_emails=true so the cloud demo surfaces real emails, the
        # locked "email_not_unlocked" placeholder is stripped, and a revealed
        # contact carries email_status + revealed=true.
        script = textwrap.dedent(
            r"""
            import assert from "node:assert/strict";
            import { pathToFileURL } from "node:url";

            const workerUrl = pathToFileURL(`${process.cwd()}/deployment/cloudflare/worker.js`).href;

            class FakeKV {
              constructor() { this.values = new Map(); }
              async get(key, type) {
                const raw = this.values.has(key) ? this.values.get(key) : null;
                if (raw === null || raw === undefined) return null;
                return type === "json" ? JSON.parse(raw) : raw;
              }
              async put(key, value) { this.values.set(key, String(value)); }
            }

            const apolloCalls = [];
            globalThis.fetch = async (input) => {
              const requestUrl = typeof input === "string" ? input : input.url;
              apolloCalls.push(requestUrl);
              if (requestUrl.includes("/mixed_people/api_search")) {
                // Search teaser: obfuscated last name, locked placeholder email.
                return new Response(JSON.stringify({ people: [
                  { id: "p1", first_name: "Dana", last_name_obfuscated: "L.",
                    title: "VP Product", email: "email_not_unlocked@domain.com",
                    has_email: true, organization: { name: "Durable Fleet" } },
                ] }), { status: 200, headers: { "content-type": "application/json" } });
              }
              if (requestUrl.includes("/people/bulk_match")) {
                // Match reveal: full name + real verified email.
                return new Response(JSON.stringify({ matches: [
                  { id: "p1", name: "Dana Lopez", title: "VP Product",
                    email: "dana@durable.example", email_status: "verified",
                    linkedin_url: "https://www.linkedin.com/in/dana-lopez" },
                ] }), { status: 200, headers: { "content-type": "application/json" } });
              }
              throw new Error(`unexpected fetch ${requestUrl}`);
            };

            const worker = (await import(`${workerUrl}?apollo=reveal`)).default;
            const env = { ICP_STATE: new FakeKV(), ICP_ADMIN_TOKEN: "admin-secret", APOLLO_API_KEY: "test-key" };

            async function request(path, payload, token) {
              const headers = { "content-type": "application/json" };
              if (token) headers.authorization = `Bearer ${token}`;
              const init = payload === undefined ? { headers } : { method: "POST", headers, body: JSON.stringify(payload) };
              const response = await worker.fetch(new Request(`https://worker.test${path}`, init), env);
              const body = await response.json();
              if (!response.ok) throw new Error(`${path} failed ${response.status}: ${JSON.stringify(body)}`);
              return body;
            }

            const session = await request("/api/auth/session", { token: "admin-secret" });
            const token = session.session_token;
            const run = await request("/api/runs", {
              query: "apollo reveal run",
              candidates: [{ company: "Durable Fleet", domain: "durable.example",
                notes: "Fleet telematics and dispatch workflow software for transport operators" }],
              fetch: false,
              include_github: false,
            }, token);

            const prospects = await request(`/api/runs/${run.id}/prospects`, undefined, token);

            // People Match was asked to reveal the personal email.
            const matchCall = apolloCalls.find((url) => url.includes("/people/bulk_match"));
            assert.ok(matchCall, "bulk_match was not called");
            assert.match(matchCall, /reveal_personal_emails=true/);

            const apolloProspect = prospects.prospects.find((item) => item.source === "apollo");
            assert.ok(apolloProspect, "no apollo-sourced prospect");
            assert.equal(apolloProspect.name, "Dana Lopez");
            assert.equal(apolloProspect.email, "dana@durable.example");
            assert.equal(apolloProspect.email_status, "verified");
            assert.equal(apolloProspect.revealed, true);
            // The locked placeholder never leaks as a real address.
            for (const item of prospects.prospects) {
              assert.ok(!String(item.email || "").includes("email_not_unlocked"), JSON.stringify(item));
            }
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
            self.fail(f"Apollo reveal check failed.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")


if __name__ == "__main__":
    unittest.main()
