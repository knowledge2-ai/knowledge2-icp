const SEED_CREATED_AT = "2026-06-12T00:00:00+00:00";
const SEED_RUN_ID = "run-seeded-icp";
const MAX_APOLLO_ENRICH_LEADS = 12;
const BLOCKED_DISCOVERY_HOSTS = new Set([
  "bing.com",
  "capterra.com",
  "crunchbase.com",
  "duckduckgo.com",
  "facebook.com",
  "g2.com",
  "github.com",
  "google.com",
  "linkedin.com",
  "twitter.com",
  "x.com",
  "youtube.com",
]);
const DISCOVERY_QUERY_STOPWORDS = new Set([
  "companies",
  "company",
  "data",
  "limited",
  "platform",
  "public",
  "saas",
  "software",
  "workflow",
  "workflows",
  "with",
]);

const SEED_CRITERIA_MARKDOWN = `# Seeded ICP Criteria

Source: local \`icp.md\`.

## Bottom line

Pre-2025 incumbent software companies with proprietary workflow/data assets,
enough customers to feel competitive pressure, and either no public AI
narrative or a shallow AI feature that does not yet change the customer core
workflow.

## Hard gates

- Founded before 2025.
- Product company, not primarily services or consulting.
- B2B or B2B2C with business customers, enterprise accounts, or partner channels.
- Has proprietary workflow/data such as trips, claims, inventory, tickets,
  inspections, schedules, diagnostics, documents, or transactions.
- Enough budget: roughly 25-2000 employees, or smaller when clearly funded.
- Not AI-native as the founding premise or core category.

## Scoring settings

- AI gap: 30 points.
- Data/workflow moat: 25 points.
- Commercial urgency: 20 points.
- Budget/access: 15 points.
- Feasibility: 10 points.
- Tier A threshold: 75.
- Tier B threshold: 60.
- Reject or nurture below 60.

## Priority verticals

Priority verticals: automotive, dealer, dealership, fleet, telematics,
field service, maintenance, logistics, warehouse, construction, property,
facilities, insurance, claims, healthcare admin, manufacturing, ERP,
compliance, govtech, permitting, legal, accounting, TMS, WMS, CMMS, RCM.
`;

const SEED_PROMPTS = [
  {
    id: "prompt-discovery-priority-verticals",
    label: "Discovery query",
    kind: "search",
    text: "workflow SaaS companies with fleet, dealership, field service, claims, or logistics data and limited public AI positioning",
  },
  {
    id: "prompt-ai-posture-audit",
    label: "AI posture audit",
    kind: "research",
    text: "Which Tier A or B leads have proprietary workflow data but weak AI posture, and what public evidence supports the recommendation?",
  },
  {
    id: "prompt-apollo-personas",
    label: "Apollo persona targets",
    kind: "prospecting",
    text: "Find product, engineering, data, and vertical GM leaders who can own an AI workflow opportunity map.",
  },
  {
    id: "prompt-k2-manifest",
    label: "K2 metadata manifest",
    kind: "k2",
    text: "Upload lead evidence with run_id, criteria_hash, source_type, page_category, signal_tags, persona_titles, and outreach_angle metadata.",
  },
];

const SEED_SETTINGS = {
  default_query: SEED_PROMPTS[0].text,
  max_companies: 50,
  max_pages: 6,
  fetch_website_evidence: true,
  include_github_metadata: true,
  use_apollo_enrichment: false,
  use_serp_discovery: true,
  tier_a_threshold: 75,
  tier_b_threshold: 60,
  employee_range: "25-2000 employees",
  deployment_mode: "cloudflare-seeded-worker",
};

const SEED_LISTS = {
  account_universe: [
    {
      company: "Mojio Example",
      domain: "moj.io",
      category: "connected mobility software",
      founded_year: 2012,
      employee_count: 120,
      hq: "Canada",
      notes: "Connected vehicle platform with trips diagnostics telematics data API integrations and partner workflows.",
    },
    {
      company: "Automate Example",
      domain: "automate.co.za",
      category: "dealership management software",
      founded_year: 1980,
      employee_count: 150,
      hq: "South Africa",
      notes: "Dealership management software trusted by dealerships with inventory transactions reporting and business workflows.",
    },
    {
      company: "AI Native Example",
      domain: "example.com",
      category: "AI agents",
      founded_year: 2025,
      employee_count: 20,
      hq: "US",
      notes: "AI-native autonomous agent platform for every business.",
    },
  ],
  priority_verticals: [
    "automotive",
    "fleet",
    "telematics",
    "dealership",
    "field service",
    "logistics",
    "construction",
    "insurance claims",
    "healthcare admin",
    "manufacturing",
    "govtech",
    "legal practice software",
  ],
};

