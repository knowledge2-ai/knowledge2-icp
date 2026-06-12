export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/healthz") {
      return withSecurityHeaders(json({
        status: "ok",
        service: "knowledge2-icp-worker",
        api_origin_configured: Boolean(env.ICP_API_ORIGIN),
        auth_required: Boolean(env.ICP_ADMIN_TOKEN),
      }));
    }
    if (url.pathname.startsWith("/api/")) {
      const auth = authorizeApiRequest(request, env);
      if (!auth.configured) {
        return withSecurityHeaders(json({ error: "ICP_ADMIN_TOKEN is required for Worker API proxying." }, 503));
      }
      if (!auth.authorized) {
        return withSecurityHeaders(unauthorized());
      }
      return proxyApiRequest(request, env);
    }

    if (url.pathname.startsWith("/assets/")) {
      const assetUrl = new URL(request.url);
      assetUrl.pathname = `/${url.pathname.split("/").pop() || ""}`;
      const assetResponse = await env.ASSETS.fetch(new Request(assetUrl, request));
      if (assetResponse.status !== 404) return withSecurityHeaders(assetResponse);
    }

    const assetResponse = await env.ASSETS.fetch(request);
    if (assetResponse.status !== 404) return withSecurityHeaders(assetResponse);

    const indexUrl = new URL(request.url);
    indexUrl.pathname = "/";
    return withSecurityHeaders(await env.ASSETS.fetch(new Request(indexUrl, request)));
  },
};

async function proxyApiRequest(request, env) {
  if (!env.ICP_API_ORIGIN) {
    return json({ error: "ICP_API_ORIGIN is not configured." }, 503);
  }

  const incoming = new URL(request.url);
  const target = new URL(incoming.pathname + incoming.search, env.ICP_API_ORIGIN);
  const headers = new Headers(request.headers);
  headers.set("x-forwarded-host", incoming.host);
  headers.set("x-forwarded-proto", incoming.protocol.replace(":", ""));
  headers.delete("host");

  const proxied = new Request(target, {
    method: request.method,
    headers,
    body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
    redirect: "manual",
  });
  const response = await fetch(proxied);
  return withSecurityHeaders(response);
}

function authorizeApiRequest(request, env) {
  const expected = (env.ICP_ADMIN_TOKEN || "").trim();
  if (!expected) return { configured: false, authorized: false };
  const authHeader = request.headers.get("authorization") || "";
  const [scheme, ...parts] = authHeader.split(" ");
  const token = parts.join(" ").trim();
  return {
    configured: true,
    authorized: scheme.toLowerCase() === "bearer" && constantTimeEqual(token, expected),
  };
}

function constantTimeEqual(left, right) {
  if (!left || left.length !== right.length) return false;
  let mismatch = 0;
  for (let index = 0; index < left.length; index += 1) {
    mismatch |= left.charCodeAt(index) ^ right.charCodeAt(index);
  }
  return mismatch === 0;
}

function withSecurityHeaders(response) {
  const headers = new Headers(response.headers);
  headers.set("content-security-policy", "default-src 'self'; connect-src 'self'; img-src 'self' data: https:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'");
  headers.set("x-content-type-options", "nosniff");
  headers.set("x-frame-options", "DENY");
  headers.set("referrer-policy", "strict-origin-when-cross-origin");
  headers.set("permissions-policy", "camera=(), microphone=(), geolocation=()");
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

function unauthorized() {
  return json({ error: "Admin token required." }, 401, {
    "www-authenticate": 'Bearer realm="knowledge2-icp"',
  });
}

function json(payload, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "content-type": "application/json",
      "cache-control": "no-store",
      ...extraHeaders,
    },
  });
}
