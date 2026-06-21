# Lock gtm-dev behind Google SSO (Cloudflare Access)

Goal: only `@posterity.ventures` Google accounts can reach
`gtm-dev.knowledge2.ai`, and authenticated users get the full read-write app
with PII reveal — no more anonymous public demo.

How it fits together:

```
Browser ──▶ Cloudflare Access ──▶ gtm-dev-proxy (Worker) ──▶ Cloud Run (private)
            Google SSO,            adds Cloud Run ID token,     engine in access mode:
            policy @posterity       forwards Cf-Access-*         trusts Cf-Access email,
            .ventures               headers                      full read-write
```

The edge does the SSO. The engine never sees a password — it only trusts the
`Cf-Access-Authenticated-User-Email` header Access stamps on every request. That
trust is sound because the engine is reachable **only** through this Worker
(Cloud Run is private; the Worker has `workers_dev = false`), and Access
overwrites that header at the edge so a client can't forge it.

## Steps that touch credentials — you run these

### 1. Google OAuth client (Google Cloud Console)

Create an OAuth 2.0 Client ID so Cloudflare can use Google as the identity
provider. APIs & Services → Credentials → Create credentials → OAuth client ID →
**Web application**.

- Authorized redirect URI: `https://<your-team>.cloudflareaccess.com/cdn-cgi/access/callback`
  (the exact value is shown in the Cloudflare step below — copy it from there).

Save the **Client ID** and **Client Secret**. Treat the secret like any other —
don't paste it into chat; enter it directly in the Cloudflare dashboard.

### 2. Add Google as a login method (Cloudflare Zero Trust)

Zero Trust dashboard → Settings → Authentication → Login methods → Add new →
**Google**. Paste the Client ID + Secret from step 1. The page shows the exact
redirect URI — make sure it matches what you set in Google. Test the connection.

### 3. Create the Access application

Zero Trust → Access → Applications → Add an application → **Self-hosted**.

- Application domain: `gtm-dev.knowledge2.ai`
- Identity providers: Google (from step 2)
- Session duration: your call (24h is typical)

Add an **Allow** policy:

- Name: `posterity.ventures only`
- Action: Allow
- Include → **Emails ending in** → `@posterity.ventures`

Optionally add a **Bypass** policy for `path is /healthz` so uptime monitoring
can hit health without a login (the engine serves `/healthz` before its auth
gate; without a bypass, Access gates it too).

## Steps I can't run for you — but the code/config is ready

### 4. Redeploy the Worker with workers.dev off

`wrangler.toml` now sets `workers_dev = false`. Republish so the only way in is
the Access-gated custom domain:

```bash
cd deployment/cloudflare-proxy && wrangler deploy
```

### 5. Flip the engine from read-only to access mode

The engine reads `ICP_ACCESS_TRUSTED_DOMAIN`. Update the live Cloud Run service
(drops the old read-only flag, adds the access domain):

```bash
gcloud run services update gtm-demo \
  --project knowledge2-dev-9650 --region us-central1 \
  --update-env-vars ICP_ACCESS_TRUSTED_DOMAIN=posterity.ventures \
  --remove-env-vars ICP_PUBLIC_READ_ONLY
```

(Or a fresh build: `PROJECT=knowledge2-dev-9650 SERVICE=gtm-demo AUTH=access ./deployment/cloudrun/deploy.sh`.)

## Verify

In a browser, hit `https://gtm-dev.knowledge2.ai` — you should get the Google
login, and only an `@posterity.ventures` account gets through to the app. A
logged-in user can now create runs, edit criteria, and reveal PII.

`curl` without an Access token gets the login redirect (that's the point). To
smoke-test the API headless, mint an Access **service token** and send the
`CF-Access-Client-Id` / `CF-Access-Client-Secret` headers, or check `/healthz`
if you added the bypass policy.

## Still gated on Apollo

The auth wall is independent and solid. **Real names/emails actually appearing**
still depends on Apollo returning PII on your plan via People-Match
(`reveal_personal_emails=true` in `apollo.py`) — which is unverified. Validate
that separately before promising filled contacts behind the wall.