const runtime = {
  criteria: null,
  runs: new Map(),
  seedLists: null,
};

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/healthz") {
      return withSecurityHeaders(json({
        status: "ok",
        service: "knowledge2-icp-worker",
        mode: "seeded-worker",
        auth_required: false,
        protected_actions: ["k2_apply_sync"],
        k2_configured: Boolean(env.K2_API_KEY),
        apollo_configured: Boolean(env.APOLLO_API_KEY),
      }));
    }

    if (url.pathname.startsWith("/api/")) {
      return withSecurityHeaders(await handleApiRequest(request, env, url));
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

async function handleApiRequest(request, env, url) {
  const method = request.method.toUpperCase();
  const lists = await seedLists(env);
  if (method === "GET" && url.pathname === "/api/health") {
    return json({
      status: "ok",
      service: "knowledge2-icp",
      version: "0.1.0-worker",
      auth_required: false,
      protected_actions: ["k2_apply_sync"],
      mode: "seeded-worker",
      run_count: listRuns(lists).length,
      provider_status: providerStatus(env),
    });
  }

  if (method === "GET" && url.pathname === "/api/state") {
    return json(currentState(env, lists));
  }

  if (method === "POST" && url.pathname === "/api/criteria") {
    const payload = await readJson(request);
    const markdown = String(payload.markdown || "").trim();
    if (!markdown) return json({ error: "Criteria markdown is required." }, 400);
    runtime.criteria = criteriaPayload(`${markdown}\n`, "worker-runtime");
    return json({ criteria: runtime.criteria });
  }

  if (method === "POST" && url.pathname === "/api/search") {
    const payload = await readJson(request);
    const result = await discoverCandidates(payload, lists, env);
    return json(result);
  }

  if (method === "POST" && url.pathname === "/api/runs") {
    const payload = await readJson(request);
    const run = await createRuntimeRun(payload, lists, env);
    runtime.runs.set(run.id, run);
    return json(run);
  }

  if (method === "POST" && url.pathname === "/api/research") {
    const payload = await readJson(request);
    const run = loadRun(String(payload.run_id || ""), lists);
    if (!run) return json({ answer: "Run not found.", citations: [], matched_leads: [] }, 404);
    return json(localResearchAnswer(run, String(payload.question || "")));
  }

  const runMatch = url.pathname.match(/^\/api\/runs\/([^/]+)(?:\/([^/]+))?$/);
  if (runMatch) {
    const run = loadRun(runMatch[1], lists);
    if (!run) return json({ error: "Run not found." }, 404);
    const action = runMatch[2] || "";
    if (method === "GET" && !action) return json(run);
    if (method === "GET" && action === "prospects") return json(await buildRunProspectsWithApollo(run, env));
    if (method === "GET" && action === "prospects.csv") {
      const prospects = await buildRunProspectsWithApollo(run, env);
      return new Response(prospectsCsv(prospects.prospects), {
        headers: {
          "content-type": "text/csv; charset=utf-8",
          "cache-control": "no-store",
          "content-disposition": `attachment; filename="${run.id}-prospects.csv"`,
        },
      });
    }
    if (method === "GET" && action === "k2-manifest") return json(buildManifest(run, env));
    if (method === "POST" && action === "k2-export") {
      return json({ ...buildManifest(run, env), export_path: `worker://knowledge2-icp/${run.id}.json` });
    }
    if (method === "POST" && action === "k2-sync") {
      const payload = await readJson(request);
      const apply = Boolean(payload.apply);
      if (!apply) {
        return json({
          status: "dry_run",
          project_name: String(payload.project_name || "Knowledge2 ICP GTM"),
          corpus_name: String(payload.corpus_name || `ICP Run ${run.id}`),
          document_count: buildUploadDocuments(run).length,
          k2_configured: Boolean(env.K2_API_KEY),
          mode: "cloudflare-worker",
        });
      }
      const auth = authorizeApiRequest(request, env);
      if (!auth.configured) {
        return json({ error: "ICP_ADMIN_TOKEN is required for K2 apply sync." }, 503);
      }
      if (!auth.authorized) {
        return unauthorized("K2 apply token required.");
      }
      const result = await uploadToK2(env, run, {
        projectName: String(payload.project_name || "Knowledge2 ICP GTM"),
        corpusName: String(payload.corpus_name || `ICP Run ${run.id}`),
      });
      if (result.status === "uploaded") {
        run.k2 = result;
        runtime.runs.set(run.id, run);
      }
      return json(result, result.status === "error" ? 400 : 200);
    }
  }

  return json({ error: "Not found." }, 404);
}

async function seedLists(env) {
  if (runtime.seedLists) return runtime.seedLists;
  try {
    const response = await env.ASSETS.fetch(new Request("https://seed.local/seed-companies.json"));
    if (response.ok) {
      const payload = await response.json();
      const accounts = Array.isArray(payload.account_universe) ? payload.account_universe : [];
      if (accounts.length) {
        runtime.seedLists = {
          account_universe: normalizeSeedAccounts(accounts),
          priority_verticals: clone(SEED_LISTS.priority_verticals),
          sources: Array.isArray(payload.sources) ? payload.sources : [],
        };
        return runtime.seedLists;
      }
    }
  } catch {
    // Keep the small embedded fallback if the static seed asset is unavailable.
  }
  runtime.seedLists = clone(SEED_LISTS);
  return runtime.seedLists;
}

function normalizeSeedAccounts(accounts) {
  return accounts
    .map((account) => ({
      company: String(account.company || "").trim(),
      domain: normalizeDomain(account.domain || account.source_url || account.company || ""),
      category: String(account.category || account.source_group || "vertical market software").trim(),
      founded_year: account.founded_year || null,
      employee_count: account.employee_count || null,
      hq: String(account.hq || "").trim(),
      source_group: String(account.source_group || "").trim(),
      source_url: String(account.source_url || "").trim(),
      source: String(account.source || "").trim(),
      notes: String(account.notes || "").trim(),
      qualification: account.qualification && typeof account.qualification === "object" ? clone(account.qualification) : {},
    }))
    .filter((account) => account.company && account.domain);
}

function currentState(env, lists) {
  const runs = listRuns(lists);
  return {
    criteria: currentCriteria(),
    prompts: clone(SEED_PROMPTS),
    settings: clone(SEED_SETTINGS),
    lists: clone(lists),
    runs,
    provider_status: providerStatus(env),
    latest_run: loadRun(runs[0]?.id || SEED_RUN_ID, lists),
  };
}

function providerStatus(env) {
  return {
    apollo: { configured: Boolean(env.APOLLO_API_KEY), env: "APOLLO_API_KEY" },
    k2: {
      configured: Boolean(env.K2_API_KEY),
      env: "K2_API_KEY",
      base_url: env.K2_BASE_URL || "https://api.knowledge2.ai",
      research_corpus_configured: false,
    },
    github: { configured: false, env: "GITHUB_TOKEN", public_fallback: true },
    search: {
      configured: true,
      provider: env.SERPER_API_KEY || env.SERP_API_KEY
        ? "serper"
        : env.APOLLO_API_KEY
          ? "apollo-company-search"
          : "seeded-worker",
      serp_configured: Boolean(env.SERPER_API_KEY || env.SERP_API_KEY),
    },
  };
}

function currentCriteria() {
  return runtime.criteria || criteriaPayload(SEED_CRITERIA_MARKDOWN, "icp.md");
}

function criteriaPayload(markdown, source) {
  return {
    markdown,
    source,
    updated_at: SEED_CREATED_AT,
    hash: "seeded-icp-v1",
  };
}

function listRuns(lists) {
  const summaries = Array.from(runtime.runs.values()).map(runSummary);
  if (!runtime.runs.has(SEED_RUN_ID)) {
    summaries.push(runSummary(seedRun(lists)));
  }
  return summaries.sort((left, right) => String(right.created_at || "").localeCompare(String(left.created_at || "")));
}

function loadRun(runId, lists) {
  if (runtime.runs.has(runId)) return clone(runtime.runs.get(runId));
  if (runId === SEED_RUN_ID) return seedRun(lists);
  return null;
}

function runSummary(run) {
  const leads = run.leads || [];
  const scores = leads.map((lead) => Number(lead.score?.total_score || 0));
  return {
    id: run.id,
    query: run.query || "",
    created_at: run.created_at,
    status: run.status || "unknown",
    lead_count: leads.length,
    top_score: scores.length ? Math.max(...scores) : 0,
    tier_counts: tierCounts(leads),
    warnings: (run.warnings || []).slice(0, 5),
  };
}

function tierCounts(leads) {
  return leads.reduce((acc, lead) => {
    const tier = lead.score?.tier || "Unknown";
    acc[tier] = (acc[tier] || 0) + 1;
    return acc;
  }, {});
}

async function discoverCandidates(payload, lists, env = {}) {
  const fromSeedText = parseSeedText(String(payload.seed_text || ""));
  const query = String(payload.query || "").toLowerCase();
  const maxCompanies = Number(payload.max_companies || 10);
  const warnings = [];
  const live = query ? await discoverLiveCandidates(query, maxCompanies, env, warnings) : [];
  const terms = queryTerms(query);
  const seeded = lists.account_universe
    .map((item) => ({ item, rank: seedMatchScore(item, terms) }))
    .filter((item) => {
      if (!query) return true;
      return item.rank > 0;
    })
    .sort((left, right) => right.rank - left.rank || Number(right.item.qualification?.total_score || 0) - Number(left.item.qualification?.total_score || 0) || String(left.item.company || "").localeCompare(String(right.item.company || "")))
    .map(({ item }) => candidateFromAccount(item, "Seeded local account list"));
  const candidates = dedupeCandidates([...fromSeedText, ...seeded, ...live]).slice(0, maxCompanies);
  if (!candidates.length && !warnings.length) warnings.push("No candidates matched the request.");
  return { candidates, warnings };
}

async function discoverLiveCandidates(query, maxCompanies, env, warnings) {
  if (!query.trim()) return [];
  if (env.SERPER_API_KEY || env.SERP_API_KEY) {
    const result = await serperSearchCompanies(env, query, maxCompanies);
    if (result.status === "ok") return result.candidates;
    warnings.push(result.reason || "Serper search failed.");
  }
  if (env.APOLLO_API_KEY) {
    const result = await apolloSearchOrganizations(env, query, maxCompanies);
    if (result.status === "ok") return result.candidates;
    warnings.push(result.reason || "Apollo company search failed.");
  }
  if (!env.SERPER_API_KEY && !env.SERP_API_KEY && !env.APOLLO_API_KEY) {
    warnings.push("Live SERP discovery is not configured; using seeded accounts and manual seed text only.");
  }
  return [];
}

function seedMatchScore(item, terms) {
  if (!terms.length) return 1;
  const weighted = [
    [String(item.company || ""), 4],
    [String(item.domain || ""), 3],
    [String(item.category || ""), 3],
    [String(item.notes || ""), 2],
    [String(item.source_group || ""), 1],
  ];
  return weighted.reduce((score, [value, weight]) => {
    const haystack = value.toLowerCase();
    return score + terms.filter((term) => haystack.includes(term)).length * weight;
  }, 0);
}

async function serperSearchCompanies(env, query, maxCompanies) {
  const apiKey = env.SERPER_API_KEY || env.SERP_API_KEY;
  const baseUrl = String(env.SERPER_BASE_URL || "https://google.serper.dev").replace(/\/+$/, "");
  try {
    const response = await fetch(`${baseUrl}/search`, {
      method: "POST",
      headers: {
        accept: "application/json",
        "content-type": "application/json",
        "user-agent": "Knowledge2ICPWorker/0.1",
        "x-api-key": apiKey,
      },
      body: JSON.stringify({ q: query, num: Math.max(10, Math.min(Number(maxCompanies || 10) * 2, 100)) }),
    });
    if (!response.ok) return { status: "error", reason: `Serper returned HTTP ${response.status}.`, candidates: [] };
    const payload = await response.json();
    return {
      status: "ok",
      candidates: candidatesFromSearchResults(Array.isArray(payload.organic) ? payload.organic : [], "Serper SERP result", maxCompanies),
    };
  } catch (error) {
    return { status: "error", reason: `Serper search failed: ${error?.message || error}`, candidates: [] };
  }
}

async function apolloSearchOrganizations(env, query, maxCompanies) {
  const baseUrl = String(env.APOLLO_BASE_URL || "https://api.apollo.io/api/v1").replace(/\/+$/, "");
  const params = new URLSearchParams();
  params.append("per_page", String(Math.max(10, Math.min(Number(maxCompanies || 10) * 2, 100))));
  params.append("q_keywords", query);
  try {
    const response = await fetch(`${baseUrl}/mixed_companies/search?${params.toString()}`, {
      method: "POST",
      headers: {
        accept: "application/json",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "user-agent": "Knowledge2ICPWorker/0.1",
        "x-api-key": env.APOLLO_API_KEY,
      },
      body: "{}",
    });
    if (!response.ok) return { status: "error", reason: `Apollo returned HTTP ${response.status}.`, candidates: [] };
    const payload = await response.json();
    const items = Array.isArray(payload.organizations) ? payload.organizations : Array.isArray(payload.accounts) ? payload.accounts : [];
    return { status: "ok", candidates: candidatesFromApolloOrganizations(items, maxCompanies, queryTerms(query)) };
  } catch (error) {
    return { status: "error", reason: `Apollo company search failed: ${error?.message || error}`, candidates: [] };
  }
}

function candidatesFromSearchResults(items, sourceTitle, maxCompanies) {
  const candidates = [];
  for (const item of items) {
    const link = String(item?.link || item?.url || "").trim();
    const title = String(item?.title || "").trim();
    const snippet = String(item?.snippet || "").trim();
    const domain = companyDomainFromUrl(link);
    if (!domain || isBlockedDiscoveryDomain(domain) || candidates.some((candidate) => candidate.domain === domain)) continue;
    candidates.push({
      company: companyNameFromTitleOrDomain(title, domain),
      domain,
      source_url: link || `https://${domain}`,
      source_title: title || sourceTitle,
      notes: snippet ? `${sourceTitle}: ${snippet}` : sourceTitle,
      github_urls: [],
      linkedin_urls: [],
      other_urls: [],
    });
    if (candidates.length >= maxCompanies) break;
  }
  return candidates;
}

function candidatesFromApolloOrganizations(items, maxCompanies, terms) {
  const candidates = [];
  for (const item of items) {
    if (!item || typeof item !== "object") continue;
    const domain = companyDomainFromUrl(item.website_url || item.primary_domain || item.domain || "");
    if (!domain || isBlockedDiscoveryDomain(domain) || candidates.some((candidate) => candidate.domain === domain)) continue;
    const haystack = [
      item.name,
      domain,
      item.industry,
      item.short_description,
      item.seo_description,
      ...(Array.isArray(item.keywords) ? item.keywords : []),
    ].join(" ").toLowerCase();
    if (terms.length && !terms.some((term) => haystack.includes(term))) continue;
    const location = [item.city, item.state, item.country].map((part) => String(part || "").trim()).filter(Boolean).join(", ");
    const employeeCount = item.estimated_num_employees ? `${item.estimated_num_employees} employees` : "";
    candidates.push({
      company: String(item.name || companyNameFromTitleOrDomain("", domain)),
      domain,
      source_url: item.website_url || `https://${domain}`,
      source_title: "Apollo company search",
      notes: [item.industry, employeeCount, location].filter(Boolean).join(" · ") || "Discovered from Apollo company search.",
      github_urls: [],
      linkedin_urls: item.linkedin_url ? [String(item.linkedin_url)] : [],
      other_urls: [],
    });
    if (candidates.length >= maxCompanies) break;
  }
  return candidates;
}

function parseSeedText(seedText) {
  return seedText
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const parts = line.split(",").map((part) => part.trim()).filter(Boolean);
      const company = parts[0] || "";
      const domain = normalizeDomain(parts[1] || company);
      return company && domain ? {
        company,
        domain,
        source_url: `https://${domain}`,
        source_title: "Manual seed",
        notes: "Manually seeded by operator.",
        github_urls: [],
        linkedin_urls: [],
        other_urls: [],
      } : null;
    })
    .filter(Boolean);
}

