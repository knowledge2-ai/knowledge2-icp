# Knowledge2 Agentic GTM Dashboard Security Review Report

**Date:** 2026-06-12
**Scope:** Agentic GTM dashboard feature slice in the main `knowledge2-icp` repository, including the Python web/API server, vanilla JavaScript frontend, Cloudflare Worker shell, K2/Apollo adapters, tests, and deployment documentation.
**Focus Areas:** API authentication, Cloudflare edge proxying, outbound evidence fetching, secrets handling, frontend XSS/token handling, K2/Apollo provider boundaries, deployment configuration
**Review Method:** Static analysis + dynamic testing + architecture review + documentation audit

### Submodule Scope

No git submodules detected. Entire repository is in scope.

---

## Executive Summary

This review identified **3 open findings** and **2 issues resolved during the review**. No open Critical or High findings remain in this feature slice after the remediation pass.

| Severity | Count | Requires Immediate Action |
|----------|-------|---------------------------|
| **CRITICAL** | 0 | No |
| **HIGH** | 0 | No |
| **MEDIUM** | 0 | No |
| **LOW** | 2 | Track and harden before broad rollout |
| **INFO** | 1 | Backlog |

### Verification Summary

| Verification Status | Count |
|---------------------|-------|
| **Confirmed** (dynamic test) | 3 |
| **Static Analysis Only** | 2 |
| **False Positive** | 0 |

### Top Priority Issues

1. **Admin token is stored in browser `localStorage`** - acceptable for the current admin-only tool, but vulnerable if a future XSS bug appears.
2. **No API rate limiting or retry budget** - authenticated endpoints can trigger provider calls and remote K2 writes without server-side throttling.
3. **Security scanners are not installed in the local toolchain** - manual checks passed, but dependency/SAST coverage should be added to CI.

### Resolved During This Review

| Finding | Resolution |
|---------|------------|
| Worker API fail-opened when `ICP_ADMIN_TOKEN` was missing | `deployment/cloudflare/worker.js` now fails closed with `503`; dynamic probe now returns `missing_secret=503`, `missing_token=401`, `valid_token=200`. |
| Evidence fetching could target private/internal hosts from seed domains | `icp_engine/enrichment.py` now rejects non-HTTP(S), localhost, literal private IPs, and domains resolving to non-global IPs before `urlopen`. Regression tests cover localhost, metadata IP, and private DNS resolution. |

---

## Attack Surface Summary

- Public static frontend: `/`, `/assets/*`, and Worker static assets.
- Public liveness: Python `/healthz` and Worker `/healthz`, with minimal status fields.
- Protected API: `/api/state`, `/api/criteria`, `/api/search`, `/api/runs`, `/api/research`, K2 export/sync, prospects JSON/CSV, and `/api/health`.
- State-changing operations: criteria edits, run creation, manifest export, live K2 sync when `apply=true`.
- External calls: DuckDuckGo HTML search, public company websites, GitHub Search API, Apollo API, and K2 API.
- Sensitive configuration: `ICP_ADMIN_TOKEN`, `K2_API_KEY`, `APOLLO_API_KEY`, `GITHUB_TOKEN`, Gemini/Google credentials, Cloudflare deployment token outside source.
- Storage: local app state under `out/app_state`, local K2 manifests, cached fetched evidence, ignored by git.

---

## 1. Authentication & Access Control

### 1.1 Findings

#### LOW: Admin Token Is Stored In Browser `localStorage`

**Source:** `main`
**Location:** `icp_engine/web_assets/app.js:9`, `icp_engine/web_assets/app.js:18`, `icp_engine/web_assets/app.js:49`
**Verification:** Static Analysis Only

```javascript
const AUTH_TOKEN_KEY = "knowledge2.icp.adminToken";
const token = localStorage.getItem(AUTH_TOKEN_KEY) || "";
localStorage.setItem(AUTH_TOKEN_KEY, value);
```

**Impact:** A future XSS issue in the dashboard could read the saved bearer token and reuse it against `/api/*`.

**Evidence:** The frontend stores the operator-entered token in `localStorage` and attaches it as a bearer token on API requests. Current rendering consistently escapes dynamic content and the Worker sets a strict CSP, so this is a residual hardening issue rather than an active exploit.

**Recommendation:** Prefer a short-lived server-side session or `HttpOnly; Secure; SameSite=Strict` cookie before broad multi-user rollout. For this admin-only slice, keep the CSP strict and avoid any raw HTML rendering.

### 1.2 Design Guidelines

1. Keep static assets public but require bearer auth for all `/api/*` routes.
2. Keep `ICP_ADMIN_TOKEN` high entropy and rotate it before production use.
3. Do not use the Cloudflare API token as the dashboard admin token.

---

## 2. Multi-Tenancy Isolation

### 2.1 Findings

