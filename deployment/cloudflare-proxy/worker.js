// Cloudflare Worker: front gtm-dev.knowledge2.ai with the private Cloud Run
// `gtm-demo` service.
//
// The Cloud Run service is NOT public (the org blocks allUsers), so it only
// answers requests bearing a Google-signed ID token whose audience is the
// service URL and whose service account has roles/run.invoker. This Worker
// mints that token from a service-account key held in Worker secrets, caches
// it, and forwards every request to Cloud Run with it attached. The engine
// itself runs in ICP_PUBLIC_READ_ONLY mode, so the *app* still blocks writes —
// this layer only gets anonymous browser traffic past Cloud Run's edge auth.
//
// Required secrets (wrangler secret put ...):
//   GCP_SA_EMAIL            service account email
//   GCP_SA_PRIVATE_KEY      its private key, PKCS#8 PEM (-----BEGIN PRIVATE KEY-----)
//   GCP_SA_PRIVATE_KEY_ID   the key id (sets the JWT `kid`)
// Required var (wrangler.toml [vars]):
//   CLOUD_RUN_URL           e.g. https://gtm-demo-tpl2qqmb4a-uc.a.run.app

const TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token";
const JWT_BEARER = "urn:ietf:params:oauth:grant-type:jwt-bearer";

// Cached per isolate; an ID token is valid ~1h. Refresh a minute early.
let cachedToken = null; // { token: string, exp: number }

function b64url(input) {
  const bytes = typeof input === "string" ? new TextEncoder().encode(input) : new Uint8Array(input);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function pemToPkcs8(pem) {
  const body = pem
    .replace(/-----BEGIN PRIVATE KEY-----/, "")
    .replace(/-----END PRIVATE KEY-----/, "")
    .replace(/\s+/g, "");
  const raw = atob(body);
  const buf = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) buf[i] = raw.charCodeAt(i);
  return buf.buffer;
}

async function mintIdToken(env, now) {
  const audience = env.CLOUD_RUN_URL;
  const header = { alg: "RS256", typ: "JWT", kid: env.GCP_SA_PRIVATE_KEY_ID };
  const claims = {
    iss: env.GCP_SA_EMAIL,
    sub: env.GCP_SA_EMAIL,
    aud: TOKEN_ENDPOINT,
    iat: now,
    exp: now + 3600,
    target_audience: audience,
  };
  const signingInput = `${b64url(JSON.stringify(header))}.${b64url(JSON.stringify(claims))}`;
  const key = await crypto.subtle.importKey(
    "pkcs8",
    pemToPkcs8(env.GCP_SA_PRIVATE_KEY),
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("RSASSA-PKCS1-v1_5", key, new TextEncoder().encode(signingInput));
  const assertion = `${signingInput}.${b64url(sig)}`;

  const resp = await fetch(TOKEN_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: `grant_type=${encodeURIComponent(JWT_BEARER)}&assertion=${encodeURIComponent(assertion)}`,
  });
  if (!resp.ok) {
    throw new Error(`token exchange failed: ${resp.status} ${await resp.text()}`);
  }
  const data = await resp.json();
  if (!data.id_token) throw new Error("token endpoint returned no id_token");
  return data.id_token;
}

async function getIdToken(env) {
  const now = Math.floor(Date.now() / 1000);
  if (cachedToken && cachedToken.exp - 60 > now) return cachedToken.token;
  const token = await mintIdToken(env, now);
  cachedToken = { token, exp: now + 3600 };
  return token;
}

export default {
  async fetch(request, env) {
    if (!env.CLOUD_RUN_URL || !env.GCP_SA_EMAIL || !env.GCP_SA_PRIVATE_KEY) {
      return new Response("proxy misconfigured: missing CLOUD_RUN_URL / service-account secrets", { status: 500 });
    }
    let idToken;
    try {
      idToken = await getIdToken(env);
    } catch (err) {
      return new Response(`upstream auth failed: ${err.message}`, { status: 502 });
    }

    // Preserve path + query; swap only the origin to the Cloud Run service.
    const incoming = new URL(request.url);
    const target = new URL(env.CLOUD_RUN_URL);
    target.pathname = incoming.pathname;
    target.search = incoming.search;

    const headers = new Headers(request.headers);
    headers.set("Authorization", `Bearer ${idToken}`);
    headers.set("Host", target.host);

    const upstream = new Request(target.toString(), {
      method: request.method,
      headers,
      body: request.method === "GET" || request.method === "HEAD" ? undefined : request.body,
      redirect: "manual",
    });
    return fetch(upstream);
  },
};