function candidateFromAccount(account, sourceTitle) {
  return {
    company: account.company,
    domain: account.domain,
    source_url: account.source_url || `https://${account.domain}`,
    source_title: sourceTitle,
    notes: account.notes,
    github_urls: account.domain === "moj.io" ? ["https://github.com/mojio"] : [],
    linkedin_urls: account.domain === "moj.io" ? ["https://www.linkedin.com/company/mojio"] : [],
    other_urls: [],
  };
}

function dedupeCandidates(candidates) {
  const seen = new Set();
  const result = [];
  for (const candidate of candidates) {
    const key = normalizeDomain(candidate.domain || "");
    if (!key || seen.has(key)) continue;
    seen.add(key);
    result.push({ ...candidate, domain: key });
  }
  return result;
}

async function createRuntimeRun(payload, lists, env = {}) {
  let discoveryWarnings = [];
  let candidates;
  if (Array.isArray(payload.candidates) && payload.candidates.length) {
    candidates = dedupeCandidates(payload.candidates);
  } else {
    const discovery = await discoverCandidates(payload, lists, env);
    candidates = discovery.candidates;
    discoveryWarnings = discovery.warnings || [];
  }
  const runId = `run-worker-${Date.now().toString(36)}`;
  const leads = candidates.slice(0, Number(payload.max_companies || 8)).map((candidate) => leadFromCandidate(runId, candidate, lists));
  leads.sort((left, right) => Number(right.score.total_score || 0) - Number(left.score.total_score || 0));
  const run = {
    id: runId,
    query: String(payload.query || ""),
    created_at: new Date().toISOString().replace(/\.\d{3}Z$/, "+00:00"),
    status: "completed",
    criteria: {
      hash: currentCriteria().hash,
      source: currentCriteria().source,
      updated_at: currentCriteria().updated_at,
      profile: seededCriteriaProfile(lists),
    },
    warnings: candidates.length ? discoveryWarnings : ["No selected candidates were provided for this run.", ...discoveryWarnings],
    leads,
  };
  run.k2 = {
    status: "ready_for_sdk_sync",
    reason: "Worker run can be exported or uploaded from the K2 tab.",
    document_count: buildManifest(run, {}).document_count,
  };
  return run;
}