No multi-tenancy findings. This feature slice is a single-operator local/control-plane app with no tenant model.

### 2.2 Design Guidelines

1. Add explicit tenant/project scoping before offering this dashboard to multiple customer teams.
2. Ensure K2 project/corpus names cannot be used as an authorization boundary; authorization must happen before sync.

---

## 3. Input Validation & Injection

### 3.1 Findings

No open injection findings after remediation.

**Resolved SSRF hardening:** `icp_engine/enrichment.py:96`, `icp_engine/enrichment.py:131`, and `icp_engine/enrichment.py:237` now validate outbound fetch targets before network calls.

```python
if not _is_public_fetch_url(url):
    continue
```

```python
if not host or host.lower() == "localhost" or host.endswith(".localhost"):
    return False
```

**Verification:** Confirmed through `tests/test_enrichment.py:28` and `tests/test_enrichment.py:34`, plus full test run.

### 3.2 Design Guidelines

1. Keep response byte caps and timeouts on all outbound HTTP calls.
2. Re-check private-network controls if the fetcher is replaced with an async HTTP client that follows redirects differently.
3. Treat DNS-rebinding prevention as a deeper follow-up if this fetcher becomes internet-facing beyond admin use.

---

## 4. Data Security & Encryption

### 4.1 Findings

No open data-security findings. Provider keys are read from environment variables and are not returned in API responses. Provider status exposes configured booleans and env var names only at `icp_engine/app_store.py:106`.

### 4.2 Design Guidelines

1. Keep `out/app_state` ignored and avoid uploading run caches into public artifacts.
2. Treat Apollo people records as GTM contact data; export only to approved systems.
3. Store production secrets in Cloudflare secrets or the origin platform secret store, never `wrangler.toml`.

---

## 5. Frontend & Client-Side Security

### 5.1 Findings

See Finding 1. The dashboard uses `innerHTML` heavily, but dynamic values are passed through `escapeHtml` or `escapeAttribute` in the reviewed render paths. Worker CSP is restrictive at `deployment/cloudflare/worker.js:75`.

### 5.2 Design Guidelines

1. Continue escaping every interpolated field before assigning `innerHTML`.
2. Avoid adding inline scripts or third-party CDN scripts; the current CSP blocks them.
3. If markdown rendering is added, use a sanitizer rather than direct HTML insertion.

---

## 6. API Security

### 6.1 Findings

#### LOW: No API Rate Limiting Or Provider Usage Budget

**Source:** `main`
**Location:** `icp_engine/web.py:124`, `icp_engine/web.py:149`, `icp_engine/web.py:183`
**Verification:** Static Analysis Only

```python
if parsed.path == "/api/search":
if parsed.path == "/api/runs":
if parsed.path.startswith("/api/runs/") and parsed.path.endswith("/k2-sync"):
```

**Impact:** A valid token holder, leaked token, or compromised browser could repeatedly trigger search, enrichment, Apollo, GitHub, or K2 operations. That can create cost, quota, or remote-data churn.

**Evidence:** The API has authentication and input size caps, but no per-token or per-IP rate limiting. K2 apply still requires `K2_API_KEY` and an explicit `apply=true`, which limits impact.

**Recommendation:** Add edge rate limiting in Cloudflare for `/api/*`, and add server-side run/job concurrency limits before production. Log denied attempts and high-volume activity.

### 6.2 Design Guidelines

1. Keep state-changing K2 sync behind both auth and `apply=true`.
2. Return generic errors; avoid exposing provider exception details beyond operator-safe status.
3. Add audit logs for criteria edits, run creation, and live K2 sync.

---

## 7. Infrastructure & DevOps

### 7.1 Findings

No open High/Medium infra findings after remediation.

**Resolved edge fail-open:** `deployment/cloudflare/worker.js:12` now requires configured edge auth before proxying; `icp_engine/web.py:327` now rejects non-loopback binds without a token unless explicitly overridden.

```javascript
if (!auth.configured) {
  return withSecurityHeaders(json({ error: "ICP_ADMIN_TOKEN is required for Worker API proxying." }, 503));
}
```

```python
if not token and not _open_api_allowed(host, allow_open_api):
    raise ValueError("ICP_ADMIN_TOKEN is required when binding the API to a non-loopback host.")
```

**Verification:** Dynamic Worker probe now returns `missing_secret=503`, `missing_token=401`, `valid_token=200`. `tests/test_web.py:140` covers the non-loopback origin guard.

### 7.2 Design Guidelines

1. Keep `workers_dev=false` and use the confirmed custom domain route.
2. Replace placeholder `account_id` and `ICP_API_ORIGIN` outside committed source or via deployment overlay.
3. Keep origin access private where possible, even with Worker auth enabled.

---

## 8. Secrets & Key Management

### 8.1 Findings