function leadFromCandidate(runId, candidate, lists) {
  const account = lists.account_universe.find((item) => item.domain === normalizeDomain(candidate.domain));
  if (account) return seedLead(runId, account, candidate);
  const accountFromCandidate = {
    company: candidate.company || candidate.domain,
    domain: normalizeDomain(candidate.domain),
    category: "",
    founded_year: null,
    employee_count: null,
    hq: "",
    notes: candidate.notes || "Runtime selected candidate.",
  };
  return seedLead(runId, accountFromCandidate, candidate);
}

function seedRun(lists) {
  const leads = lists.account_universe
    .map((account) => seedLead(SEED_RUN_ID, account, candidateFromAccount(account, account.source_group || "Seeded account universe")))
    .sort((left, right) => Number(right.score?.total_score || 0) - Number(left.score?.total_score || 0) || String(left.score?.company?.company || "").localeCompare(String(right.score?.company?.company || "")));
  return {
    id: SEED_RUN_ID,
    query: SEED_SETTINGS.default_query,
    created_at: SEED_CREATED_AT,
    status: "completed",
    criteria: {
      hash: "seeded-icp-v1",
      source: "icp.md",
      updated_at: SEED_CREATED_AT,
      profile: seededCriteriaProfile(lists),
    },
    warnings: [],
    k2: {
      status: "uploaded",
      project_id: "357b922f-6024-4b3e-bf32-3d0d39deed42",
      project_name: "Knowledge2 ICP GTM Dev",
      corpus_id: "3cf7ba62-c57a-4e32-abea-97479fd55aaa",
      corpus_name: "Seeded ICP GTM Dashboard",
      document_count: leads.length * 6,
    },
    leads,
  };
}

function seededCriteriaProfile(lists) {
  return {
    source: "icp.md",
    hash: "seeded-icp-v1",
    tier_a_threshold: 75,
    tier_b_threshold: 60,
    min_employee_count: 25,
    max_employee_count: 2000,
    priority_terms: clone(lists.priority_verticals || SEED_LISTS.priority_verticals),
    warnings: [],
  };
}