#### INFO: Local Security Scanner Tooling Is Not Installed

**Source:** `main`
**Location:** local toolchain / CI follow-up
**Verification:** Confirmed

```text
bandit: not installed
pip-audit: not installed
safety: not installed
semgrep: not installed
gitleaks: not installed
trivy: not installed
```

**Impact:** Manual scans and targeted `rg` checks passed, but CI will not automatically catch new secrets, SAST issues, or dependency advisories unless these tools are added.

**Evidence:** `pyproject.toml:6` has no runtime dependencies and the local secret scan for provided token fragments returned no matches. Wrangler dry run also reported only the experimental `secrets` config warning.

**Recommendation:** Add at least one CI secret scan and one Python SAST/dependency audit path. For this repo, `gitleaks detect`, `bandit -r icp_engine`, and `pip-audit` are sufficient starting points.

### 8.2 Design Guidelines

1. Keep `.env.example` placeholders empty for `ICP_ADMIN_TOKEN`, `K2_API_KEY`, and `APOLLO_API_KEY`.
2. Rotate any tokens shared outside the secret manager before production.
3. Avoid logging request headers or provider response bodies that may contain keys or PII.

---

## 9. Documentation Gaps

### Stale or Misleading Documentation

| File | Issue | Impact |
|------|-------|--------|
| None remaining after this pass | Cloudflare docs were updated to describe fail-closed Worker auth and origin non-loopback token requirements. | N/A |

### Missing Documentation

| Topic | Recommendation |
|-------|----------------|
| Incident/key rotation runbook | Add exact steps for rotating `ICP_ADMIN_TOKEN`, `K2_API_KEY`, `APOLLO_API_KEY`, and Cloudflare API credentials. |
| Provider usage controls | Document expected run volume, Apollo/K2 quotas, and operational response for runaway jobs. |

### Suppressed Warnings

No `# nosec`, `eslint-disable`, or equivalent suppressions were found in the reviewed feature files.

---

## 10. Design Guidelines & Recommendations

### 10.1 Immediate Actions (Before Production)

| Priority | Issue | Effort | Impact |
|----------|-------|--------|--------|
| P0 | Configure Cloudflare `ICP_ADMIN_TOKEN`, origin `ICP_ADMIN_TOKEN`, `K2_API_KEY`, and `APOLLO_API_KEY` as secrets. | Low | High |
| P0 | Confirm `ICP_API_ORIGIN`, Cloudflare account, and custom hostname outside committed source. | Low | High |

### 10.2 Short-Term Improvements (1-2 Sprints)

| Priority | Issue | Effort | Impact |
|----------|-------|--------|--------|
| P2 | Add Cloudflare rate limiting for `/api/*`. | Low | Medium |
| P2 | Add CI secret/SAST scans. | Medium | Medium |
| P3 | Replace localStorage admin token storage with a server-issued session when multi-user access is planned. | Medium | Medium |

### 10.3 Long-Term Security Roadmap

1. **Tenant-aware authorization:** Add users, projects, roles, and tenant-scoped run storage before broader team use.
2. **Async job isolation:** Move enrichment/provider calls behind a queue with concurrency and budget controls.
3. **Audit trail:** Record criteria edits, run creation, export, and K2 apply actions with actor and timestamp.

---

## 11. Remediation Priority Matrix

### By Severity and Effort

```text
                    LOW EFFORT          MEDIUM EFFORT       HIGH EFFORT
                    -----------------------------------------------------
CRITICAL          | none                | none                | none
HIGH              | none                | none                | none
MEDIUM            | none                | none                | none
LOW               | rate limiting       | session auth        | none
INFO              | CI scanners         | rotation runbook    | none
```

### OWASP Top 10 Coverage

| OWASP Category | Findings | Status |
|----------------|----------|--------|
| A01 Broken Access Control | 0 open; 1 resolved | Green |
| A02 Cryptographic Failures | 0 | Green |
| A03 Injection | 0 | Green |
| A04 Insecure Design | 1 open | Yellow |
| A05 Security Misconfiguration | 0 open; 1 resolved | Green |
| A06 Vulnerable Components | 0 known; scanner gap noted | Yellow |
| A07 Auth Failures | 1 open residual | Yellow |
| A08 Data Integrity Failures | 0 | Green |
| A09 Logging Failures | 1 recommendation | Yellow |
| A10 SSRF | 0 open; 1 resolved | Green |

### Breaking-Change Remediation Risk Summary

| # | Finding | Severity | Breaking Change | Test Coverage | Tests to Add |
|---|---------|----------|-----------------|---------------|--------------|
| 1 | Replace browser token storage with server session | LOW | Yes, changes auth flow and UI token handling | Partial | Add API session tests and browser auth-flow tests when session auth is implemented. |
| 2 | Add rate limits | LOW | Possibly, changes repeated request behavior | Partial | Add Worker/API tests for limit exceeded and retry headers. |

### Compliance Considerations

| Standard | Key Gaps |
|----------|----------|
| **SOC 2** | Add audit logging, CI security scans, key rotation runbook, and provider usage monitoring. |
| **GDPR** | Apollo prospect exports may include personal data; document lawful basis, retention, and deletion workflow before production. |
| **HIPAA** | Not applicable unless future runs ingest healthcare PHI; current design should not process PHI. |

---

## Appendix A: Files Reviewed

### Python API And Pipeline
- `icp_engine/web.py` - HTTP routes, auth, health, origin bind safety.
- `icp_engine/enrichment.py` - outbound company website fetching and SSRF controls.
- `icp_engine/discovery.py` - search result parsing and candidate extraction.
- `icp_engine/research.py` - run creation, provider calls, NL research.
- `icp_engine/app_store.py` - local state, provider readiness response.
- `icp_engine/k2_backend.py` - manifest/export/live K2 sync construction.
- `icp_engine/k2_client.py` - K2 HTTP client and API key handling.
- `icp_engine/apollo.py` - Apollo API client and compacted people/org payloads.

### Frontend And Edge
- `icp_engine/web_assets/app.js` - token storage, render paths, API calls, K2 apply confirmation.
- `icp_engine/web_assets/index.html` - admin token control and dashboard views.
- `deployment/cloudflare/worker.js` - edge auth, API proxying, security headers.
- `deployment/cloudflare/wrangler.toml` - assets, route, placeholders, secret names.

### Tests And Docs
- `tests/test_web.py`, `tests/test_enrichment.py`, `tests/test_cloudflare_config.py`.
- `.env.example`, `README.md`, `docs/OPERATIONS.md`, `deployment/cloudflare/README.md`, `docs/CLOUDFLARE_K2_DEPLOYMENT.md`.

---

## Appendix B: Automated Scanner Results

### SAST
- Tool(s) used: targeted `rg` pattern scan. `bandit` and `semgrep` were not installed.
- Total issues: 0 confirmed open SAST issues in reviewed feature files.

### Dependency Audit
- Tool(s) used: manifest inspection. `pip-audit` and `safety` were not installed.
- Vulnerable packages: 0 known from local manifests; `pyproject.toml` declares no runtime dependencies and optional `google-genai`/`pytest`.

### Secrets Scanning
- Tool: targeted `rg` scan for provided token/account fragments and common Cloudflare token prefix.
- Secrets found: 0.
- Supporting test: `tests/test_cloudflare_config.py:21` checks Cloudflare token-shaped values and literal secret assignment patterns.

### Container / IaC Scanning
- Tool: `wrangler deploy --dry-run --config deployment/cloudflare/wrangler.toml`.
- Issues: 0 blocking; Wrangler warns that `secrets` fields are experimental.

---

## Appendix C: Dynamic Test Evidence

### Worker Edge Auth Fail-Closed Probe

**Target:** `deployment/cloudflare/worker.js`

**Script:**
```javascript
import worker from './deployment/cloudflare/worker.js';
globalThis.fetch = async (request) =>
  new Response(JSON.stringify({ proxied: true, url: request.url }), { status: 200 });
const baseEnv = { ICP_API_ORIGIN: 'https://origin.example', ASSETS: { fetch: async () => new Response('asset') } };
```

**Result:**
```text
missing_secret=503
missing_token=401
valid_token=200
```

**Conclusion:** Confirmed fixed. Before remediation, the same probe returned `unauthenticated_worker_api_status=200`.

### Local Dashboard Health Smoke

**Target:** Fresh local app at `http://127.0.0.1:8765`

**Result:**
```text
/healthz ok auth_required=False providers=False
/api/health ok auth_required=False providers=True
```

**Conclusion:** Local loopback open mode still works as documented.

### Regression Suite

**Target:** Python tests, syntax, Worker dry run

**Result:**
```text
python3 -m unittest discover -s tests
Ran 33 tests ... OK

python3 -m py_compile icp_engine/*.py
node --check icp_engine/web_assets/app.js
node --check deployment/cloudflare/worker.js
git diff --check
wrangler deploy --dry-run --config deployment/cloudflare/wrangler.toml
```

**Conclusion:** All required checks passed; Wrangler emitted only the experimental `secrets` field warning.

---

## Appendix D: Security Headers Reference

The Worker currently applies these response headers at `deployment/cloudflare/worker.js:75`:

```text
Content-Security-Policy: default-src 'self'; connect-src 'self'; img-src 'self' data: https:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), microphone=(), geolocation=()
```

Recommended production addition once the custom domain is live:

```text
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
```

---

*Report generated by automated security review on 2026-06-12. Manual verification recommended before live deployment.*