function seedLead(runId, account, candidate) {
  const qualification = account.qualification && typeof account.qualification === "object" ? account.qualification : {};
  const qualifiedTier = String(qualification.tier || "");
  const reject = qualifiedTier === "Reject" || account.domain === "example.com" || String(account.category || "").toLowerCase().includes("ai agents");
  const vertical = verticalFor(account);
  const highPriority = isHighPriorityVertical(vertical);
  const tier = qualifiedTier || (reject ? "Reject" : highPriority ? "A" : "B");
  const score = qualifiedNumber(qualification, "total_score", reject ? 24 : account.domain === "moj.io" ? 82 : highPriority ? 79 : 68);
  const aiPosture = qualifiedNumber(qualification, "ai_posture", reject ? 5 : 0);
  const dataWorkflow = Math.max(0, Math.min(5, Math.round(qualifiedNumber(qualification, "data_workflow_score", reject ? 5 : account.domain === "moj.io" ? 25 : 22) / 5)));
  const feasibility = Math.max(0, Math.min(5, Math.round(qualifiedNumber(qualification, "feasibility_score", reject ? 4 : 8) / 2)));
  const docsUrl = account.domain === "moj.io"
    ? "https://moj.io/docs/api"
    : account.domain === "automate.co.za"
      ? "https://www.automate.co.za/solutions"
      : "";
  const githubUrl = account.domain === "moj.io" ? "https://github.com/mojio" : "";
  const linkedinUrl = candidate.linkedin_urls?.[0] || (account.domain === "automate.co.za" ? "https://www.linkedin.com/company/automate-dms" : "");
  const evidenceText = evidenceTextFor(account);
  const sourceRefs = {
    careers_urls: [],
    contact_urls: [],
    docs_urls: docsUrl ? [docsUrl] : [],
    github_urls: githubUrl ? [githubUrl] : [],
    linkedin_urls: linkedinUrl ? [linkedinUrl] : [],
    marketplace_urls: [],
    other_urls: [],
    pricing_urls: [],
    social_urls: [],
  };
  const signalTags = reject ? ["ai-native"] : ["workflow", "data", "commercial", ...(docsUrl ? ["integration"] : []), ...(Object.keys(qualification).length ? ["qualified-data"] : [])];
  const personas = reject ? [{
    title: "Do Not Prospect",
    priority: "reject",
    rationale: "Negative-control account for the seeded list.",
    apollo_titles: [],
  }] : personasFor(vertical);

  return {
    id: `${runId}:${account.domain}`,
    candidate: {
      source_url: candidate.source_url || `https://${account.domain}`,
      source_title: candidate.source_title || "Seeded local account list",
      github_urls: sourceRefs.github_urls,
      linkedin_urls: sourceRefs.linkedin_urls,
      other_urls: candidate.other_urls || [],
    },
    score: {
      company: account,
      gates: gatesFor(account, reject),
      classification: {
        ai_posture: aiPosture,
        data_workflow: dataWorkflow,
        commercial_urgency: reject ? 1 : 3,
        budget_access: reject ? 1 : 3,
        feasibility,
        reasons: {
          ai_posture: reject ? "AI-native positioning is a seeded reject signal." : "No deep public AI positioning in the local seed notes.",
          data_workflow: `Signals include ${vertical} workflow data and operational systems.`,
          criteria: "Scored with seeded local ICP criteria.",
        },
        evidence_ids: {
          ai_posture: ["seed-evidence"],
          data_workflow: ["seed-evidence"],
          commercial_urgency: ["seed-evidence"],
          feasibility: docsUrl ? ["seed-evidence"] : [],
        },
        confidence: Object.keys(qualification).length && !reject ? 0.82 : reject ? 0.55 : 0.72,
        source: qualification.classification_source || "seed",
      },
      ai_gap_score: qualifiedNumber(qualification, "ai_gap_score", reject ? 0 : 30),
      data_workflow_score: qualifiedNumber(qualification, "data_workflow_score", reject ? 5 : account.domain === "moj.io" ? 25 : 22),
      commercial_urgency_score: qualifiedNumber(qualification, "commercial_urgency_score", reject ? 3 : 14),
      budget_access_score: qualifiedNumber(qualification, "budget_access_score", reject ? 2 : 12),
      feasibility_score: qualifiedNumber(qualification, "feasibility_score", reject ? 4 : 8),
      total_score: score,
      tier,
      next_action: qualification.next_action || (reject
        ? "Reject from this ICP; keep only as a negative-control list item."
        : "Prioritize for Apollo enrichment and human account research."),
      warnings: Array.isArray(qualification.warnings) && qualification.warnings.length ? qualification.warnings : reject ? ["Fails seeded hard gates for pre-2025 non-AI-native incumbents."] : [],
      hard_gate_failed: typeof qualification.hard_gate_failed === "boolean" ? qualification.hard_gate_failed : reject,
      hard_gate_unknown: typeof qualification.hard_gate_unknown === "boolean" ? qualification.hard_gate_unknown : false,
    },
    strategy: {
      headline: `${account.company}: ${reject ? "not a fit for the incumbent-software ICP" : "turn proprietary workflow data into a visible AI product narrative"}`,
      wedge: reject ? "reject or reposition toward AI governance" : "turn proprietary workflow data into a visible AI product narrative",
      urgency: "Peers are adding AI; durable differentiation depends on proprietary workflow data.",
      offer: reject
        ? "Do not outbound from this list."
        : `Propose a 2-week AI opportunity map for ${vertical} workflows, grounded in existing product data and metadata.`,
      outreach_angle: reject
        ? "Not a fit: public positioning is AI-native or too early for this incumbent-software ICP."
        : `${account.company} appears to have meaningful ${vertical} data but limited public AI positioning.`,
      first_step: reject ? "Keep as a reject control." : "Enrich product, engineering, data, and vertical-GM contacts in Apollo.",
      objections: ["Verify current AI roadmap ownership and commercial urgency."],
      personas,
      apollo_titles: [...new Set(personas.flatMap((persona) => persona.apollo_titles || []))].sort(),
    },
    evidence: [{
      evidence_id: "seed-evidence",
      url: candidate.source_url || `https://${account.domain}`,
      title: "Seeded local evidence",
      text: evidenceText,
      source_type: "website",
      metadata: {
        page_category: reject ? "company" : "product",
        links: [docsUrl, githubUrl, linkedinUrl].filter(Boolean),
        external_links: [githubUrl, linkedinUrl].filter(Boolean),
      },
    }],
    metadata: {
      company: account.company,
      domain: account.domain,
      criteria_profile: seededCriteriaProfile(SEED_LISTS),
      source_counts: { [reject ? "website:company" : "website:product"]: 1 },
      source_refs: sourceRefs,
      signal_tags: signalTags,
      public_profile_count: sourceRefs.github_urls.length + sourceRefs.linkedin_urls.length,
      public_resource_count: sourceRefs.docs_urls.length,
      public_emails: [],
      intelligence_coverage: {
        has_contact_path: false,
        has_docs_or_api: Boolean(docsUrl),
        has_github_profile: Boolean(githubUrl),
        has_marketplace_profile: false,
        has_pricing_or_commercial: !reject,
        has_social_profile: Boolean(linkedinUrl),
        has_website_evidence: true,
      },
      evidence_metadata: [{
        evidence_id: "seed-evidence",
        url: candidate.source_url || `https://${account.domain}`,
        title: "Seeded local evidence",
        source_type: "website",
        page_category: reject ? "company" : "product",
        signal_tags: signalTags,
        link_count: [docsUrl, githubUrl, linkedinUrl].filter(Boolean).length,
        external_link_count: [githubUrl, linkedinUrl].filter(Boolean).length,
      }],
      k2_metadata_preview: {
        company: account.company,
        domain: account.domain,
        signal_tags: signalTags,
        source_count: 1,
        source_types: [reject ? "website:company" : "website:product"],
      },
      apollo_organizations: {
        status: "seeded",
        reason: "Seeded account list is available before live Apollo enrichment.",
        organizations: [],
      },
      qualification,
    },
  };
}

function verticalFor(account) {
  const text = `${account.category || ""} ${account.notes || ""}`.toLowerCase();
  if (text.includes("dealer") || text.includes("automotive")) return "dealership";
  if (text.includes("fleet") || text.includes("telematics") || text.includes("mobility") || text.includes("transport")) return "fleet";
  if (text.includes("claim") || text.includes("risk")) return "claims";
  if (text.includes("health") || text.includes("medical") || text.includes("patient")) return "healthcare admin";
  if (text.includes("utility") || text.includes("public") || text.includes("government") || text.includes("municipal")) return "govtech";
  if (text.includes("asset") || text.includes("field") || text.includes("logistics") || text.includes("maintenance")) return "field service";
  if (text.includes("education") || text.includes("student")) return "education admin";
  if (text.includes("food") || text.includes("hospitality")) return "hospitality";
  return text.includes("ai") ? "AI-native" : "workflow";
}

function isHighPriorityVertical(vertical) {
  return ["dealership", "fleet", "claims", "healthcare admin", "govtech", "field service"].includes(vertical);
}

function qualifiedNumber(qualification, key, fallback) {
  const value = qualification?.[key];
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function evidenceTextFor(account) {
  if (account.domain === "moj.io") {
    return "Founded in 2012. Enterprise software platform for fleet workflow, dispatch, telematics records, integrations, API, permissions, analytics, and customer operations.";
  }
  if (account.domain === "automate.co.za") {
    return "40+ years of dealership-management software experience, trusted by 1,000+ dealerships with inventory, transactions, reporting, BI, and operational workflow data.";
  }
  return account.notes || `${account.company} is listed in a seeded official vertical-market software portfolio. Verify AI posture, founded date, budget, and workflow depth before outbound.`;
}

function gatesFor(account, reject) {
  if (reject) {
    return [
      { name: "Founded before 2025", status: "fail", reason: `Founded year ${account.founded_year}.`, evidence_ids: [] },
      { name: "Product company", status: "pass", reason: "Seeded software product.", evidence_ids: [] },
      { name: "B2B or B2B2C", status: "unknown", reason: "Negative-control account.", evidence_ids: [] },
      { name: "Has proprietary workflow/data", status: "unknown", reason: "No incumbent workflow data proved.", evidence_ids: [] },
      { name: "Enough budget", status: "fail", reason: "Below seeded employee range.", evidence_ids: [] },
      { name: "Not AI-native", status: "fail", reason: "AI-native category.", evidence_ids: [] },
    ];
  }
  return [
    {
      name: "Founded before 2025",
      status: account.founded_year ? "pass" : "unknown",
      reason: account.founded_year ? `Founded year ${account.founded_year}.` : "Official incumbent-software portfolio seed; founded date needs verification.",
      evidence_ids: [],
    },
    { name: "Product company", status: "pass", reason: "Seeded software platform evidence.", evidence_ids: [] },
    { name: "B2B or B2B2C", status: "pass", reason: "Business customer and partner workflows.", evidence_ids: [] },
    { name: "Has proprietary workflow/data", status: "pass", reason: "Operational workflow and data signals.", evidence_ids: [] },
    { name: "Enough budget", status: "pass", reason: "Inside seeded employee range.", evidence_ids: [] },
    { name: "Not AI-native", status: "pass", reason: "No AI-native founding/category signal.", evidence_ids: [] },
  ];
}

function personasFor(vertical) {
  return [
    {
      title: `VP ${titleCase(vertical)} Product`,
      priority: "primary",
      rationale: "Vertical owner likely cares about workflow depth and AI differentiation.",
      apollo_titles: [`vp ${vertical} product`, "vp product", "general manager"],
    },
    {
      title: "Chief Product Officer",
      priority: "primary",
      rationale: "Owns AI product strategy, roadmap tradeoffs, and customer-facing differentiation.",
      apollo_titles: ["chief product officer", "vp product", "head of product"],
    },
    {
      title: "VP Engineering",
      priority: "primary",
      rationale: "Owns integration architecture and delivery capacity for workflow AI.",
      apollo_titles: ["vp engineering", "head of engineering", "chief technology officer"],
    },
    {
      title: "Chief Data Officer",
      priority: "secondary",
      rationale: "Owns proprietary data readiness, governance, and metadata quality.",
      apollo_titles: ["chief data officer", "head of data", "vp data"],
    },
  ];
}

async function buildRunProspectsWithApollo(run, env = {}) {
  if (!env.APOLLO_API_KEY) {
    return {
      ...buildRunProspects(run),
      enrichment: { provider: "apollo", configured: false, status: "skipped", reason: "APOLLO_API_KEY is not configured." },
    };
  }

  const apolloPeopleByDomain = {};
  const errors = [];
  const leadsForApollo = (run.leads || [])
    .filter((lead) => lead.score?.tier !== "Reject")
    .sort((left, right) => Number(right.score?.total_score || 0) - Number(left.score?.total_score || 0))
    .slice(0, MAX_APOLLO_ENRICH_LEADS);
  for (const lead of leadsForApollo) {
    if (lead.score?.tier === "Reject") continue;
    const company = lead.score?.company || {};
    const domain = String(company.domain || "").trim().toLowerCase();
    if (!domain) continue;
    const titles = [...new Set((lead.strategy?.apollo_titles || []).map((title) => String(title || "").trim()).filter(Boolean))];
    const result = await apolloSearchPeople(env, domain, titles);
    if (result.status === "ok" && result.people.length) {
      apolloPeopleByDomain[domain] = result.people;
    } else if (result.status === "error") {
      errors.push({ domain, reason: result.reason });
    }
  }

  const payload = buildRunProspects(run, { apolloPeopleByDomain });
  const apolloCount = payload.source_counts.apollo || 0;
  return {
    ...payload,
    enrichment: {
      provider: "apollo",
      configured: true,
      status: apolloCount ? "ok" : errors.length ? "fallback" : "empty",
      errors: errors.slice(0, 3),
    },
  };
}

async function apolloSearchPeople(env, domain, titles) {
  const baseUrl = String(env.APOLLO_BASE_URL || "https://api.apollo.io/api/v1").replace(/\/+$/, "");
  const params = new URLSearchParams();
  params.append("per_page", "8");
  params.append("q_organization_domains_list[]", domain);
  params.append("include_similar_titles", "true");
  for (const title of titles.length ? titles : ["chief product officer", "vp product", "vp engineering", "chief data officer"]) {
    params.append("person_titles[]", title);
  }
  const response = await fetch(`${baseUrl}/mixed_people/api_search?${params.toString()}`, {
    method: "POST",
    headers: {
      accept: "application/json",
      "cache-control": "no-cache",
      "content-type": "application/json",
      "user-agent": "Knowledge2ICPWorker/0.1",
      "x-api-key": env.APOLLO_API_KEY,
    },
    body: "{}",
  });
  if (!response.ok) {
    return { status: "error", reason: `Apollo returned HTTP ${response.status}.`, people: [] };
  }
  const payload = await response.json();
  const people = compactApolloPeople(payload);
  const enriched = await apolloBulkMatchPeople(env, people);
  return { status: "ok", people: enriched.length ? mergeApolloPeople(people, enriched) : people };
}

async function apolloBulkMatchPeople(env, people) {
  const details = people
    .filter((person) => person.id)
    .slice(0, 10)
    .map((person) => ({ id: person.id }));
  if (!details.length) return [];
  const baseUrl = String(env.APOLLO_BASE_URL || "https://api.apollo.io/api/v1").replace(/\/+$/, "");
  const response = await fetch(`${baseUrl}/people/bulk_match?reveal_personal_emails=false&reveal_phone_number=false`, {
    method: "POST",
    headers: {
      accept: "application/json",
      "cache-control": "no-cache",
      "content-type": "application/json",
      "user-agent": "Knowledge2ICPWorker/0.1",
      "x-api-key": env.APOLLO_API_KEY,
    },
    body: JSON.stringify({ details }),
  });
  if (!response.ok) return [];
  const payload = await response.json();
  return compactApolloPeople({ people: Array.isArray(payload.matches) ? payload.matches : [] });
}

function mergeApolloPeople(searchPeople, enrichedPeople) {
  const enrichedById = new Map(enrichedPeople.map((person) => [person.id, person]));
  return searchPeople.map((person) => ({ ...person, ...(enrichedById.get(person.id) || {}) }));
}

function compactApolloPeople(payload) {
  const rawItems = Array.isArray(payload.people) ? payload.people : Array.isArray(payload.contacts) ? payload.contacts : [];
  return rawItems.slice(0, 20).filter((item) => item && typeof item === "object").map((item) => {
    const org = item.organization && typeof item.organization === "object" ? item.organization : {};
    const contact = item.contact && typeof item.contact === "object" ? item.contact : {};
    const phone = Array.isArray(contact.phone_numbers) && contact.phone_numbers[0]?.sanitized_number
      ? contact.phone_numbers[0].sanitized_number
      : contact.sanitized_phone || item.sanitized_phone || "";
    return {
      id: item.id || "",
      name: item.name || contact.name || "",
      title: item.title || contact.title || "",
      email: item.email || contact.email || "",
      email_status: item.email_status || contact.email_status || "",
      linkedin_url: item.linkedin_url || contact.linkedin_url || "",
      phone,
      city: item.city || "",
      state: item.state || "",
      country: item.country || "",
      organization: {
        id: org.id || "",
        name: org.name || "",
        website_url: org.website_url || "",
        linkedin_url: org.linkedin_url || "",
      },
    };
  });
}

function buildRunProspects(run, options = {}) {
  const apolloPeopleByDomain = options.apolloPeopleByDomain || {};
  const prospects = [];
  for (const lead of run.leads || []) {
    if (lead.score?.tier === "Reject") continue;
    const company = lead.score.company;
    const domain = String(company.domain || "").trim().toLowerCase();
    const apolloPeople = apolloPeopleByDomain[domain] || [];
    if (apolloPeople.length) {
      for (const [index, person] of apolloPeople.entries()) {
        prospects.push(personProspect(run, lead, person, index + 1));
      }
      continue;
    }
    for (const [index, persona] of (lead.strategy?.personas || []).entries()) {
      prospects.push({
        id: `${lead.id}:persona:${index + 1}`,
        run_id: run.id,
        lead_id: lead.id,
        company: company.company,
        domain: company.domain,
        tier: lead.score.tier,
        company_score: lead.score.total_score,
        status: "persona_target",
        source: "strategy",
        name: persona.title,
        title: persona.title,
        persona: persona.title,
        persona_priority: persona.priority,
        priority_score: Number(lead.score.total_score || 0) + (persona.priority === "primary" ? 18 : 8),
        linkedin_url: "",
        email: "",
        location: "",
        organization_name: company.company,
        outreach_angle: lead.strategy.outreach_angle,
        first_step: lead.strategy.first_step,
      });
    }
  }
  prospects.sort((left, right) => Number(right.priority_score || 0) - Number(left.priority_score || 0));
  return {
    run_id: run.id,
    prospect_count: prospects.length,
    source_counts: sourceCounts(prospects),
    prospects,
  };
}

function personProspect(run, lead, person, index) {
  const company = lead.score.company;
  const persona = matchPersona(String(person.title || ""), lead.strategy?.personas || []);
  const location = [person.city, person.state, person.country].map((part) => String(part || "").trim()).filter(Boolean).join(", ");
  const personKey = person.id || person.linkedin_url || person.email || person.title || index;
  return {
    id: `${lead.id}:apollo:${slug(String(personKey))}`,
    run_id: run.id,
    lead_id: lead.id,
    company: company.company,
    domain: company.domain,
    tier: lead.score.tier,
    company_score: lead.score.total_score,
    status: "person_found",
    source: "apollo",
    name: person.name || person.title || "Apollo contact",
    title: person.title || "",
    persona: persona.title || person.title || "",
    persona_priority: persona.priority || "unknown",
    priority_score: Number(lead.score.total_score || 0) + (persona.priority === "primary" ? 18 : 8) + 10,
    linkedin_url: person.linkedin_url || "",
    email: person.email || "",
    email_status: person.email_status || "",
    phone: person.phone || "",
    location,
    organization_name: person.organization?.name || company.company,
    outreach_angle: lead.strategy.outreach_angle,
    first_step: lead.strategy.first_step,
  };
}

function matchPersona(title, personas) {
  const titleTerms = terms(title);
  let best = {};
  let bestScore = 0;
  for (const persona of personas) {
    const haystack = `${persona.title || ""} ${(persona.apollo_titles || []).join(" ")}`;
    const overlap = [...titleTerms].filter((term) => terms(haystack).has(term)).length;
    if (overlap > bestScore) {
      best = persona;
      bestScore = overlap;
    }
  }
  return best.title ? best : personas[0] || {};
}

function sourceCounts(prospects) {
  return prospects.reduce((acc, prospect) => {
    const source = String(prospect.source || "unknown");
    acc[source] = (acc[source] || 0) + 1;
    return acc;
  }, {});
}

function prospectsCsv(prospects) {
  const fields = ["run_id", "lead_id", "company", "domain", "tier", "company_score", "priority_score", "source", "status", "name", "title", "persona", "persona_priority", "linkedin_url", "email", "phone", "location", "organization_name", "outreach_angle", "first_step"];
  return `${fields.join(",")}\n${prospects.map((row) => fields.map((field) => csvCell(row[field])).join(",")).join("\n")}\n`;
}

function csvCell(value) {
  const text = String(value ?? "");
  if (/[",\n]/.test(text)) return `"${text.replaceAll('"', '""')}"`;
  return text;
}

function localResearchAnswer(run, question) {
  const leads = (run.leads || []).filter((lead) => lead.score?.tier !== "Reject");
  const top = leads.slice(0, 3);
  const matched = top.map((lead) => lead.id);
  const citations = top.flatMap((lead) => (lead.evidence || []).slice(0, 1).map((item) => ({
    company: lead.score.company.company,
    domain: lead.score.company.domain,
    url: item.url,
    evidence_id: item.evidence_id,
    snippet: item.text,
    source_type: item.source_type || "website",
    page_category: item.metadata?.page_category || "product",
    signal_tags: lead.metadata?.signal_tags || [],
  })));
  const answer = [
    `Recommended GTM motion for: ${question || "seeded ICP review"}`,
    "",
    ...top.map((lead) => `- ${lead.score.company.company}: Tier ${lead.score.tier}, score ${lead.score.total_score}. ${lead.strategy.outreach_angle}`),
    "",
    "Use Apollo for the seeded product, engineering, data, and vertical-owner personas, then export the K2 manifest with run_id and criteria_hash metadata.",
  ].join("\n");
  return {
    answer,
    citations,
    matched_leads: matched,
    provider: "local",
    metadata_used: {
      signal_tags: [...new Set(top.flatMap((lead) => lead.metadata?.signal_tags || []))],
      source_types: ["website"],
      page_categories: ["product"],
      coverage: ["has_website_evidence", "has_docs_or_api"],
      persona_titles: [...new Set(top.flatMap((lead) => (lead.strategy?.personas || []).map((persona) => persona.title)))],
      criteria_hashes: [run.criteria?.hash || "seeded-icp-v1"],
    },
  };
}

function buildManifest(run, env = {}) {
  const documents = buildDocuments(run);
  return {
    status: "ready",
    k2_configured: Boolean(env.K2_API_KEY),
    base_url: env.K2_BASE_URL || "https://api.knowledge2.ai",
    run_id: run.id,
    query: run.query,
    document_count: documents.length,
    metadata_keys: [...new Set(documents.flatMap((document) => Object.keys(document.metadata || {})))].sort(),
    documents,
  };
}

function buildDocuments(run) {
  const documents = [];
  for (const lead of run.leads || []) {
    const score = lead.score || {};
    const company = score.company || {};
    const strategy = lead.strategy || {};
    const leadMetadata = lead.metadata || {};
    const sourceRefs = leadMetadata.source_refs || {};
    documents.push({
      id: `${run.id}:${company.domain}:account-summary`,
      text: [
        `Company: ${company.company} (${company.domain})`,
        `Tier: ${score.tier} score ${score.total_score}`,
        `Criteria: Tier A >= 75, Tier B >= 60, employee range 25-2000`,
        `Strategy: ${strategy.outreach_angle}`,
        `Offer: ${strategy.offer}`,
        `Personas: ${(strategy.personas || []).map((persona) => persona.title).join(", ")}`,
        `Signals: ${(leadMetadata.signal_tags || []).join(", ")}`,
      ].join("\n"),
      metadata: {
        run_id: run.id,
        query: run.query,
        criteria_hash: run.criteria?.hash,
        company: company.company,
        domain: company.domain,
        tier: score.tier,
        total_score: score.total_score,
        ai_posture: score.classification?.ai_posture,
        source_type: "account_summary",
        page_category: "summary",
        source_url: company.domain,
        evidence_id: "account-summary",
        signal_tags: leadMetadata.signal_tags || [],
        github_urls: sourceRefs.github_urls || [],
        linkedin_urls: sourceRefs.linkedin_urls || [],
        docs_urls: sourceRefs.docs_urls || [],
        public_profile_count: leadMetadata.public_profile_count || 0,
        public_resource_count: leadMetadata.public_resource_count || 0,
        persona_titles: (strategy.personas || []).map((persona) => persona.title),
        outreach_angle: strategy.outreach_angle,
      },
    });
    for (const item of lead.evidence || []) {
      documents.push({
        id: `${run.id}:${company.domain}:${item.evidence_id}`,
        text: item.text || "",
        metadata: {
          run_id: run.id,
          query: run.query,
          criteria_hash: run.criteria?.hash,
          company: company.company,
          domain: company.domain,
          tier: score.tier,
          total_score: score.total_score,
          ai_posture: score.classification?.ai_posture,
          source_type: item.source_type || "website",
          page_category: item.metadata?.page_category || "product",
          source_url: item.url,
          source_title: item.title,
          evidence_id: item.evidence_id,
          signal_tags: leadMetadata.signal_tags || [],
          persona_titles: (strategy.personas || []).map((persona) => persona.title),
          outreach_angle: strategy.outreach_angle,
        },
      });
    }
  }
  for (const prospect of buildRunProspects(run).prospects) {
    documents.push({
      id: `${prospect.id}:prospect`,
      text: [
        `Company: ${prospect.company} (${prospect.domain})`,
        `Prospect: ${prospect.name}`,
        `Title: ${prospect.title}`,
        `Persona: ${prospect.persona} (${prospect.persona_priority})`,
        `Outreach angle: ${prospect.outreach_angle}`,
      ].join("\n"),
      metadata: {
        run_id: run.id,
        query: run.query,
        criteria_hash: run.criteria?.hash,
        company: prospect.company,
        domain: prospect.domain,
        tier: prospect.tier,
        total_score: prospect.company_score,
        source_type: "prospect",
        page_category: "persona",
        evidence_id: "prospect",
        persona_titles: [prospect.persona],
        outreach_angle: prospect.outreach_angle,
      },
    });
  }
  return documents;
}

function buildUploadDocuments(run) {
  return buildDocuments(run)
    .filter((document) => String(document.text || "").trim())
    .map((document) => {
      const metadata = document.metadata || {};
      const sourceUri = String(metadata.source_url || `inline://knowledge2-icp/${document.id}`);
      return {
        source_uri: `${sourceUri.startsWith("http") || sourceUri.startsWith("inline://") ? sourceUri : `inline://knowledge2-icp/${sourceUri}`}#k2-icp-${metadata.evidence_id || document.id}`,
        raw_text: String(document.text || ""),
        metadata,
      };
    });
}

async function uploadToK2(env, run, { projectName, corpusName }) {
  if (!env.K2_API_KEY) {
    return {
      status: "error",
      reason: "K2_API_KEY is required when apply=true.",
      document_count: buildUploadDocuments(run).length,
    };
  }
  const baseUrl = (env.K2_BASE_URL || "https://api.knowledge2.ai").replace(/\/+$/, "");
  try {
    const project = await ensureK2Project(baseUrl, env.K2_API_KEY, projectName);
    const projectId = String(project.id || project.project_id || project.projectId || "");
    const corpus = await ensureK2Corpus(baseUrl, env.K2_API_KEY, projectId, corpusName);
    const corpusId = String(corpus.id || corpus.corpus_id || corpus.corpusId || "");
    const documents = buildUploadDocuments(run);
    const upload = await k2Request(baseUrl, env.K2_API_KEY, "POST", `/v1/corpora/${encodeURIComponent(corpusId)}/documents:batch`, {
      documents,
      auto_index: false,
      wait: false,
    }, { "idempotency-key": `knowledge2-icp-${run.id}` });
    return {
      status: "uploaded",
      project_id: projectId,
      project_name: project.name || projectName,
      corpus_id: corpusId,
      corpus_name: corpus.name || corpusName,
      document_count: documents.length,
      upload,
    };
  } catch (error) {
    return {
      status: "error",
      reason: error instanceof Error ? error.message : String(error),
      document_count: buildUploadDocuments(run).length,
    };
  }
}

async function ensureK2Project(baseUrl, apiKey, name) {
  const payload = await k2Request(baseUrl, apiKey, "GET", "/v1/projects?limit=100&offset=0");
  const existing = (payload.projects || []).find((project) => project.name === name);
  if (existing) return existing;
  return k2Request(baseUrl, apiKey, "POST", "/v1/projects", { name });
}

async function ensureK2Corpus(baseUrl, apiKey, projectId, name) {
  const payload = await k2Request(baseUrl, apiKey, "GET", `/v1/corpora?project_id=${encodeURIComponent(projectId)}&limit=100&offset=0`);
  const existing = (payload.corpora || []).find((corpus) => corpus.name === name);
  if (existing) return existing;
  return k2Request(baseUrl, apiKey, "POST", "/v1/corpora", {
    project_id: projectId,
    name,
    description: "Agentic GTM lead research evidence and metadata.",
  });
}

async function k2Request(baseUrl, apiKey, method, path, body, extraHeaders = {}) {
  const response = await fetch(`${baseUrl}${path}`, {
    method,
    headers: {
      accept: "application/json",
      "content-type": "application/json",
      "user-agent": "Knowledge2ICPWorker/0.1",
      "x-api-key": apiKey,
      ...extraHeaders,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await response.text();
  let payload = {};
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { raw: text.slice(0, 1000) };
    }
  }
  if (!response.ok) {
    throw new Error(`K2 API returned HTTP ${response.status}: ${JSON.stringify(payload).slice(0, 600)}`);
  }
  return payload;
}

function authorizeApiRequest(request, env) {
  const expected = String(env.ICP_ADMIN_TOKEN || "").trim();
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

async function readJson(request) {
  try {
    const payload = await request.json();
    return payload && typeof payload === "object" && !Array.isArray(payload) ? payload : {};
  } catch {
    return {};
  }
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

function unauthorized(message = "Token required.") {
  return json({ error: message }, 401, {
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

function normalizeDomain(value) {
  return String(value || "")
    .trim()
    .replace(/^https?:\/\//i, "")
    .replace(/^www\./i, "")
    .split("/")[0]
    .toLowerCase();
}

function companyDomainFromUrl(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  try {
    const parsed = new URL(raw.includes("://") ? raw : `https://${raw}`);
    return normalizeDomain(parsed.hostname);
  } catch {
    return normalizeDomain(raw);
  }
}

function isBlockedDiscoveryDomain(domain) {
  const clean = normalizeDomain(domain);
  if (!clean || !clean.includes(".")) return true;
  return [...BLOCKED_DISCOVERY_HOSTS].some((host) => clean === host || clean.endsWith(`.${host}`));
}

function companyNameFromTitleOrDomain(title, domain) {
  const cleanTitle = String(title || "").split(/[-|:]/, 1)[0].replace(/\b(official site|homepage|software|platform)\b/gi, "").trim();
  if (cleanTitle && cleanTitle.length <= 80) return cleanTitle;
  return titleCase(normalizeDomain(domain).split(".", 1)[0].replace(/[-_]+/g, " "));
}

function queryTerms(query) {
  return String(query || "")
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((term) => term.length >= 4 && !DISCOVERY_QUERY_STOPWORDS.has(term));
}

function terms(value) {
  return new Set(
    String(value || "")
      .toLowerCase()
      .split(/[^a-z0-9]+/)
      .filter((term) => term.length > 1 && !["of", "and", "the"].includes(term)),
  );
}

function slug(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || "item";
}

function titleCase(value) {
  return String(value || "")
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part.slice(0, 1).toUpperCase() + part.slice(1))
    .join(" ");
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}
