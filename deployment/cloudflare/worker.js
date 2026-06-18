const SEED_CREATED_AT = "2026-06-12T00:00:00+00:00";
const SEED_RUN_ID = "run-seeded-icp";
// A user run needs at least this many leads before the dashboard lands on it
// instead of the seeded showcase. Mirrors icp_engine.app_store._core.
const SUBSTANTIVE_RUN_LEADS = 3;
// Explicit horizontal-audience language. Live candidates that pitch "any
// business / all industries" get their workflow-moat capped, mirroring
// scoring.HORIZONTAL_AUDIENCE_KEYWORDS in the Python engine.
const HORIZONTAL_AUDIENCE_KEYWORDS = [
  "for businesses",
  "any business",
  "all businesses",
  "businesses of all sizes",
  "any industry",
  "all industries",
  "across industries",
  "every industry",
  "any team",
  "every team",
  "any company",
  "any organization",
  "organizations of all",
  "teams of all sizes",
  "companies of all sizes",
  "for everyone",
];
const MAX_APOLLO_ENRICH_LEADS = 12;
const K2_WORKSPACE_PROJECT_DEFAULT = "Knowledge2 ICP GTM Dev";
const K2_WORKSPACE_PIPELINE_NAME = "ICP Expansion Pipeline";
const K2_WORKSPACE_CORPORA = [
  { key: "source", name: "ICP Source Corpus", description: "Portfolio pages, source lists, SERP results, company pages, and provider payload summaries." },
  { key: "candidate", name: "ICP Candidate Corpus", description: "Normalized account records for K2-fit ICP candidates." },
  { key: "evidence", name: "ICP Evidence Corpus", description: "Scoring evidence, score components, hard gates, rationale, and citations." },
  { key: "prospect", name: "ICP Prospect Corpus", description: "Persona targets, Apollo people, contact confidence, and outreach readiness records." },
  { key: "criteria", name: "ICP Criteria Corpus", description: "Criteria markdown, prompt versions, settings, lists, accepted/rejected examples, and query profile hints." },
];
const K2_WORKSPACE_AGENTS = [
  { key: "source_discovery", name: "ICP Source Discovery Agent", description: "Extract normalized company/domain candidates from source pages and list payloads." },
  { key: "qualification", name: "ICP Company Qualification Agent", description: "Score candidate accounts against the K2 incumbent-software ICP." },
  { key: "evidence_gap", name: "ICP Evidence Gap Agent", description: "Find missing source coverage and recommend the next scrape/search/enrichment action." },
  { key: "prospect_role", name: "ICP Prospect Role Agent", description: "Normalize prospect/persona records into a role tree with outreach readiness." },
  { key: "criteria_refinement", name: "ICP Criteria Refinement Agent", description: "Review accepted/rejected/exported outcomes and propose criteria/query-profile updates." },
  { key: "outreach", name: "ICP Outreach Draft Agent", description: "Draft evidence-backed outreach variants for approved prospects." },
];
const K2_WORKSPACE_FEEDS = [
  { key: "source_to_candidate", name: "ICP Source-to-Candidate Feed", description: "Reactive extraction of normalized candidate accounts when new source documents land." },
  { key: "daily_source_sweep", name: "ICP Daily Source Sweep Feed", description: "Daily source-corpus sweep to keep the candidate corpus growing from existing source material." },
  { key: "candidate_to_evidence", name: "ICP Candidate Qualification Feed", description: "Reactive qualification of candidate accounts into scored evidence records." },
  { key: "prospect_expansion", name: "ICP Prospect Expansion Feed", description: "Reactive normalization of prospect records and fallback personas into a role tree." },
];
const STATE_COLLECTIONS = [
  { key: "criteria", type: "object" },
  { key: "criteria_versions", type: "array" },
  { key: "settings", type: "object" },
  { key: "sources", type: "array" },
  { key: "source_scans", type: "array" },
  { key: "expansion_runs", type: "array" },
  { key: "provider_usage", type: "array" },
  { key: "runs", type: "array" },
  { key: "lead_states", type: "object" },
  { key: "lead_views", type: "array" },
  { key: "quality_feedback", type: "array" },
  { key: "outreach_statuses", type: "object" },
  { key: "eval_cases", type: "array" },
  { key: "eval_runs", type: "array" },
];
const API_SESSION_TTL_SECONDS = 8 * 60 * 60;
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
  provider_limits: {
    enabled: true,
    daily: {
      search: 200,
      source_scan: 100,
      run: 80,
      apollo_enrichment: 100,
      research: 300,
      k2_apply: 10,
      k2_dry_run: 100,
    },
    rate_per_minute: {
      search: 30,
      source_scan: 20,
      run: 10,
      apollo_enrichment: 20,
      research: 60,
      k2_apply: 5,
      k2_dry_run: 20,
    },
    per_run: {
      max_companies: 100,
      max_pages: 20,
    },
  },
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
  criteriaVersions: [],
  runs: new Map(),
  seedLists: null,
  settings: null,
  leadStates: new Map(),
  leadViews: [],
  sources: null,
  sourceScans: [],
  expansionRuns: [],
  providerUsage: [],
  qualityFeedback: [],
  outreachStatuses: {},
  evalCases: null,
  evalRuns: [],
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
  async scheduled(event, env) {
    const lists = await seedLists(env);
    await runExpansion(env, lists, {
      trigger: event?.cron ? `cron:${event.cron}` : "scheduled",
      dueOnly: true,
      maxCompanies: 25,
    });
  },
};

async function handleApiRequest(request, env, url) {
  const method = request.method.toUpperCase();
  if (method === "POST" && url.pathname === "/api/auth/session") {
    return createApiSessionResponse(request, env);
  }
  const auth = await authorizeApiRequest(request, env);
  if (method === "GET" && url.pathname === "/api/health") {
    const lists = await seedLists(env);
    return json({
      status: "ok",
      service: "knowledge2-icp",
      version: "0.1.0-worker",
      auth_required: auth.configured,
      authenticated: auth.authorized,
      public_read_only: true,
      protected_actions: ["mutations", "provider_runs", "exports", "admin_diagnostics", "k2_apply_sync"],
      mode: "seeded-worker",
      run_count: (await listRuns(env, lists)).length,
      provider_status: providerStatus(env),
      provider_controls: await providerControls(env),
    });
  }
  const publicRead = isPublicReadRequest(method, url);
  if (!auth.configured && !publicRead) {
    return json({ error: "ICP_ADMIN_TOKEN is required for API access." }, 503);
  }
  if (!auth.authorized && !publicRead) {
    return unauthorized("API token required.");
  }

  const lists = await seedLists(env);

  if (method === "GET" && url.pathname === "/api/state") {
    return json(await currentState(env, lists));
  }

  if (method === "GET" && url.pathname === "/api/workspace-state") {
    return json(await workspaceStateStatus(env));
  }

  if (method === "GET" && url.pathname === "/api/settings") {
    return json({ settings: await loadSettings(env) });
  }

  if (method === "POST" && url.pathname === "/api/settings") {
    const payload = await readJson(request);
    try {
      const settings = await saveSettings(env, payload);
      return json({ settings, provider_controls: await providerControls(env) });
    } catch (error) {
      return json({ error: error.message || String(error) }, 400);
    }
  }

  if (method === "GET" && url.pathname === "/api/lead-views") {
    return json({ views: await loadLeadViews(env) });
  }

  if (method === "POST" && url.pathname === "/api/lead-views") {
    const payload = await readJson(request);
    try {
      const view = await saveLeadView(env, payload);
      return json({ view, views: await loadLeadViews(env) });
    } catch (error) {
      return json({ error: error.message || String(error) }, 400);
    }
  }

  if (method === "GET" && url.pathname === "/api/evals/cases") {
    return json({ cases: await loadEvalCases(env, null) });
  }

  if (method === "POST" && url.pathname === "/api/evals/cases") {
    const payload = await readJson(request);
    try {
      const saved = await saveEvalCase(env, payload);
      return json({ case: saved, cases: await loadEvalCases(env, null) });
    } catch (error) {
      return json({ error: error.message || String(error) }, 400);
    }
  }

  if (method === "GET" && url.pathname === "/api/evals/runs.csv") {
    return new Response(evalRunsCsv(await listEvalRuns(env)), {
      headers: {
        "content-type": "text/csv; charset=utf-8",
        "cache-control": "no-store",
        "content-disposition": 'attachment; filename="icp-eval-runs.csv"',
      },
    });
  }

  if (method === "GET" && url.pathname === "/api/evals/runs") {
    const runs = await listEvalRuns(env);
    return json({ runs, summary: evalSummary(runs) });
  }

  if (method === "POST" && url.pathname === "/api/evals/runs") {
    const payload = await readJson(request);
    const run = await loadRun(env, String(payload.run_id || ""), lists);
    if (!run) return json({ error: "Run not found." }, 400);
    const result = await runIcpEval(env, run, lists, Array.isArray(payload.case_ids) ? payload.case_ids.map(String) : []);
    const runs = await appendEvalRun(env, result);
    return json({ eval_run: result, summary: evalSummary(runs.filter((item) => item.run_id === run.id)) });
  }

  if (method === "GET" && url.pathname === "/api/evals/summary") {
    return json(evalSummary(await listEvalRuns(env)));
  }

  if (method === "GET" && url.pathname === "/api/k2-workspace") {
    return json(await k2WorkspaceStatus(env));
  }

  if (method === "POST" && url.pathname === "/api/k2-workspace/pipeline") {
    return k2WorkspacePipelineAction(env, await readJson(request));
  }

  if (method === "GET" && url.pathname === "/api/sources") {
    return json({
      sources: await loadSources(env, lists),
      scans: (await loadSourceScans(env)).slice(-50),
      expansion_runs: (await loadExpansionRuns(env)).slice(-25),
      coverage: await sourceCoverage(env, lists),
    });
  }

  if (method === "GET" && url.pathname === "/api/expansion/runs") {
    return json({ runs: await loadExpansionRuns(env), coverage: await sourceCoverage(env, lists) });
  }

  if (method === "GET" && url.pathname === "/api/criteria/versions") {
    const criteria = await currentCriteria(env);
    return json({ versions: await criteriaVersions(env), current_hash: criteria.hash });
  }

  if (method === "POST" && url.pathname === "/api/criteria") {
    const payload = await readJson(request);
    const markdown = String(payload.markdown || "");
    if (!markdown.trim()) return json({ error: "Criteria markdown is required." }, 400);
    await rememberCriteriaVersion(env, await currentCriteria(env));
    runtime.criteria = criteriaPayload(formatCriteriaMarkdown(markdown), "worker-runtime", nowIso());
    await persistCriteria(env, runtime.criteria);
    await rememberCriteriaVersion(env, runtime.criteria);
    return json({ criteria: runtime.criteria, versions: await criteriaVersions(env), lint: lintCriteriaMarkdown(runtime.criteria.markdown) });
  }

  if (method === "POST" && url.pathname === "/api/criteria/lint") {
    const payload = await readJson(request);
    return json(lintCriteriaMarkdown(String(payload.markdown || "")));
  }

  if (method === "POST" && url.pathname === "/api/criteria/impact") {
    const payload = await readJson(request);
    const run = await loadRun(env, String(payload.run_id || ""), lists);
    if (!run) return json({ error: "Run not found." }, 400);
    try {
      return json(criteriaImpact(run, String(payload.markdown || ""), lists));
    } catch (error) {
      return json({ error: error.message || String(error) }, 400);
    }
  }

  if (method === "POST" && url.pathname === "/api/criteria/restore") {
    const payload = await readJson(request);
    const id = String(payload.id || payload.hash || "");
    const selected = (await criteriaVersions(env)).find((item) => item.id === id || item.hash === id);
    if (!selected) return json({ error: "Criteria version not found." }, 404);
    runtime.criteria = criteriaPayload(selected.markdown, "worker-runtime", nowIso());
    await persistCriteria(env, runtime.criteria);
    await rememberCriteriaVersion(env, runtime.criteria);
    return json({ criteria: runtime.criteria, versions: await criteriaVersions(env), lint: lintCriteriaMarkdown(runtime.criteria.markdown) });
  }

  if (method === "POST" && url.pathname === "/api/sources") {
    const payload = await readJson(request);
    try {
      const source = await saveSource(env, payload, lists);
      return json({ source, sources: await loadSources(env, lists), coverage: await sourceCoverage(env, lists) });
    } catch (error) {
      return json({ error: error.message || String(error) }, 400);
    }
  }

  if (method === "POST" && url.pathname === "/api/expansion/run") {
    const payload = await readJson(request);
    const result = await runExpansion(env, lists, {
      trigger: Boolean(payload.due_only ?? true) ? "manual_due" : "manual_all_scheduled",
      dueOnly: Boolean(payload.due_only ?? true),
      maxCompanies: Number(payload.max_companies || 25),
    });
    return json({
      run: result,
      sources: await loadSources(env, lists),
      scans: (await loadSourceScans(env)).slice(-50),
      expansion_runs: (await loadExpansionRuns(env)).slice(-25),
      coverage: await sourceCoverage(env, lists),
    });
  }

  const sourceScanMatch = url.pathname.match(/^\/api\/sources\/([^/]+)\/scan$/);
  if (method === "POST" && sourceScanMatch) {
    const payload = await readJson(request);
    const sourceId = decodeURIComponent(sourceScanMatch[1]);
    const source = (await loadSources(env, lists)).find((item) => item.id === sourceId);
    if (!source) return json({ error: "Source not found." }, 404);
    const maxCompanies = Number(payload.max_companies || 25);
    const guard = await authorizeProviderAction(env, "source_scan", {
      details: {
        source_id: sourceId,
        source_type: source.type,
        max_companies: maxCompanies,
      },
    });
    if (!guard.allowed) return providerDenied(guard);
    const result = await scanSource(source, maxCompanies, lists, env);
    const scan = await recordSourceScan(env, source, result.candidates, result.warnings, result.status, lists);
    return json({ source: (await loadSources(env, lists)).find((item) => item.id === sourceId) || source, scan, candidates: result.candidates, warnings: result.warnings, coverage: await sourceCoverage(env, lists) });
  }

  if (method === "POST" && url.pathname === "/api/search") {
    const payload = await readJson(request);
    const guard = await authorizeProviderAction(env, "search", {
      details: { max_companies: Number(payload.max_companies || 10) },
    });
    if (!guard.allowed) return providerDenied(guard);
    const result = await discoverCandidates(payload, lists, env);
    return json(result);
  }

  if (method === "POST" && url.pathname === "/api/runs") {
    const payload = await readJson(request);
    const maxCompanies = Number(payload.max_companies || 8);
    const maxPages = Number(payload.max_pages || 8);
    let guard = await authorizeProviderAction(env, "run", {
      details: {
        max_companies: maxCompanies,
        max_pages: maxPages,
        use_apollo: Boolean(payload.use_apollo),
      },
    });
    if (!guard.allowed) return providerDenied(guard);
    if (!Array.isArray(payload.candidates) && String(payload.query || "").trim()) {
      guard = await authorizeProviderAction(env, "search", {
        details: { max_companies: maxCompanies, source: "run" },
      });
      if (!guard.allowed) return providerDenied(guard);
    }
    if (Boolean(payload.use_apollo)) {
      guard = await authorizeProviderAction(env, "apollo_enrichment", {
        amount: maxCompanies,
        details: { max_companies: maxCompanies },
      });
      if (!guard.allowed) return providerDenied(guard);
    }
    const run = await createRuntimeRun(payload, lists, env);
    await saveRun(env, run);
    return json(run);
  }

  if (method === "POST" && url.pathname === "/api/research") {
    const payload = await readJson(request);
    const guard = await authorizeProviderAction(env, "research", {
      details: { run_id: String(payload.run_id || "") },
    });
    if (!guard.allowed) return providerDenied(guard);
    const run = await loadRun(env, String(payload.run_id || ""), lists);
    if (!run) return json({ answer: "Run not found.", citations: [], matched_leads: [] }, 404);
    return json(await researchAnswer(env, run, String(payload.question || "")));
  }

  const accountMatch = url.pathname.match(/^\/api\/runs\/([^/]+)\/accounts\/([^/]+)$/);
  if (method === "GET" && accountMatch) {
    const run = await loadRun(env, accountMatch[1], lists);
    if (!run) return json({ error: "Run not found." }, 404);
    const detail = await accountDetail(run, decodeURIComponent(accountMatch[2]), env);
    if (!detail) return json({ error: "Account not found." }, 404);
    return json(detail);
  }

  const outreachStatusMatch = url.pathname.match(/^\/api\/runs\/([^/]+)\/outreach-drafts\/status$/);
  if (method === "POST" && outreachStatusMatch) {
    const run = await loadRun(env, outreachStatusMatch[1], lists);
    if (!run) return json({ error: "Run not found." }, 404);
    const payload = await readJson(request);
    let record;
    try {
      record = await saveOutreachStatus(env, run.id, payload);
    } catch (error) {
      return json({ error: error.message || String(error) }, 400);
    }
    const accountDrafts = await listOutreachDrafts(env, run, { domain: record.domain });
    return json({
      outreach_status: record,
      summary: outreachSummary(await listOutreachDrafts(env, run)),
      account_summary: outreachSummary(accountDrafts),
    });
  }

  const bulkLeadStateMatch = url.pathname.match(/^\/api\/runs\/([^/]+)\/lead-state\/bulk$/);
  if (method === "POST" && bulkLeadStateMatch) {
    const run = await loadRun(env, bulkLeadStateMatch[1], lists);
    if (!run) return json({ error: "Run not found." }, 404);
    const payload = await readJson(request);
    try {
      return json(await bulkUpdateLeadStates(env, run, payload));
    } catch (error) {
      return json({ error: error.message || String(error) }, 400);
    }
  }

  const runMatch = url.pathname.match(/^\/api\/runs\/([^/]+)(?:\/([^/]+))?$/);
  if (runMatch) {
    const run = await loadRun(env, runMatch[1], lists);
    if (!run) return json({ error: "Run not found." }, 404);
    const action = runMatch[2] || "";
    if (method === "GET" && !action) return json(run);
    if (method === "GET" && action === "workflow") {
      return json({
        run_id: run.id,
        lead_statuses: run.workflow?.lead_statuses || [],
        status_counts: run.workflow?.status_counts || {},
        lead_states: Array.from((await loadLeadStates(env, run.id)).values()),
        saved_views: await loadLeadViews(env),
      });
    }
    if (method === "POST" && action === "lead-state") {
      const payload = await readJson(request);
      let record;
      try {
        record = await saveLeadState(env, run.id, payload);
      } catch (error) {
        return json({ error: error.message || String(error) }, 400);
      }
      const hydrated = await attachWorkflow(env, run);
      return json({ lead_state: record, status_counts: leadStatusCounts(hydrated) });
    }
    if (method === "GET" && action === "quality-feedback") {
      return json({
        run_id: run.id,
        feedback: await listQualityFeedback(env, { runId: run.id, limit: 200 }),
        summary: await qualityFeedbackSummary(env, { runId: run.id }),
      });
    }
    if (method === "GET" && action === "quality-feedback.csv") {
      return new Response(await qualityFeedbackCsv(env, { runId: run.id }), {
        headers: {
          "content-type": "text/csv; charset=utf-8",
          "cache-control": "no-store",
          "content-disposition": `attachment; filename="${run.id}-quality-feedback.csv"`,
        },
      });
    }
    if (method === "POST" && action === "quality-feedback") {
      const payload = await readJson(request);
      let record;
      try {
        record = await saveQualityFeedback(env, run.id, payload);
      } catch (error) {
        return json({ error: error.message || String(error) }, 400);
      }
      return json({
        feedback: record,
        summary: await qualityFeedbackSummary(env, { runId: run.id }),
        account_summary: await qualityFeedbackSummary(env, { runId: run.id, domain: record.domain }),
      });
    }
    if (method === "GET" && action === "outreach-drafts") {
      const drafts = await listOutreachDrafts(env, run);
      return json({ run_id: run.id, drafts, summary: outreachSummary(drafts) });
    }
    if (method === "GET" && action === "outreach-drafts.csv") {
      return new Response(outreachDraftsCsv(await listOutreachDrafts(env, run)), {
        headers: {
          "content-type": "text/csv; charset=utf-8",
          "cache-control": "no-store",
          "content-disposition": `attachment; filename="${run.id}-outreach-drafts.csv"`,
        },
      });
    }
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
        const guard = await authorizeProviderAction(env, "k2_dry_run", {
          details: { run_id: run.id, apply },
        });
        if (!guard.allowed) return providerDenied(guard);
        return json({
          status: "dry_run",
          project_name: String(payload.project_name || "Knowledge2 ICP GTM"),
          corpus_name: String(payload.corpus_name || `ICP Run ${run.id}`),
          document_count: buildUploadDocuments(run).length,
          k2_configured: Boolean(env.K2_API_KEY),
          mode: "cloudflare-worker",
        });
      }
      const auth = await authorizeApiRequest(request, env);
      if (!auth.configured) {
        return json({ error: "ICP_ADMIN_TOKEN is required for K2 apply sync." }, 503);
      }
      if (!auth.authorized) {
        return unauthorized("K2 apply token required.");
      }
      const guard = await authorizeProviderAction(env, "k2_apply", {
        details: { run_id: run.id, apply },
      });
      if (!guard.allowed) return providerDenied(guard);
      const result = await uploadToK2(env, run, {
        projectName: String(payload.project_name || "Knowledge2 ICP GTM"),
        corpusName: String(payload.corpus_name || `ICP Run ${run.id}`),
      });
      if (result.status === "uploaded") {
        run.k2 = result;
        await saveRun(env, run);
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

async function currentState(env, lists) {
  const runs = await listRuns(env, lists);
  for (const run of runs) {
    run.quality_feedback_counts = (await qualityFeedbackSummary(env, { runId: run.id })).rating_counts;
    const hydrated = await loadRun(env, run.id, lists);
    run.outreach_counts = hydrated ? outreachSummary(await listOutreachDrafts(env, hydrated)).status_counts : {};
    run.eval_status = evalSummary(await listEvalRuns(env, { runId: run.id })).latest_status;
  }
  const criteria = await currentCriteria(env);
  return {
    criteria,
    criteria_versions: await criteriaVersions(env),
    prompts: clone(SEED_PROMPTS),
    settings: await loadSettings(env),
    lists: clone(lists),
    runs,
    lead_views: await loadLeadViews(env),
    sources: await loadSources(env, lists),
    source_scans: (await loadSourceScans(env)).slice(-25),
    expansion_runs: (await loadExpansionRuns(env)).slice(-25),
    source_coverage: await sourceCoverage(env, lists),
    provider_controls: await providerControls(env),
    quality_feedback_summary: await qualityFeedbackSummary(env),
    outreach_summary: await workspaceOutreachSummary(env, lists),
    eval_summary: evalSummary(await listEvalRuns(env)),
    provider_status: providerStatus(env),
    workspace_state: await workspaceStateStatus(env),
    latest_run: await loadRun(env, defaultLandingRunId(runs), lists),
  };
}

async function loadSources(env, lists) {
  if (env?.ICP_STATE?.get) {
    const stored = await getStateJson(env, "sources", null);
    if (Array.isArray(stored)) {
      runtime.sources = stored.map((item) => sourceRecord(item));
      return runtime.sources;
    }
  }
  if (!runtime.sources) runtime.sources = defaultSources(lists);
  return runtime.sources;
}

function defaultSources(lists) {
  const accountCount = Array.isArray(lists.account_universe) ? lists.account_universe.length : 0;
  const discoveryPrompt = SEED_PROMPTS.find((item) => item.id === "discovery-query")?.text || "vertical market software portfolio companies with workflow data";
  return [
    sourceRecord({
      id: "seed-constellation-portfolio",
      name: "Constellation/Volaris/Harris account universe",
      type: "manual_seed",
      value: `${accountCount} committed portfolio and ICP accounts from local seed data`,
      source_group: "seeded-portfolio",
      schedule: "manual",
      last_status: "seeded",
      last_candidate_count: accountCount,
    }),
    sourceRecord({
      id: "seed-portfolio-expansion-serp",
      name: "Portfolio expansion SERP",
      type: "serp_query",
      value: discoveryPrompt,
      source_group: "portfolio-expansion",
      schedule: "weekly",
    }),
    sourceRecord({
      id: "seed-ai-gap-serp",
      name: "AI gap audit SERP",
      type: "serp_query",
      value: "pre-2025 vertical SaaS workflow software weak AI positioning API integrations",
      source_group: "ai-gap-audit",
      schedule: "weekly",
    }),
  ];
}

function sourceRecord(input) {
  const now = input.updated_at || "2026-06-13T00:00:00+00:00";
  const type = normalizeSourceType(input.type || "serp_query");
  const id = input.id || criteriaHash(`${type}:${input.name}:${input.value}`).slice(0, 16);
  return {
    id,
    name: String(input.name || "Source").trim(),
    type,
    value: String(input.value || "").trim(),
    source_group: String(input.source_group || sourceGroupForType(type)).trim(),
    schedule: normalizeSourceSchedule(String(input.schedule || "manual")),
    enabled: input.enabled !== false,
    created_at: input.created_at || now,
    updated_at: now,
    last_scan_at: input.last_scan_at || "",
    last_status: input.last_status || "never_scanned",
    last_candidate_count: Number(input.last_candidate_count || 0),
    last_warning_count: Number(input.last_warning_count || 0),
  };
}

async function saveSource(env, payload, lists) {
  const source = sourceRecord({
    id: payload.id ? String(payload.id) : "",
    name: String(payload.name || ""),
    type: String(payload.type || "serp_query"),
    value: String(payload.value || ""),
    source_group: String(payload.source_group || ""),
    schedule: String(payload.schedule || "manual"),
    enabled: payload.enabled !== false,
    updated_at: nowIso(),
  });
  if (!source.name) throw new Error("Source name is required.");
  if (!source.value) throw new Error("Source value is required.");
  const sources = (await loadSources(env, lists)).filter((item) => item.id !== source.id);
  sources.push(source);
  runtime.sources = sources.sort((left, right) => String(left.name).localeCompare(String(right.name)));
  await putStateJson(env, "sources", runtime.sources);
  return source;
}

async function scanSource(source, maxCompanies, lists, env) {
  let result;
  if (source.type === "manual_seed" || source.type === "csv_upload") {
    const candidates = parseSeedText(source.value).slice(0, maxCompanies);
    const sourceLabel = source.type === "csv_upload" ? "CSV source text" : "manual seed text";
    result = { candidates, warnings: candidates.length ? [] : [`No company domains were discovered from ${sourceLabel}.`] };
  } else {
    result = await discoverCandidates({ query: source.value, max_companies: maxCompanies }, lists, env);
    if (source.type === "portfolio_url") {
      result.warnings = [`Portfolio URL scanning uses configured search providers on Worker for ${source.value}.`, ...(result.warnings || [])];
    }
  }
  return {
    status: result.candidates?.length ? "completed" : "empty",
    candidates: result.candidates || [],
    warnings: result.warnings || [],
  };
}

async function recordSourceScan(env, source, candidates, warnings, status, lists) {
  const now = nowIso();
  const scan = {
    id: criteriaHash(`${now}:${source.id}:${candidates.length}:${warnings.length}`).slice(0, 16),
    source_id: source.id,
    source_name: source.name,
    source_type: source.type,
    source_group: source.source_group,
    status,
    scanned_at: now,
    candidate_count: candidates.length,
    warning_count: warnings.length,
    warnings: warnings.slice(0, 20),
    candidates: candidates.slice(0, 100),
  };
  runtime.sourceScans = await loadSourceScans(env);
  runtime.sourceScans.push(scan);
  runtime.sourceScans = runtime.sourceScans.slice(-500);
  runtime.sources = (await loadSources(env, lists)).map((item) => item.id === source.id
    ? { ...item, last_scan_at: now, last_status: status, last_candidate_count: candidates.length, last_warning_count: warnings.length, updated_at: now }
    : item);
  await putStateJson(env, "source_scans", runtime.sourceScans);
  await putStateJson(env, "sources", runtime.sources);
  return scan;
}

async function loadSourceScans(env) {
  if (env?.ICP_STATE?.get) {
    const stored = await getStateJson(env, "source_scans", null);
    if (Array.isArray(stored)) {
      runtime.sourceScans = stored.filter((item) => item && typeof item === "object");
      return runtime.sourceScans;
    }
  }
  return runtime.sourceScans;
}

async function loadExpansionRuns(env) {
  if (env?.ICP_STATE?.get) {
    const stored = await getStateJson(env, "expansion_runs", null);
    if (Array.isArray(stored)) {
      runtime.expansionRuns = stored.filter((item) => item && typeof item === "object");
      return runtime.expansionRuns;
    }
  }
  return runtime.expansionRuns;
}

async function runExpansion(env, lists, { trigger = "manual_due", dueOnly = true, maxCompanies = 25 } = {}) {
  const boundedMaxCompanies = Math.max(1, Math.min(Number(maxCompanies) || 25, 100));
  const sources = dueOnly
    ? await expansionSourcesDue(env, lists)
    : (await loadSources(env, lists)).filter((source) => source.enabled && source.schedule !== "manual");
  const sourceResults = [];
  for (const source of sources) {
    const guard = await authorizeProviderAction(env, "source_scan", {
      details: {
        source_id: source.id,
        source_type: source.type,
        max_companies: boundedMaxCompanies,
        trigger: "expansion",
      },
    });
    if (!guard.allowed) {
      sourceResults.push({
        source_id: source.id,
        source_name: source.name,
        status: "skipped",
        candidate_count: 0,
        warning_count: 1,
        reason: guard.reason || "Provider budget denied.",
      });
      continue;
    }
    try {
      const result = await scanSource(source, boundedMaxCompanies, lists, env);
      const scan = await recordSourceScan(env, source, result.candidates || [], result.warnings || [], result.status, lists);
      sourceResults.push({
        source_id: source.id,
        source_name: source.name,
        status: scan.status,
        scan_id: scan.id,
        candidate_count: scan.candidate_count,
        warning_count: scan.warning_count,
      });
    } catch (error) {
      sourceResults.push({
        source_id: source.id,
        source_name: source.name,
        status: "failed",
        candidate_count: 0,
        warning_count: 1,
        reason: error.message || String(error),
      });
    }
  }
  const status = sourceResults.length
    ? sourceResults.some((item) => item.status === "failed") ? "failed" : "completed"
    : "empty";
  return recordExpansionRun(env, { trigger, status, sourceResults });
}

async function expansionSourcesDue(env, lists) {
  const sources = await loadSources(env, lists);
  const now = Date.now();
  return sources.filter((source) => source.enabled && source.schedule !== "manual" && sourceScheduleDue(source, now));
}

function sourceScheduleDue(source, nowMs) {
  const schedule = String(source.schedule || "manual");
  if (schedule === "manual") return false;
  const lastScan = Date.parse(String(source.last_scan_at || ""));
  if (Number.isNaN(lastScan)) return true;
  const intervals = {
    daily: 24 * 60 * 60 * 1000,
    weekly: 7 * 24 * 60 * 60 * 1000,
    monthly: 30 * 24 * 60 * 60 * 1000,
  };
  if (schedule.startsWith("cron:")) return false;
  const interval = intervals[schedule] || 0;
  return Boolean(interval && nowMs - lastScan >= interval);
}

async function recordExpansionRun(env, { trigger, status, sourceResults, warnings = [] }) {
  const now = nowIso();
  const run = {
    id: criteriaHash(`${now}:${trigger}:${sourceResults.length}:${status}`).slice(0, 16),
    created_at: now,
    trigger,
    status,
    source_count: sourceResults.length,
    scanned_source_count: sourceResults.filter((item) => item.status !== "skipped").length,
    candidate_count: sourceResults.reduce((sum, item) => sum + Number(item.candidate_count || 0), 0),
    warning_count: sourceResults.reduce((sum, item) => sum + Number(item.warning_count || 0), 0) + warnings.length,
    source_results: sourceResults.slice(0, 100),
    warnings: warnings.slice(0, 50),
  };
  runtime.expansionRuns = await loadExpansionRuns(env);
  runtime.expansionRuns.push(run);
  runtime.expansionRuns = runtime.expansionRuns.slice(-500);
  await putStateJson(env, "expansion_runs", runtime.expansionRuns);
  return run;
}

async function sourceCoverage(env, lists) {
  const sources = await loadSources(env, lists);
  const scans = await loadSourceScans(env);
  const expansionRuns = await loadExpansionRuns(env);
  const domains = new Set();
  for (const scan of scans) {
    for (const candidate of scan.candidates || []) {
      if (candidate.domain) domains.add(candidate.domain);
    }
  }
  return {
    source_count: sources.length,
    enabled_count: sources.filter((item) => item.enabled).length,
    source_type_counts: countByKey(sources, "type"),
    source_group_counts: countByKey(sources, "source_group"),
    scan_count: scans.length,
    candidate_count: scans.reduce((sum, scan) => sum + Number(scan.candidate_count || 0), 0),
    unique_candidate_domains: domains.size,
    latest_scan: scans[scans.length - 1] || null,
    latest_expansion_run: expansionRuns[expansionRuns.length - 1] || null,
    due_source_count: (await expansionSourcesDue(env, lists)).length,
  };
}

async function loadSettings(env) {
  if (env?.ICP_STATE?.get) {
    const stored = await getStateJson(env, "settings", null);
    if (stored && typeof stored === "object" && !Array.isArray(stored)) {
      runtime.settings = mergeSettings(stored);
      return runtime.settings;
    }
  }
  if (!runtime.settings) runtime.settings = mergeSettings({});
  return runtime.settings;
}

async function saveSettings(env, payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("Settings payload must be an object.");
  }
  const current = await loadSettings(env);
  runtime.settings = normalizeSettingsPayload(payload, current);
  await putStateJson(env, "settings", runtime.settings);
  return runtime.settings;
}

function mergeSettings(overrides) {
  const settings = { ...clone(SEED_SETTINGS), ...(overrides && typeof overrides === "object" ? clone(overrides) : {}) };
  settings.provider_limits = mergeProviderLimits(settings.provider_limits);
  return settings;
}

function normalizeSettingsPayload(payload, current) {
  const nextSettings = mergeSettings(current || {});
  for (const key of ["default_query", "employee_range"]) {
    if (key in payload) nextSettings[key] = String(payload[key] || "").trim().replace(/\s+/g, " ");
  }
  for (const key of ["fetch_website_evidence", "include_github_metadata", "use_apollo_enrichment", "use_serp_discovery"]) {
    if (key in payload) nextSettings[key] = coerceBoolean(payload[key], Boolean(nextSettings[key]));
  }
  const intFields = {
    max_companies: [1, 1000],
    max_pages: [0, 100],
    tier_a_threshold: [0, 100],
    tier_b_threshold: [0, 100],
  };
  for (const [key, [minimum, maximum]] of Object.entries(intFields)) {
    if (key in payload) nextSettings[key] = boundedInteger(payload[key], Number(nextSettings[key] || minimum), minimum, maximum);
  }
  if (payload.provider_limits && typeof payload.provider_limits === "object" && !Array.isArray(payload.provider_limits)) {
    nextSettings.provider_limits = normalizeProviderLimits(payload.provider_limits, nextSettings.provider_limits);
  }
  return mergeSettings(nextSettings);
}

function mergeProviderLimits(overrides) {
  const base = clone(SEED_SETTINGS.provider_limits || {});
  if (!overrides || typeof overrides !== "object" || Array.isArray(overrides)) return base;
  for (const [key, value] of Object.entries(overrides)) {
    if (value && typeof value === "object" && !Array.isArray(value) && base[key] && typeof base[key] === "object") {
      base[key] = { ...base[key], ...value };
    } else {
      base[key] = value;
    }
  }
  return base;
}

function normalizeProviderLimits(payload, current) {
  const limits = mergeProviderLimits(current);
  if ("enabled" in payload) limits.enabled = coerceBoolean(payload.enabled, limits.enabled !== false);
  for (const group of ["daily", "rate_per_minute"]) {
    if (!payload[group] || typeof payload[group] !== "object" || Array.isArray(payload[group])) continue;
    const currentGroup = limits[group] && typeof limits[group] === "object" ? limits[group] : {};
    limits[group] = { ...currentGroup };
    for (const [key, value] of Object.entries(payload[group])) {
      limits[group][key] = boundedInteger(value, Number(currentGroup[key] || 0), 0, 100000);
    }
  }
  if (payload.per_run && typeof payload.per_run === "object" && !Array.isArray(payload.per_run)) {
    const currentPerRun = limits.per_run && typeof limits.per_run === "object" ? limits.per_run : {};
    limits.per_run = { ...currentPerRun };
    for (const [key, value] of Object.entries(payload.per_run)) {
      limits.per_run[key] = boundedInteger(value, Number(currentPerRun[key] || 0), 0, 10000);
    }
  }
  return mergeProviderLimits(limits);
}

function boundedInteger(value, fallback, minimum, maximum) {
  const number = Number(value);
  if (!Number.isFinite(number)) throw new Error(`Expected an integer between ${minimum} and ${maximum}.`);
  return Math.max(minimum, Math.min(Math.trunc(number), maximum));
}

function coerceBoolean(value, fallback) {
  if (typeof value === "boolean") return value;
  if (typeof value === "string") {
    const lowered = value.trim().toLowerCase();
    if (["true", "1", "yes", "on"].includes(lowered)) return true;
    if (["false", "0", "no", "off"].includes(lowered)) return false;
  }
  if (value === null || value === undefined) return Boolean(fallback);
  return Boolean(value);
}

function normalizeSourceType(value) {
  const type = String(value || "serp_query").trim().toLowerCase().replaceAll("-", "_").replaceAll(" ", "_");
  if (!["serp_query", "portfolio_url", "manual_seed", "csv_upload", "apollo_query"].includes(type)) throw new Error(`Invalid source type: ${value}.`);
  return type;
}

function sourceGroupForType(type) {
  return {
    serp_query: "saved-serp",
    portfolio_url: "portfolio-page",
    manual_seed: "manual-seed",
    csv_upload: "csv-upload",
    apollo_query: "apollo-search",
  }[type] || "source";
}

function normalizeSourceSchedule(value) {
  const schedule = String(value || "manual").trim().toLowerCase().replaceAll("_", "-");
  if (!["manual", "daily", "weekly", "monthly"].includes(schedule) && !schedule.startsWith("cron:")) throw new Error("Source schedule must be manual, daily, weekly, monthly, or cron:<utc expression>.");
  return schedule;
}

function countByKey(items, key) {
  return items.reduce((acc, item) => {
    const value = String(item[key] || "unknown");
    acc[value] = (acc[value] || 0) + 1;
    return acc;
  }, {});
}

async function providerControls(env) {
  const events = await loadProviderUsage(env);
  const settings = await loadSettings(env);
  const today = nowIso().slice(0, 10);
  const allowed = events.filter(
    (event) => event.created_at.startsWith(today) && event.status === "allowed",
  );
  const denied = events.filter(
    (event) => event.created_at.startsWith(today) && event.status === "denied",
  );
  return {
    policy: clone(settings.provider_limits || SEED_SETTINGS.provider_limits),
    today,
    allowed_counts: providerAmountsByAction(allowed),
    denied_counts: providerAmountsByAction(denied),
    recent_events: events.slice(-25),
  };
}

async function authorizeProviderAction(env, action, options = {}) {
  const cleanAction = normalizeProviderAction(action);
  const requestedAmount = Number(options.amount || 1);
  const amount = Number.isFinite(requestedAmount) ? Math.max(1, requestedAmount) : 1;
  const details = options.details && typeof options.details === "object" ? options.details : {};
  const settings = await loadSettings(env);
  const policy = settings.provider_limits || SEED_SETTINGS.provider_limits || {};
  if (!policy.enabled) {
    const event = await recordProviderUsage(
      env,
      cleanAction,
      "allowed",
      amount,
      "",
      { ...details, policy_disabled: true },
    );
    return { allowed: true, action: cleanAction, event, policy };
  }
  const denial = await providerActionDenial(env, cleanAction, amount, details, policy);
  if (denial) {
    const event = await recordProviderUsage(env, cleanAction, "denied", amount, denial.reason, details);
    return { allowed: false, action: cleanAction, event, policy, ...denial };
  }
  const event = await recordProviderUsage(env, cleanAction, "allowed", amount, "", details);
  return { allowed: true, action: cleanAction, event, policy };
}

async function providerActionDenial(env, action, amount, details, policy) {
  const events = await loadProviderUsage(env);
  const perRun = policy.per_run || {};
  const maxCompanies = Number(details.max_companies || 0);
  const maxPages = Number(details.max_pages || 0);
  if (maxCompanies && perRun.max_companies && maxCompanies > Number(perRun.max_companies)) {
    return {
      reason: `Requested max_companies=${maxCompanies} exceeds provider policy max_companies=${perRun.max_companies}.`,
      limit_type: "per_run",
      limit: Number(perRun.max_companies),
      usage: maxCompanies,
    };
  }
  if (maxPages && perRun.max_pages && maxPages > Number(perRun.max_pages)) {
    return {
      reason: `Requested max_pages=${maxPages} exceeds provider policy max_pages=${perRun.max_pages}.`,
      limit_type: "per_run",
      limit: Number(perRun.max_pages),
      usage: maxPages,
    };
  }
  const dailyLimit = Number((policy.daily || {})[action] || 0);
  if (dailyLimit) {
    const usage = providerActionAmount(
      events.filter(
        (event) =>
          event.status === "allowed" &&
          event.action === action &&
          event.created_at.startsWith(nowIso().slice(0, 10)),
      ),
    );
    if (usage + amount > dailyLimit) {
      return {
        reason: `Daily provider budget for ${action} is exhausted (${usage}/${dailyLimit}, requested ${amount}).`,
        limit_type: "daily",
        limit: dailyLimit,
        usage,
      };
    }
  }
  const rateLimit = Number((policy.rate_per_minute || {})[action] || 0);
  if (rateLimit) {
    const usage = providerActionAmount(
      events.filter(
        (event) =>
          event.status === "allowed" &&
          event.action === action &&
          eventWithinSeconds(event, 60),
      ),
    );
    if (usage + amount > rateLimit) {
      return {
        reason: `Rate limit for ${action} is exceeded (${usage}/${rateLimit} in the last minute, requested ${amount}).`,
        limit_type: "rate_per_minute",
        limit: rateLimit,
        usage,
      };
    }
  }
  return null;
}

async function recordProviderUsage(env, action, status, amount, reason, details) {
  const now = nowIso();
  const events = await loadProviderUsage(env);
  const event = {
    id: criteriaHash(`${now}:${action}:${status}:${events.length}`).slice(0, 16),
    created_at: now,
    action,
    status,
    amount,
    reason,
    details: details || {},
  };
  events.push(event);
  runtime.providerUsage = events.slice(-1000);
  await putStateJson(env, "provider_usage", runtime.providerUsage);
  return event;
}

async function loadProviderUsage(env) {
  if (env?.ICP_STATE?.get) {
    const stored = await getStateJson(env, "provider_usage", null);
    if (Array.isArray(stored)) {
      runtime.providerUsage = stored.filter((item) => item && typeof item === "object");
      return runtime.providerUsage;
    }
  }
  return runtime.providerUsage;
}

function providerDenied(guard) {
  return json(
    {
      error: guard.reason || "Provider action denied by budget policy.",
      provider_control: guard,
    },
    429,
  );
}

function normalizeProviderAction(action) {
  return String(action || "unknown").trim().toLowerCase().replaceAll("-", "_").replaceAll(" ", "_") || "unknown";
}

function providerAmountsByAction(events) {
  return events.reduce((acc, event) => {
    const action = normalizeProviderAction(event.action);
    acc[action] = (acc[action] || 0) + Number(event.amount || 1);
    return acc;
  }, {});
}

function providerActionAmount(events) {
  return events.reduce((sum, event) => sum + Number(event.amount || 1), 0);
}

function eventWithinSeconds(event, seconds) {
  const createdAt = Date.parse(String(event.created_at || ""));
  if (Number.isNaN(createdAt)) return false;
  return Date.now() - createdAt <= seconds * 1000;
}

function providerStatus(env) {
  return {
    apollo: { configured: Boolean(env.APOLLO_API_KEY), env: "APOLLO_API_KEY" },
    k2: {
      configured: Boolean(env.K2_API_KEY),
      env: "K2_API_KEY",
      base_url: env.K2_BASE_URL || "https://api.knowledge2.ai",
      workspace_project_name: env.K2_ICP_PROJECT_NAME || K2_WORKSPACE_PROJECT_DEFAULT,
      research_corpus_configured: Boolean(env.K2_RESEARCH_CORPUS_ID),
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

async function currentCriteria(env) {
  if (env?.ICP_STATE?.get) {
    const stored = await getStateJson(env, "criteria", null);
    if (stored && typeof stored === "object" && stored.markdown) {
      runtime.criteria = criteriaPayload(String(stored.markdown), String(stored.source || "worker-kv"), String(stored.updated_at || nowIso()));
      return runtime.criteria;
    }
  }
  return runtime.criteria || criteriaPayload(SEED_CRITERIA_MARKDOWN, "icp.md");
}

function criteriaPayload(markdown, source, updatedAt = SEED_CREATED_AT) {
  const hash = criteriaHash(markdown);
  return {
    markdown,
    source,
    updated_at: updatedAt,
    hash,
  };
}

async function persistCriteria(env, criteria) {
  runtime.criteria = criteria;
  await putStateJson(env, "criteria", criteria);
}

async function criteriaVersions(env) {
  await rememberCriteriaVersion(env, await currentCriteria(env));
  return runtime.criteriaVersions.slice(-50);
}

async function rememberCriteriaVersion(env, criteria) {
  if (env?.ICP_STATE?.get) {
    const stored = await getStateJson(env, "criteria_versions", null);
    if (Array.isArray(stored)) {
      runtime.criteriaVersions = stored.filter((item) => item && typeof item === "object" && item.markdown);
    }
  }
  const version = {
    id: criteria.hash,
    hash: criteria.hash,
    markdown: criteria.markdown,
    source: criteria.source,
    updated_at: criteria.updated_at,
  };
  runtime.criteriaVersions = runtime.criteriaVersions.filter((item) => item.hash !== version.hash);
  runtime.criteriaVersions.push(version);
  runtime.criteriaVersions = runtime.criteriaVersions.slice(-50);
  await putStateJson(env, "criteria_versions", runtime.criteriaVersions);
}

function formatCriteriaMarkdown(markdown) {
  const lines = String(markdown || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n");
  const formatted = [];
  let blankCount = 0;
  let inFence = false;
  for (const rawLine of lines) {
    let line = rawLine.replace(/\s+$/g, "").replace(/\t/g, "  ");
    if (line.trim().startsWith("```")) inFence = !inFence;
    if (!inFence) {
      line = line.replace(/^(\s*)[*+]\s+(.+)$/, "$1- $2");
      if (line.startsWith("#") && formatted.length && formatted[formatted.length - 1] !== "") {
        formatted.push("");
      }
    }
    if (line === "") {
      blankCount += 1;
      if (blankCount <= 1) formatted.push(line);
      continue;
    }
    blankCount = 0;
    formatted.push(line);
  }
  while (formatted[0] === "") formatted.shift();
  while (formatted[formatted.length - 1] === "") formatted.pop();
  return `${formatted.join("\n")}\n`;
}

function lintCriteriaMarkdown(markdown) {
  const text = String(markdown || "");
  const lines = text.replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n");
  const diagnostics = [];
  const headings = [];
  let h1Count = 0;
  let inFence = false;
  if (!text.trim()) diagnostics.push(criteriaDiagnostic("error", 1, "empty", "Criteria markdown is empty."));
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const lineNumber = index + 1;
    const trimmed = line.trim();
    if (trimmed.startsWith("```")) inFence = !inFence;
    if (inFence) continue;
    if (line.replace(/\s+$/g, "") !== line) diagnostics.push(criteriaDiagnostic("warning", lineNumber, "trailing-whitespace", "Remove trailing whitespace."));
    if (line.includes("\t")) diagnostics.push(criteriaDiagnostic("warning", lineNumber, "tab-indentation", "Use spaces instead of tabs."));
    if (/^[*+]\s+/.test(trimmed)) diagnostics.push(criteriaDiagnostic("info", lineNumber, "bullet-style", "Use '-' for markdown bullets."));
    const heading = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      const level = heading[1].length;
      headings.push({ line: lineNumber, level });
      if (level === 1) h1Count += 1;
    }
  }
  if (text.trim() && !lines.some((line) => line.startsWith("# "))) {
    diagnostics.push(criteriaDiagnostic("warning", 1, "missing-h1", "Add a top-level '# ...' heading."));
  }
  if (h1Count > 1) diagnostics.push(criteriaDiagnostic("warning", 1, "multiple-h1", "Use one top-level H1 heading."));
  let previousLevel = 0;
  for (const heading of headings) {
    if (previousLevel && heading.level > previousLevel + 1) {
      diagnostics.push(criteriaDiagnostic("warning", heading.line, "heading-jump", "Do not skip heading levels."));
    }
    previousLevel = heading.level;
  }
  const lowered = text.toLowerCase();
  if (!lowered.includes("tier a")) diagnostics.push(criteriaDiagnostic("info", 1, "tier-a-default", "No Tier A threshold found; default scoring threshold applies."));
  if (!lowered.includes("tier b")) diagnostics.push(criteriaDiagnostic("info", 1, "tier-b-default", "No Tier B threshold found; default scoring threshold applies."));
  if (!lowered.includes("employee") && !lowered.includes("budget")) {
    diagnostics.push(criteriaDiagnostic("info", 1, "budget-default", "No employee or budget range found; default budget gates apply."));
  }
  const formatted = formatCriteriaMarkdown(text);
  return {
    diagnostics,
    error_count: diagnostics.filter((item) => item.severity === "error").length,
    warning_count: diagnostics.filter((item) => item.severity === "warning").length,
    info_count: diagnostics.filter((item) => item.severity === "info").length,
    formatted,
    changed: formatted !== text,
  };
}

function criteriaDiagnostic(severity, line, rule, message) {
  return { severity, line, rule, message };
}

function criteriaImpact(run, markdown, lists) {
  if (!String(markdown || "").trim()) throw new Error("Criteria markdown is required.");
  const proposedProfile = criteriaProfileFromMarkdown(markdown, lists, "criteria-impact-preview", criteriaHash(markdown));
  const currentProfile = run.criteria?.profile && typeof run.criteria.profile === "object"
    ? run.criteria.profile
    : seededCriteriaProfile(lists);
  const leads = (run.leads || []).filter((lead) => lead && typeof lead === "object");
  const currentCounts = tierLabelCounts(leads.map((lead) => String(lead.score?.tier || "Unknown")));
  const proposedTiers = [];
  const changes = [];
  for (const lead of leads) {
    const score = lead.score || {};
    const company = score.company || {};
    const currentTier = String(score.tier || "Unknown");
    const totalScore = Number(score.total_score || 0);
    const currentBudget = Number(score.budget_access_score || 0);
    const proposedBudget = estimatedBudgetScore(company, proposedProfile, currentBudget);
    const proposedTotal = Math.max(0, Math.min(100, totalScore - currentBudget + proposedBudget));
    const proposedTier = tierForTotal(proposedTotal, Boolean(score.hard_gate_failed), proposedProfile);
    proposedTiers.push(proposedTier);
    if (proposedTier !== currentTier || proposedTotal !== totalScore) {
      changes.push({
        company: String(company.company || ""),
        domain: String(company.domain || ""),
        current_tier: currentTier,
        proposed_tier: proposedTier,
        current_score: totalScore,
        proposed_score: proposedTotal,
        score_delta: proposedTotal - totalScore,
        reason: criteriaImpactReason(score, company, currentProfile, proposedProfile, currentBudget, proposedBudget),
      });
    }
  }
  const proposedCounts = tierLabelCounts(proposedTiers);
  const warnings = [...(proposedProfile.warnings || [])];
  if (JSON.stringify([...(proposedProfile.priority_terms || [])].sort()) !== JSON.stringify([...(currentProfile.priority_terms || [])].sort())) {
    warnings.push("Priority-term changes require a new run to fully re-score data/workflow boosts from evidence.");
  }
  return {
    run_id: run.id,
    lead_count: leads.length,
    current_profile: currentProfile,
    proposed_profile: proposedProfile,
    lint: lintCriteriaMarkdown(markdown),
    current_counts: currentCounts,
    proposed_counts: proposedCounts,
    deltas: Object.fromEntries(["A", "B", "C", "Reject", "Unknown"].map((tier) => [tier, (proposedCounts[tier] || 0) - (currentCounts[tier] || 0)])),
    changed_count: changes.length,
    changes: changes.sort((left, right) => Math.abs(right.score_delta) - Math.abs(left.score_delta) || String(left.company).localeCompare(String(right.company))).slice(0, 100),
    warnings,
  };
}

function criteriaProfileFromMarkdown(markdown, lists, source, hash) {
  const warnings = [];
  let tierA = criteriaThreshold(markdown, "a", 75, warnings);
  let tierB = criteriaThreshold(markdown, "b", 60, warnings);
  if (tierB >= tierA) {
    warnings.push("Tier B threshold must be lower than Tier A; using default thresholds.");
    tierA = 75;
    tierB = 60;
  }
  const [minEmployees, maxEmployees] = criteriaEmployeeRange(markdown, warnings);
  return {
    source,
    hash,
    tier_a_threshold: tierA,
    tier_b_threshold: tierB,
    min_employee_count: minEmployees,
    max_employee_count: maxEmployees,
    priority_terms: criteriaPriorityTerms(markdown, lists),
    warnings,
  };
}

function criteriaThreshold(markdown, tier, fallback, warnings) {
  const normalized = String(markdown || "").toLowerCase().replace(/[–—]/g, "-");
  const patterns = [
    new RegExp(`tier\\s*${tier}\\s*(?:threshold|score)?\\D{0,30}(\\d{2,3})`, "i"),
    new RegExp(`\\b${tier.toUpperCase()}\\s*tier\\s*(?:threshold|score)?\\D{0,30}(\\d{2,3})`, "i"),
  ];
  for (const pattern of patterns) {
    const match = normalized.match(pattern);
    if (!match) continue;
    const value = Number(match[1]);
    if (value >= 0 && value <= 100) return value;
    warnings.push(`Ignored out-of-range Tier ${tier.toUpperCase()} threshold ${value}.`);
    return fallback;
  }
  return fallback;
}

function criteriaEmployeeRange(markdown, warnings) {
  const normalized = String(markdown || "").toLowerCase().replace(/[–—]/g, "-").replaceAll(",", "");
  const match = normalized.match(/(\d{1,5})\s*-\s*(\d{1,5})\s+employees/);
  if (!match) return [25, 2000];
  const minimum = Number(match[1]);
  const maximum = Number(match[2]);
  if (minimum <= 0 || maximum < minimum) {
    warnings.push("Ignored invalid employee range in criteria markdown.");
    return [25, 2000];
  }
  return [minimum, maximum];
}

function criteriaPriorityTerms(markdown, lists) {
  const known = new Set([...(lists.priority_verticals || []), ...(SEED_LISTS.priority_verticals || []), "govtech", "healthcare admin", "legaltech", "permitting", "cmms", "tms", "wms"]);
  const normalized = String(markdown || "").toLowerCase();
  const terms = new Set([...known].filter((term) => normalized.includes(String(term).toLowerCase())));
  for (const line of normalized.split(/\n/)) {
    if (!["priority vertical", "target vertical", "priority category", "target category"].some((label) => line.includes(label))) continue;
    const payload = line.includes(":") ? line.split(":").slice(1).join(":") : line;
    for (const item of payload.split(/[,;|/]/)) {
      const cleaned = item.replace(/[^a-z0-9 +&-]+/g, " ").replace(/\s+/g, " ").trim().replace(/^-+|-+$/g, "");
      if (cleaned.length >= 2 && cleaned.length <= 40 && !cleaned.startsWith("priority") && !cleaned.startsWith("target")) terms.add(cleaned);
    }
  }
  return terms.size ? [...terms].sort() : [...(SEED_LISTS.priority_verticals || [])];
}

function tierLabelCounts(tiers) {
  const counts = { A: 0, B: 0, C: 0, Reject: 0, Unknown: 0 };
  for (const tier of tiers) counts[tier in counts ? tier : "Unknown"] += 1;
  return counts;
}

function tierForTotal(totalScore, hardGateFailed, profile) {
  if (hardGateFailed) return "Reject";
  if (totalScore >= Number(profile.tier_a_threshold || 75)) return "A";
  if (totalScore >= Number(profile.tier_b_threshold || 60)) return "B";
  return "C";
}

function estimatedBudgetScore(company, profile, fallback) {
  const employeeCount = Number(company.employee_count);
  if (!Number.isFinite(employeeCount)) return fallback;
  const minimum = Number(profile.min_employee_count || 25);
  const maximum = Number(profile.max_employee_count || 2000);
  if (employeeCount >= minimum && employeeCount <= maximum) return 5;
  if (employeeCount > maximum) return 4;
  return 2;
}

function criteriaImpactReason(score, company, currentProfile, proposedProfile, currentBudget, proposedBudget) {
  const reasons = [];
  if (currentProfile.tier_a_threshold !== proposedProfile.tier_a_threshold) reasons.push(`Tier A threshold ${currentProfile.tier_a_threshold} -> ${proposedProfile.tier_a_threshold}.`);
  if (currentProfile.tier_b_threshold !== proposedProfile.tier_b_threshold) reasons.push(`Tier B threshold ${currentProfile.tier_b_threshold} -> ${proposedProfile.tier_b_threshold}.`);
  if (currentBudget !== proposedBudget) {
    reasons.push(`Budget score ${currentBudget} -> ${proposedBudget} from employee range ${proposedProfile.min_employee_count}-${proposedProfile.max_employee_count} and ${company.employee_count || "unknown"} employees.`);
  }
  if (score.hard_gate_failed) reasons.push("Hard gate failure still forces Reject.");
  return reasons.join(" ") || "Tier changed from updated thresholds.";
}

function criteriaHash(markdown) {
  let hash = 2166136261;
  const text = String(markdown || "");
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return `criteria-${(hash >>> 0).toString(16).padStart(8, "0")}`;
}

function nowIso() {
  return new Date().toISOString().replace(/\.\d{3}Z$/, "+00:00");
}

async function loadRuntimeRuns(env) {
  if (env?.ICP_STATE?.get) {
    const stored = await getStateJson(env, "runs", null);
    if (Array.isArray(stored)) {
      runtime.runs = new Map(stored.filter((item) => item && item.id).map((item) => [item.id, item]));
    }
  }
  return runtime.runs;
}

async function saveRun(env, run) {
  const runs = await loadRuntimeRuns(env);
  runs.set(run.id, clone(run));
  runtime.runs = runs;
  await putStateJson(env, "runs", Array.from(runs.values()).slice(-100));
  return run;
}

async function listRuns(env, lists) {
  const runs = await loadRuntimeRuns(env);
  // Pin the seeded showcase first so it is always reachable, then user runs
  // newest-first. Mirrors icp_engine.app_store._leads.list_runs.
  const seedSummary = runtime.runs.has(SEED_RUN_ID)
    ? runSummary(runs.get(SEED_RUN_ID))
    : runSummary(seedRun(lists));
  const userSummaries = Array.from(runs.values())
    .filter((run) => run.id !== SEED_RUN_ID)
    .map(runSummary)
    .sort((left, right) => String(right.created_at || "").localeCompare(String(left.created_at || "")));
  return [seedSummary, ...userSummaries];
}

function defaultLandingRunId(summaries) {
  // Land on the most recent substantive user run; otherwise the seeded
  // showcase. Mirrors icp_engine.app_store._core._default_landing_run_id.
  const substantive = summaries.find(
    (run) => run.id !== SEED_RUN_ID && Number(run.lead_count || 0) >= SUBSTANTIVE_RUN_LEADS,
  );
  return substantive ? substantive.id : SEED_RUN_ID;
}

async function loadRun(env, runId, lists) {
  const runs = await loadRuntimeRuns(env);
  if (runs.has(runId)) return attachWorkflow(env, clone(runs.get(runId)));
  if (runId === SEED_RUN_ID) return attachWorkflow(env, seedRun(lists));
  return null;
}

async function attachWorkflow(env, run) {
  const states = await loadLeadStates(env, run.id);
  for (const lead of run.leads || []) {
    const domain = normalizeDomain(lead.score?.company?.domain || "");
    lead.workflow = states.get(domain) || defaultLeadState(run.id, domain, lead.score?.company?.company || "");
  }
  run.workflow = {
    lead_statuses: ["New", "Review", "Qualified", "Rejected", "Exported"],
    status_counts: leadStatusCounts(run),
    saved_views: await loadLeadViews(env),
  };
  return run;
}

async function loadLeadStates(env, runId) {
  if (env?.ICP_STATE?.get) {
    const stored = await getStateJson(env, "lead_states", null);
    if (stored && typeof stored === "object") {
      runtime.leadStates = new Map(
        Object.entries(stored).map(([itemRunId, runStates]) => [
          itemRunId,
          new Map(Object.entries(runStates || {})),
        ]),
      );
    }
  }
  return runtime.leadStates.get(runId) || new Map();
}

async function persistLeadStates(env) {
  const payload = {};
  for (const [runId, states] of runtime.leadStates.entries()) {
    payload[runId] = Object.fromEntries(states.entries());
  }
  await putStateJson(env, "lead_states", payload);
}

async function saveLeadState(env, runId, payload) {
  const domain = normalizeDomain(payload.domain || "");
  if (!domain) throw new Error("Lead domain is required.");
  const runStates = await loadLeadStates(env, runId);
  const existing = runStates.get(domain) || {};
  const now = nowIso();
  const record = {
    run_id: runId,
    domain,
    company: String(payload.company || existing.company || ""),
    status: normalizeLeadStatus(payload.status || existing.status || "Review"),
    note: String(payload.note ?? existing.note ?? ""),
    owner: String(payload.owner ?? existing.owner ?? ""),
    tags: Array.isArray(payload.tags) ? [...new Set(payload.tags.map((tag) => String(tag).trim()).filter(Boolean))].slice(0, 20) : existing.tags || [],
    created_at: existing.created_at || now,
    updated_at: now,
  };
  runStates.set(domain, record);
  runtime.leadStates.set(runId, runStates);
  await persistLeadStates(env);
  return record;
}

async function bulkUpdateLeadStates(env, run, payload) {
  const domains = Array.isArray(payload.domains) ? payload.domains.map((item) => normalizeDomain(item)).filter(Boolean) : [];
  if (!domains.length) throw new Error("domains must be a non-empty list.");
  const uniqueDomains = [...new Set(domains)];
  const leadsByDomain = new Map(
    (run.leads || []).map((lead) => [normalizeDomain(lead.score?.company?.domain || ""), lead]),
  );
  const updated = [];
  for (const domain of uniqueDomains) {
    const lead = leadsByDomain.get(domain) || {};
    updated.push(await saveLeadState(env, run.id, {
      domain,
      company: lead.score?.company?.company || "",
      status: payload.status || "Review",
      note: payload.note || "",
      owner: payload.owner || "",
      tags: Array.isArray(payload.tags) ? payload.tags : undefined,
    }));
  }
  const hydrated = await attachWorkflow(env, run);
  return {
    run_id: run.id,
    updated_count: updated.length,
    lead_states: updated,
    status_counts: leadStatusCounts(hydrated),
  };
}

async function loadLeadViews(env) {
  if (env?.ICP_STATE?.get) {
    const stored = await getStateJson(env, "lead_views", null);
    if (Array.isArray(stored)) {
      runtime.leadViews = stored.filter((item) => item && typeof item === "object" && item.name);
      return runtime.leadViews;
    }
  }
  return runtime.leadViews;
}

async function saveLeadView(env, payload) {
  const cleanName = String(payload.name || "").trim().replace(/\s+/g, " ");
  if (!cleanName) throw new Error("View name is required.");
  const views = await loadLeadViews(env);
  const viewId = `lead-view-${criteriaHash(cleanName.toLowerCase()).replace("criteria-", "")}`;
  const previous = views.find((item) => item.id === viewId) || {};
  const now = nowIso();
  const view = {
    id: viewId,
    name: cleanName,
    filters: payload.filters && typeof payload.filters === "object" && !Array.isArray(payload.filters) ? clone(payload.filters) : {},
    sort: normalizeLeadViewSort(payload.sort),
    page_size: normalizeLeadViewPageSize(payload.page_size || previous.page_size || 50),
    created_at: previous.created_at || now,
    updated_at: now,
  };
  runtime.leadViews = [...views.filter((item) => item.id !== viewId), view]
    .sort((left, right) => String(left.name || "").localeCompare(String(right.name || "")));
  await putStateJson(env, "lead_views", runtime.leadViews);
  return view;
}

function normalizeLeadViewSort(input) {
  const sort = input && typeof input === "object" && !Array.isArray(input) ? input : {};
  const field = String(sort.field || "score").trim().toLowerCase();
  return {
    field: ["score", "company", "tier", "status", "source"].includes(field) ? field : "score",
    direction: String(sort.direction || "desc").toLowerCase() === "asc" ? "asc" : "desc",
  };
}

function normalizeLeadViewPageSize(value) {
  const pageSize = Number(value || 50);
  return Number.isFinite(pageSize) ? Math.max(10, Math.min(Math.trunc(pageSize), 500)) : 50;
}

async function saveQualityFeedback(env, runId, payload) {
  const domain = normalizeDomain(payload.domain || "");
  if (!domain) throw new Error("Lead domain is required.");
  const dimension = normalizeQualityDimension(payload.dimension || "score");
  const rating = normalizeQualityRating(payload.rating || "positive");
  const now = nowIso();
  const events = await loadQualityFeedback(env);
  const record = {
    id: criteriaHash(`${now}:${runId}:${domain}:${dimension}:${rating}:${events.length}`).slice(0, 16),
    run_id: runId,
    domain,
    company: String(payload.company || "").trim().replace(/\s+/g, " "),
    dimension,
    rating,
    target_id: String(payload.target_id || ""),
    target_label: String(payload.target_label || "").trim().replace(/\s+/g, " "),
    note: String(payload.note || "").trim(),
    label_source: "operator_feedback",
    k2_feedback_outcome: qualityFeedbackOutcome(rating),
    created_at: now,
  };
  events.push(record);
  await persistQualityFeedback(env, events.slice(-1000));
  return record;
}

async function listQualityFeedback(env, { runId = "", domain = "", limit = 100 } = {}) {
  const domainKey = normalizeDomain(domain);
  let events = await loadQualityFeedback(env);
  if (runId) events = events.filter((event) => event.run_id === runId);
  if (domainKey) events = events.filter((event) => normalizeDomain(event.domain || "") === domainKey);
  return events.slice(-Math.max(1, Math.min(Number(limit) || 100, 1000)));
}

async function qualityFeedbackSummary(env, { runId = "", domain = "" } = {}) {
  const events = await listQualityFeedback(env, { runId, domain, limit: 1000 });
  const ratingCounts = { positive: 0, neutral: 0, negative: 0 };
  const dimensionCounts = { score: 0, persona: 0, outreach: 0 };
  for (const event of events) {
    const rating = normalizeQualityRating(event.rating || "neutral");
    const dimension = normalizeQualityDimension(event.dimension || "score");
    ratingCounts[rating] += 1;
    dimensionCounts[dimension] += 1;
  }
  const total = events.length;
  return {
    total,
    rating_counts: ratingCounts,
    dimension_counts: dimensionCounts,
    positive_rate: total ? Math.round((ratingCounts.positive / total) * 10000) / 10000 : 0,
    recent_feedback: events.slice(-25),
  };
}

async function qualityFeedbackCsv(env, { runId = "", domain = "" } = {}) {
  const headers = ["id", "created_at", "run_id", "company", "domain", "dimension", "rating", "target_id", "target_label", "note", "label_source", "k2_feedback_outcome"];
  const lines = [headers.join(",")];
  for (const row of await listQualityFeedback(env, { runId, domain, limit: 1000 })) {
    lines.push(headers.map((header) => csvCell(row[header] || "")).join(","));
  }
  return `${lines.join("\n")}\n`;
}

async function getStateJson(env, key, fallback) {
  if (!env?.ICP_STATE?.get) return fallback;
  try {
    const stored = await env.ICP_STATE.get(key, "json");
    return stored === null || stored === undefined ? fallback : stored;
  } catch {
    return fallback;
  }
}

async function putStateJson(env, key, value) {
  if (env?.ICP_STATE?.put) {
    await env.ICP_STATE.put(key, JSON.stringify(value));
  }
}

async function workspaceStateStatus(env) {
  const durable = Boolean(env?.ICP_STATE?.get && env?.ICP_STATE?.put);
  const collections = [];
  for (const collection of STATE_COLLECTIONS) {
    collections.push(await stateCollectionStatus(env, collection));
  }
  return {
    durable,
    store: durable ? "cloudflare-kv" : "runtime-memory",
    collections,
    warnings: durable ? [] : ["ICP_STATE KV binding is missing; Worker state is isolate-memory only."],
  };
}

async function stateCollectionStatus(env, collection) {
  if (env?.ICP_STATE?.get) {
    const stored = await getStateJson(env, collection.key, null);
    return {
      key: collection.key,
      type: collection.type,
      persisted: stored !== null && stored !== undefined,
      count: stateCollectionCount(collection.key, stored),
    };
  }
  return {
    key: collection.key,
    type: collection.type,
    persisted: false,
    count: stateCollectionCount(collection.key, runtimeStateValue(collection.key)),
  };
}

function stateCollectionCount(key, value) {
  if (value === null || value === undefined) return 0;
  if (Array.isArray(value)) return value.length;
  if (typeof value === "object") {
    if (key === "criteria" || key === "settings") return 1;
    if (key === "lead_states") {
      return Object.values(value).reduce((sum, states) => sum + (states && typeof states === "object" ? Object.keys(states).length : 0), 0);
    }
    if (key === "outreach_statuses") {
      return Object.values(value).reduce((sum, statuses) => sum + (statuses && typeof statuses === "object" ? Object.keys(statuses).length : 0), 0);
    }
    return Object.keys(value).length;
  }
  return 0;
}

function runtimeStateValue(key) {
  if (key === "runs") return Array.from(runtime.runs.values());
  if (key === "lead_states") {
    return Object.fromEntries([...runtime.leadStates.entries()].map(([runId, states]) => [runId, Object.fromEntries(states.entries())]));
  }
  return {
    criteria: runtime.criteria,
    criteria_versions: runtime.criteriaVersions,
    settings: runtime.settings,
    sources: runtime.sources,
    source_scans: runtime.sourceScans,
    expansion_runs: runtime.expansionRuns,
    provider_usage: runtime.providerUsage,
    lead_views: runtime.leadViews,
    quality_feedback: runtime.qualityFeedback,
    outreach_statuses: runtime.outreachStatuses,
    eval_cases: runtime.evalCases,
    eval_runs: runtime.evalRuns,
  }[key];
}

async function loadQualityFeedback(env) {
  if (env?.ICP_STATE?.get) {
    const stored = await getStateJson(env, "quality_feedback", null);
    if (Array.isArray(stored)) {
      runtime.qualityFeedback = stored.filter((item) => item && typeof item === "object");
      return runtime.qualityFeedback;
    }
  }
  return runtime.qualityFeedback;
}

async function persistQualityFeedback(env, events) {
  runtime.qualityFeedback = Array.isArray(events) ? events : [];
  await putStateJson(env, "quality_feedback", runtime.qualityFeedback);
}

function normalizeQualityDimension(value) {
  const dimension = String(value || "score").trim().toLowerCase().replaceAll("-", "_").replaceAll(" ", "_") || "score";
  if (!["score", "persona", "outreach"].includes(dimension)) throw new Error(`Invalid feedback dimension: ${value}.`);
  return dimension;
}

function normalizeQualityRating(value) {
  let rating = String(value || "neutral").trim().toLowerCase().replaceAll("-", "_").replaceAll(" ", "_") || "neutral";
  if (["good", "yes", "useful", "correct"].includes(rating)) rating = "positive";
  if (["bad", "no", "wrong", "poor"].includes(rating)) rating = "negative";
  if (!["positive", "neutral", "negative"].includes(rating)) throw new Error(`Invalid feedback rating: ${value}.`);
  return rating;
}

function qualityFeedbackOutcome(rating) {
  return { positive: "accepted", neutral: "needs_review", negative: "rejected" }[rating] || "needs_review";
}

async function listOutreachDrafts(env, run, { domain = "" } = {}) {
  const domainKey = normalizeDomain(domain || "");
  const statuses = await loadOutreachStatuses(env, run.id);
  const leadsById = new Map((run.leads || []).map((lead) => [String(lead.id || ""), lead]));
  const prospects = buildRunProspects(run).prospects;
  return prospects
    .filter((prospect) => !domainKey || normalizeDomain(prospect.domain || "") === domainKey)
    .map((prospect) => {
      const lead = leadsById.get(String(prospect.lead_id || "")) || {};
      return outreachDraftForProspect(run, lead, prospect, statuses[String(prospect.id || "")] || {});
    });
}

function outreachDraftForProspect(run, lead, prospect, statusRecord) {
  const evidence = (lead.evidence || []).filter((item) => item && typeof item === "object").slice(0, 2);
  const evidenceRefs = evidence.map((item) => ({
    title: String(item.title || item.url || "Evidence"),
    url: String(item.url || ""),
    snippet: String(item.text || "").slice(0, 220),
  }));
  const company = lead.score?.company || {};
  const companyName = String(company.company || prospect.company || "your team");
  const contactLabel = String(prospect.name || prospect.persona || prospect.title || "there");
  const firstName = contactLabel.includes(" ") ? contactLabel.split(/\s+/)[0] : contactLabel;
  const strategy = lead.strategy || {};
  const angle = String(strategy.outreach_angle || prospect.outreach_angle || "Your workflow data may support a sharper AI product narrative.");
  const offer = String(strategy.offer || "Propose a 2-week AI opportunity map grounded in existing product data and evidence.");
  const firstStep = String(strategy.first_step || prospect.first_step || "Share a short account-specific brief.");
  const evidenceLine = evidenceRefs[0]?.snippet
    ? `${evidenceRefs[0].title}: ${evidenceRefs[0].snippet}`
    : evidenceRefs[0]?.title || "public evidence that suggests an operational workflow/data asset";
  const prospectId = String(prospect.id || "");
  return {
    id: `draft-${prospectId}`,
    run_id: run.id,
    lead_id: lead.id || prospect.lead_id || "",
    prospect_id: prospectId,
    company: companyName,
    domain: String(company.domain || prospect.domain || ""),
    prospect_name: String(prospect.name || ""),
    title: String(prospect.title || ""),
    persona: String(prospect.persona || prospect.title || ""),
    source: String(prospect.source || ""),
    status: normalizeOutreachStatus(statusRecord.status || "Draft"),
    subject: `${companyName} AI workflow opportunity map`,
    body: [
      `Hi ${firstName || "there"},`,
      `I was reviewing ${companyName} and noticed ${evidenceLine}.`,
      angle,
      `A practical next step would be: ${offer}`,
      `Would it be useful to compare this against one workflow where ${companyName} already has proprietary operational data?`,
    ].join("\n\n"),
    cta: firstStep,
    evidence: evidenceRefs,
    evidence_titles: evidenceRefs.map((item) => item.title),
    evidence_urls: evidenceRefs.map((item) => item.url),
    outreach_angle: angle,
    first_step: firstStep,
    approval_note: String(statusRecord.note || ""),
    updated_at: String(statusRecord.updated_at || ""),
  };
}

function normalizeOutreachStatus(value) {
  const status = String(value || "Draft").trim().replace(/\b\w/g, (letter) => letter.toUpperCase()) || "Draft";
  if (!["Draft", "Approved", "Rejected", "Exported"].includes(status)) throw new Error(`Invalid outreach status: ${value}.`);
  return status;
}

function outreachSummary(drafts) {
  const status_counts = { Draft: 0, Approved: 0, Rejected: 0, Exported: 0 };
  for (const draft of drafts || []) {
    status_counts[normalizeOutreachStatus(draft.status || "Draft")] += 1;
  }
  return {
    total: (drafts || []).length,
    status_counts,
    ready_count: status_counts.Approved + status_counts.Exported,
  };
}

async function workspaceOutreachSummary(env, lists) {
  const runs = await listRuns(env, lists);
  const status_counts = { Draft: 0, Approved: 0, Rejected: 0, Exported: 0 };
  let total = 0;
  for (const summary of runs) {
    const run = await loadRun(env, summary.id, lists);
    if (!run) continue;
    const runSummary = outreachSummary(await listOutreachDrafts(env, run));
    total += runSummary.total;
    for (const [status, count] of Object.entries(runSummary.status_counts)) {
      status_counts[status] = (status_counts[status] || 0) + Number(count || 0);
    }
  }
  return { total, status_counts, ready_count: status_counts.Approved + status_counts.Exported };
}

async function saveOutreachStatus(env, runId, payload) {
  const prospectId = String(payload.prospect_id || "").trim();
  if (!prospectId) throw new Error("Prospect id is required.");
  const statuses = await loadAllOutreachStatuses(env);
  const runStatuses = statuses[runId] && typeof statuses[runId] === "object" ? statuses[runId] : {};
  const existing = runStatuses[prospectId] && typeof runStatuses[prospectId] === "object" ? runStatuses[prospectId] : {};
  const now = nowIso();
  const record = {
    run_id: runId,
    prospect_id: prospectId,
    domain: normalizeDomain(payload.domain || existing.domain || ""),
    company: String(payload.company || existing.company || "").trim().replace(/\s+/g, " "),
    status: normalizeOutreachStatus(payload.status || existing.status || "Approved"),
    note: String(payload.note ?? existing.note ?? ""),
    created_at: existing.created_at || now,
    updated_at: now,
  };
  runStatuses[prospectId] = record;
  statuses[runId] = runStatuses;
  await persistOutreachStatuses(env, statuses);
  return record;
}

async function loadOutreachStatuses(env, runId) {
  const statuses = await loadAllOutreachStatuses(env);
  return statuses[runId] && typeof statuses[runId] === "object" ? statuses[runId] : {};
}

async function loadAllOutreachStatuses(env) {
  if (env?.ICP_STATE?.get) {
    const stored = await getStateJson(env, "outreach_statuses", null);
    if (stored && typeof stored === "object" && !Array.isArray(stored)) {
      runtime.outreachStatuses = stored;
      return runtime.outreachStatuses;
    }
  }
  return runtime.outreachStatuses || {};
}

async function persistOutreachStatuses(env, statuses) {
  runtime.outreachStatuses = statuses && typeof statuses === "object" ? statuses : {};
  await putStateJson(env, "outreach_statuses", runtime.outreachStatuses);
}

function outreachDraftsCsv(drafts) {
  const fields = ["id", "run_id", "lead_id", "prospect_id", "company", "domain", "prospect_name", "title", "persona", "source", "status", "subject", "body", "cta", "evidence_titles", "evidence_urls", "outreach_angle", "first_step", "approval_note", "updated_at"];
  return `${fields.join(",")}\n${(drafts || []).map((row) => fields.map((field) => csvCell(Array.isArray(row[field]) ? row[field].join("; ") : row[field])).join(",")).join("\n")}\n`;
}

async function loadEvalCases(env, run) {
  if (env?.ICP_STATE?.get) {
    const stored = await getStateJson(env, "eval_cases", null);
    if (Array.isArray(stored)) {
      runtime.evalCases = stored.map((item) => normalizeEvalCase(item)).filter(Boolean);
      return runtime.evalCases.length ? runtime.evalCases : defaultEvalCases(run);
    }
  }
  if (runtime.evalCases) return runtime.evalCases;
  return defaultEvalCases(run);
}

async function saveEvalCase(env, payload) {
  const item = normalizeEvalCase(payload);
  const cases = (await loadEvalCases(env, null)).filter((existing) => existing.id !== item.id);
  cases.push(item);
  runtime.evalCases = cases.sort((left, right) => String(left.id).localeCompare(String(right.id)));
  await putStateJson(env, "eval_cases", runtime.evalCases);
  return item;
}

function normalizeEvalCase(input) {
  const type = String(input?.type || "qualification").trim().toLowerCase().replaceAll("-", "_");
  if (!["qualification", "data_load", "prospect_tree", "research", "outreach"].includes(type)) throw new Error(`Invalid eval case type: ${type}.`);
  return {
    id: String(input.id || criteriaHash(JSON.stringify(input || {})).slice(0, 12)),
    type,
    domain: normalizeDomain(input.domain || ""),
    company: String(input.company || "").trim().replace(/\s+/g, " "),
    expected: input.expected && typeof input.expected === "object" ? input.expected : {},
    criteria_hash: String(input.criteria_hash || ""),
    label_source: String(input.label_source || "bootstrap_generated"),
    rationale: String(input.rationale || ""),
    created_at: String(input.created_at || nowIso()),
  };
}

function defaultEvalCases(run) {
  const domains = new Set((run?.leads || []).map((lead) => normalizeDomain(lead.score?.company?.domain || "")));
  const cases = [
    {
      id: "case-mojio-tier-a",
      type: "qualification",
      domain: "moj.io",
      company: "Mojio",
      expected: { tier: "A", hard_gate_failed: false },
      label_source: "expert_labeled",
      rationale: "Named ICP example with connected mobility workflow and telematics data.",
    },
    {
      id: "case-automate-tier-a",
      type: "qualification",
      domain: "automate.co.za",
      company: "Automate",
      expected: { tier: "A", hard_gate_failed: false },
      label_source: "expert_labeled",
      rationale: "Named ICP/Volaris example with dealership workflow data.",
    },
    {
      id: "case-servicetitan-tier-a",
      type: "qualification",
      domain: "servicetitan.com",
      company: "ServiceTitan",
      expected: { tier: "A", hard_gate_failed: false },
      label_source: "seeded_gold",
      rationale: "Qualified data-run account with field-service workflow depth.",
    },
    {
      id: "case-ai-native-reject",
      type: "qualification",
      domain: "example.com",
      company: "AI Native Example",
      expected: { tier: "Reject", hard_gate_failed: true },
      label_source: "negative_control",
      rationale: "Seeded reject control for AI-native/too-new companies.",
    },
  ].map(normalizeEvalCase);
  if (!domains.size) return cases;
  const present = cases.filter((item) => domains.has(item.domain));
  return present.length ? present : [normalizeEvalCase({
    id: "case-current-run-data-load",
    type: "data_load",
    expected: { min_leads: 1, min_evidence_coverage: 0.8 },
    label_source: "bootstrap_generated",
    rationale: "Bootstrap data-load coverage case for the active run.",
  })];
}

async function runIcpEval(env, run, lists, caseIds = []) {
  let cases = await loadEvalCases(env, run);
  if (caseIds.length) {
    const selected = new Set(caseIds.map(String));
    cases = cases.filter((item) => selected.has(item.id));
  }
  const leads = (run.leads || []).filter((lead) => lead && typeof lead === "object");
  const nonRejectLeads = leads.filter((lead) => lead.score?.tier !== "Reject");
  const domains = leads.map((lead) => normalizeDomain(lead.score?.company?.domain || "")).filter(Boolean);
  const uniqueDomains = new Set(domains);
  const duplicateDomains = [...uniqueDomains].filter((domain) => domains.filter((item) => item === domain).length > 1);
  const prospects = buildRunProspects(run).prospects;
  const outreachDrafts = await listOutreachDrafts(env, run);
  const feedback = await listQualityFeedback(env, { runId: run.id, limit: 1000 });
  const qualificationResults = qualificationCaseResults(cases, leads);
  const coverage = await sourceCoverage(env, lists);
  const metrics = {
    lead_count: leads.length,
    non_reject_lead_count: nonRejectLeads.length,
    unique_domain_count: uniqueDomains.size,
    duplicate_domain_count: duplicateDomains.length,
    duplicate_domain_rate: ratio(duplicateDomains.length, uniqueDomains.size),
    required_metadata_completeness: requiredMetadataCompleteness(leads),
    evidence_coverage: ratio(leads.filter((lead) => (lead.evidence || []).length).length, leads.length),
    citation_coverage: ratio(leads.filter(leadHasCitableEvidence).length, leads.length),
    qualification_case_pass_rate: ratio(qualificationResults.filter((item) => item.passed).length, qualificationResults.length),
    qualification_case_count: qualificationResults.length,
    prospect_role_coverage: prospectRoleCoverage(nonRejectLeads, prospects),
    named_contact_rate: ratio(prospects.filter((item) => item.status === "person_found" && item.name).length, prospects.length),
    contact_detail_rate: ratio(prospects.filter((item) => item.email || item.phone || item.linkedin_url).length, prospects.length),
    outreach_draft_coverage: outreachDraftCoverage(nonRejectLeads, outreachDrafts),
    outreach_ready_rate: ratio(outreachSummary(outreachDrafts).ready_count, outreachDrafts.length),
    operator_feedback_count: feedback.length,
    operator_positive_rate: ratio(feedback.filter((item) => item.rating === "positive").length, feedback.length),
    source_count: Number(coverage.source_count || 0),
    source_scan_count: Number(coverage.scan_count || 0),
    source_unique_candidate_domains: Number(coverage.unique_candidate_domains || 0),
  };
  const checks = evalThresholdChecks(metrics);
  const failures = evalFailures(leads, duplicateDomains, qualificationResults, checks);
  const now = nowIso();
  return {
    id: `eval-${now.replaceAll(":", "").replaceAll("-", "").slice(0, 15)}-${criteriaHash(run.id).slice(0, 8)}`,
    run_id: run.id,
    status: failures.length ? "needs_review" : "passed",
    created_at: now,
    case_set_hash: criteriaHash(JSON.stringify(cases)).slice(0, 12),
    criteria_hash: String(run.criteria?.hash || ""),
    case_count: cases.length,
    metrics,
    checks,
    case_results: qualificationResults,
    failures: failures.slice(0, 100),
    k2_alignment: {
      system_of_record: "K2 quality/eval/feedback primitives when available",
      primitives: ["EvalRun", "GoldLabel", "Feedback", "QualityMetrics", "Metadata", "Feeds", "Agents"],
      native_eval_status: {
        configured: Boolean(env.K2_API_KEY),
        base_url: env.K2_BASE_URL || "https://api.knowledge2.ai",
        reason: "K2 native EvalRun creation is feature-gated/internal in current K2 dev docs; local ICP eval remains canonical for this app slice.",
      },
    },
    oss_adapters: {
      langfuse: { enabled: false, status: "not_configured", reason: "Optional trace/eval adapter. K2 remains the quality system of record." },
      phoenix: { enabled: false, status: "not_configured", reason: "Optional OSS observability adapter for traces and LLM judge experiments." },
    },
  };
}

function qualificationCaseResults(cases, leads) {
  const byDomain = new Map(leads.map((lead) => [normalizeDomain(lead.score?.company?.domain || ""), lead]));
  return cases.filter((item) => item.type === "qualification").map((item) => {
    const lead = byDomain.get(item.domain);
    const expected = item.expected || {};
    const score = lead?.score || {};
    let passed = Boolean(lead);
    if (expected.tier) passed = passed && score.tier === expected.tier;
    if (expected.hard_gate_failed !== undefined) passed = passed && Boolean(score.hard_gate_failed) === Boolean(expected.hard_gate_failed);
    return {
      case_id: item.id,
      domain: item.domain,
      company: item.company,
      passed,
      expected,
      actual: {
        tier: lead ? score.tier || "" : "",
        hard_gate_failed: lead ? Boolean(score.hard_gate_failed) : null,
        total_score: lead ? score.total_score : null,
      },
      reason: passed ? "matched" : "expected qualification did not match produced lead",
    };
  });
}

function evalThresholdChecks(metrics) {
  const thresholds = {
    required_metadata_completeness: 0.85,
    evidence_coverage: 0.8,
    qualification_case_pass_rate: 0.9,
    prospect_role_coverage: 0.8,
    outreach_draft_coverage: 0.8,
  };
  const checks = {};
  for (const [name, threshold] of Object.entries(thresholds)) {
    if (name === "qualification_case_pass_rate" && !metrics.qualification_case_count) {
      checks[name] = { threshold, passed: true, skipped: true, reason: "No qualification cases matched this run." };
    } else {
      checks[name] = { threshold, value: Number(metrics[name] || 0), passed: Number(metrics[name] || 0) >= threshold };
    }
  }
  return checks;
}

function evalFailures(leads, duplicateDomains, qualificationResults, checks) {
  const failures = [];
  for (const [metric, check] of Object.entries(checks)) {
    if (!check.passed) failures.push({ type: "metric_threshold", metric, value: check.value, threshold: check.threshold });
  }
  for (const domain of duplicateDomains) failures.push({ type: "duplicate_domain", domain });
  for (const result of qualificationResults) {
    if (!result.passed) failures.push({ type: "qualification_case", ...result });
  }
  for (const lead of leads) {
    if (!leadHasCitableEvidence(lead)) failures.push({ type: "missing_citable_evidence", lead_id: lead.id, domain: normalizeDomain(lead.score?.company?.domain || "") });
  }
  return failures;
}

function requiredMetadataCompleteness(leads) {
  const checks = [
    (lead) => Boolean(lead.id),
    (lead) => Boolean(lead.score?.company?.company),
    (lead) => Boolean(lead.score?.company?.domain),
    (lead) => Boolean(lead.score?.tier),
    (lead) => lead.score?.total_score !== undefined,
    (lead) => Boolean(lead.strategy?.outreach_angle),
    (lead) => Boolean((lead.strategy?.personas || []).length),
    (lead) => Boolean(lead.metadata?.criteria_profile || lead.metadata?.qualification),
    (lead) => Boolean((lead.evidence || []).length),
  ];
  if (!leads.length) return 0;
  let passed = 0;
  for (const lead of leads) {
    for (const check of checks) {
      if (check(lead)) passed += 1;
    }
  }
  return ratio(passed, leads.length * checks.length);
}

function leadHasCitableEvidence(lead) {
  return (lead.evidence || []).some((item) => item?.url && (item.text || item.title));
}

function prospectRoleCoverage(leads, prospects) {
  if (!leads.length) return 1;
  const covered = new Set(prospects.filter((item) => item.persona || item.title).map((item) => String(item.lead_id || "")));
  return ratio(leads.filter((lead) => covered.has(String(lead.id || ""))).length, leads.length);
}

function outreachDraftCoverage(leads, drafts) {
  if (!leads.length) return 1;
  const covered = new Set(drafts.map((item) => String(item.lead_id || "")));
  return ratio(leads.filter((lead) => covered.has(String(lead.id || ""))).length, leads.length);
}

function ratio(numerator, denominator) {
  const bottom = Number(denominator || 0);
  if (!bottom) return 0;
  return Math.round((Number(numerator || 0) / bottom) * 10000) / 10000;
}

async function listEvalRuns(env, { runId = "" } = {}) {
  if (env?.ICP_STATE?.get) {
    const stored = await getStateJson(env, "eval_runs", null);
    if (Array.isArray(stored)) {
      runtime.evalRuns = stored.filter((item) => item && typeof item === "object");
    }
  }
  const runs = runtime.evalRuns || [];
  return runId ? runs.filter((item) => item.run_id === runId) : runs;
}

async function appendEvalRun(env, result) {
  const runs = await listEvalRuns(env);
  runs.push(result);
  runtime.evalRuns = runs.slice(-500);
  await putStateJson(env, "eval_runs", runtime.evalRuns);
  return runtime.evalRuns;
}

function evalSummary(runs) {
  const ordered = [...(runs || [])].sort((left, right) => String(left.created_at || "").localeCompare(String(right.created_at || "")));
  const latest = ordered[ordered.length - 1] || null;
  const status_counts = {};
  for (const run of ordered) {
    const status = String(run.status || "unknown");
    status_counts[status] = (status_counts[status] || 0) + 1;
  }
  return {
    total: ordered.length,
    status_counts,
    latest_run: latest,
    latest_status: latest ? latest.status : "not_run",
    latest_metrics: latest?.metrics || {},
    latest_failures: (latest?.failures || []).slice(0, 10),
  };
}

function evalRunsCsv(runs) {
  const fields = ["id", "run_id", "status", "case_set_hash", "criteria_hash", "metric_name", "metric_value", "threshold", "passed"];
  const lines = [fields.join(",")];
  for (const run of runs || []) {
    const metrics = run.metrics || {};
    const checks = run.checks || {};
    for (const [name, value] of Object.entries(metrics)) {
      const check = checks[name] || {};
      lines.push(fields.map((field) => csvCell({
        id: run.id,
        run_id: run.run_id,
        status: run.status,
        case_set_hash: run.case_set_hash,
        criteria_hash: run.criteria_hash,
        metric_name: name,
        metric_value: value,
        threshold: check.threshold ?? "",
        passed: check.passed ?? "",
      }[field])).join(","));
    }
  }
  return `${lines.join("\n")}\n`;
}

function defaultLeadState(runId, domain, company) {
  return { run_id: runId, domain, company, status: "New", note: "", owner: "", tags: [], created_at: "", updated_at: "" };
}

function normalizeLeadStatus(value) {
  const status = String(value || "").trim().replace(/\b\w/g, (letter) => letter.toUpperCase());
  if (!["New", "Review", "Qualified", "Rejected", "Exported"].includes(status)) throw new Error(`Invalid lead status: ${value}.`);
  return status;
}

function leadStatusCounts(run) {
  const counts = { New: 0, Review: 0, Qualified: 0, Rejected: 0, Exported: 0 };
  for (const lead of run.leads || []) {
    const status = lead.workflow?.status || "New";
    counts[status] = (counts[status] || 0) + 1;
  }
  return counts;
}

async function accountDetail(run, accountKey, env) {
  const lead = findLead(run, accountKey);
  if (!lead) return null;
  const company = lead.score?.company || {};
  const domain = normalizeDomain(company.domain || "");
  const prospects = buildRunProspects(run).prospects.filter((prospect) => normalizeDomain(prospect.domain || "") === domain || prospect.lead_id === lead.id);
  const outreachDrafts = await listOutreachDrafts(env, run, { domain });
  const workflow = lead.workflow || defaultLeadState(run.id, domain, company.company || "");
  const criteria = run.criteria || {};
  return {
    run_id: run.id,
    lead_id: lead.id,
    company,
    score: lead.score || {},
    strategy: lead.strategy || {},
    workflow,
    lead_statuses: ["New", "Review", "Qualified", "Rejected", "Exported"],
    prospects,
    role_groups: prospectRoleGroups(prospects),
    evidence_timeline: evidenceTimeline(lead.evidence || []),
    source_refs: lead.metadata?.source_refs || {},
    source_counts: lead.metadata?.source_counts || {},
    coverage: lead.metadata?.intelligence_coverage || {},
    criteria_snapshot: {
      hash: criteria.hash || lead.metadata?.criteria_profile?.hash || "",
      source: criteria.source || "",
      profile: criteria.profile || lead.metadata?.criteria_profile || {},
    },
    quality_feedback: await listQualityFeedback(env, { runId: run.id, domain, limit: 25 }),
    quality_summary: await qualityFeedbackSummary(env, { runId: run.id, domain }),
    outreach_drafts: outreachDrafts,
    outreach_summary: outreachSummary(outreachDrafts),
    audit_events: [],
  };
}

function findLead(run, accountKey) {
  const key = normalizeDomain(accountKey);
  return (run.leads || []).find((lead) => {
    const company = lead.score?.company || {};
    return [lead.id, lead.domain, lead.company, company.domain, company.company].map((item) => normalizeDomain(item || "")).includes(key);
  });
}

function prospectRoleGroups(prospects) {
  const groups = new Map();
  for (const prospect of [...prospects].sort((left, right) => prospectSortRank(left) - prospectSortRank(right))) {
    const role = prospect.persona || prospect.title || "Other role";
    if (!groups.has(role)) groups.set(role, []);
    groups.get(role).push(prospect);
  }
  return Array.from(groups.entries()).map(([role, items]) => ({ role, priority: items[0]?.persona_priority || items[0]?.source || "", prospects: items }));
}

function prospectSortRank(prospect) {
  const priority = { primary: 0, secondary: 1, tertiary: 2 }[String(prospect.persona_priority || "").toLowerCase()] ?? 3;
  const source = String(prospect.source || "").toLowerCase() === "apollo" ? 0 : 1;
  return priority * 1000 + source * 100 - Number(prospect.priority_score || 0);
}

function evidenceTimeline(evidence) {
  return evidence.map((item, index) => {
    const metadata = item.metadata || {};
    return {
      id: item.evidence_id || `evidence-${index + 1}`,
      title: item.title || item.url || "Evidence",
      url: item.url || "",
      text: item.text || "",
      source_type: item.source_type || metadata.source_type || metadata.page_category || "website",
      page_category: metadata.page_category || "",
      captured_at: item.captured_at || metadata.captured_at || "",
    };
  });
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
      if (looksLikeSeedHeader(parts)) return null;
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

function looksLikeSeedHeader(parts) {
  if (!Array.isArray(parts) || parts.length < 2) return false;
  const first = String(parts[0] || "").toLowerCase();
  const second = String(parts[1] || "").toLowerCase();
  return ["company", "company name", "name", "account"].includes(first) && ["domain", "website", "url", "company domain"].includes(second);
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
  const criteria = await currentCriteria(env);
  const run = {
    id: runId,
    query: String(payload.query || ""),
    created_at: new Date().toISOString().replace(/\.\d{3}Z$/, "+00:00"),
    status: "completed",
    criteria: {
      hash: criteria.hash,
      source: criteria.source,
      updated_at: criteria.updated_at,
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
  // Runtime candidates without a baked qualification block get vertical-focus
  // moat scoring; the seeded 428 keep their pre-rendered scores untouched.
  const moat = !reject && !Object.keys(qualification).length ? liveMoat(account, candidate) : null;
  const dataWorkflowDefault = reject ? 5 : account.domain === "moj.io" ? 25 : moat ? moat.dataWorkflowScore : 22;
  const totalDefault = reject ? 24 : account.domain === "moj.io" ? 82 : (highPriority ? 79 : 68) + (moat ? moat.totalDelta : 0);
  const score = qualifiedNumber(qualification, "total_score", totalDefault);
  const aiPosture = qualifiedNumber(qualification, "ai_posture", reject ? 5 : 0);
  const dataWorkflow = Math.max(0, Math.min(5, Math.round(qualifiedNumber(qualification, "data_workflow_score", dataWorkflowDefault) / 5)));
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
      data_workflow_score: qualifiedNumber(qualification, "data_workflow_score", dataWorkflowDefault),
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

function boundaryKeywordHit(text, term) {
  const needle = String(term || "").toLowerCase().trim();
  if (!needle) return false;
  const escaped = needle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`\\b${escaped}\\b`).test(text);
}

// Live-candidate moat scoring, mirroring scoring.score_company: vertical-market
// focus deepens the workflow moat, explicit horizontal-audience language caps it,
// and unrecognized niches stay neutral. Only applied to runtime candidates that
// lack a baked qualification block (the seeded 428 carry their own scores).
function liveMoat(account, candidate) {
  const text = `${account.category || ""} ${account.notes || candidate?.notes || ""}`.toLowerCase();
  const verticalHit = (SEED_LISTS.priority_verticals || []).some((term) => boundaryKeywordHit(text, term));
  const horizontalHit = HORIZONTAL_AUDIENCE_KEYWORDS.some((keyword) => text.includes(keyword));
  if (verticalHit) return { dataWorkflowScore: 25, totalDelta: 3, kind: "vertical" };
  if (horizontalHit) return { dataWorkflowScore: 15, totalDelta: -7, kind: "horizontal" };
  return { dataWorkflowScore: 22, totalDelta: 0, kind: "neutral" };
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
  // Reveal the real personal email — this is the point of People Match and spends
  // one credit per matched contact. Phones stay off (we don't surface them).
  const response = await fetch(`${baseUrl}/people/bulk_match?reveal_personal_emails=true&reveal_phone_number=false`, {
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

// Email availability for a person record, mirroring the gtm-icp plugin's
// _email_status: a revealed record carries a real email (-> "verified" unless
// Apollo already labeled it); the search teaser only has has_email, surfaced as
// "available_unrevealed" so a slot reads honestly rather than looking verified.
function apolloEmailStatus(item, contact) {
  const email = item.email || contact.email || "";
  if (email && !email.includes("email_not_unlocked")) {
    return item.email_status || contact.email_status || "verified";
  }
  if (item.email_status || contact.email_status) return item.email_status || contact.email_status;
  if (item.has_email || contact.has_email) return "available_unrevealed";
  return "";
}

function compactApolloPeople(payload) {
  const rawItems = Array.isArray(payload.people) ? payload.people : Array.isArray(payload.contacts) ? payload.contacts : [];
  return rawItems.slice(0, 20).filter((item) => item && typeof item === "object").map((item) => {
    const org = item.organization && typeof item.organization === "object" ? item.organization : {};
    const contact = item.contact && typeof item.contact === "object" ? item.contact : {};
    const phone = Array.isArray(contact.phone_numbers) && contact.phone_numbers[0]?.sanitized_number
      ? contact.phone_numbers[0].sanitized_number
      : contact.sanitized_phone || item.sanitized_phone || "";
    let email = item.email || contact.email || "";
    // Apollo returns a locked "email_not_unlocked@domain" placeholder until a
    // reveal credit is spent — never surface it as a real address.
    if (email.includes("email_not_unlocked")) email = "";
    return {
      id: item.id || "",
      name: item.name || contact.name || "",
      title: item.title || contact.title || "",
      email,
      email_status: apolloEmailStatus(item, contact),
      revealed: Boolean(email),
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
    revealed: Boolean(person.email),
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

async function researchAnswer(env, run, question) {
  let fallbackReason = "";
  if (String(question || "").trim()) {
    const k2 = await k2ResearchAnswer(env, run, question);
    if (k2.status === "ok") return k2;
    fallbackReason = k2.reason || k2.status || "";
  }
  const local = localResearchAnswer(run, question);
  return fallbackReason ? { ...local, k2: { status: "fallback", reason: fallbackReason } } : local;
}

async function k2ResearchAnswer(env, run, question) {
  const corpusId = String(env.K2_RESEARCH_CORPUS_ID || run.k2?.corpus_id || "").trim();
  if (!env.K2_API_KEY || !corpusId) return { status: "skipped" };
  const baseUrl = String(env.K2_BASE_URL || "https://api.knowledge2.ai").replace(/\/+$/, "");
  try {
    const payload = await k2Request(baseUrl, env.K2_API_KEY, "POST", `/v1/corpora/${encodeURIComponent(corpusId)}/search:generate`, {
      query: question,
      top_k: 8,
      hybrid: {
        enabled: true,
        fusion_mode: "rrf",
        metadata_sparse_enabled: true,
        metadata_sparse_weight: 0.20,
      },
      return_config: {
        include_text: true,
        include_scores: true,
        include_provenance: true,
      },
      generation: {
        temperature: 0.2,
        max_tokens: 700,
      },
      filters: runMetadataFilter(String(run.id || "")),
    });
    return {
      status: "ok",
      answer: String(payload.answer || ""),
      citations: k2Citations(Array.isArray(payload.results) ? payload.results : []),
      matched_leads: [],
      provider: "k2",
      corpus_id: corpusId,
      model: payload.model,
      k2: {
        status: "ok",
        raw_result_count: Array.isArray(payload.results) ? payload.results.length : 0,
      },
    };
  } catch (error) {
    return { status: "error", reason: error?.message || String(error) };
  }
}

function runMetadataFilter(runId) {
  const filters = [];
  if (runId) filters.push({ key: "run_id", op: "==", value: runId });
  return { condition: "and", filters };
}

function k2Citations(results) {
  return results.slice(0, 8).map((item) => {
    const metadata = mergedK2Metadata(item);
    return {
      company: metadata.company || "",
      domain: metadata.domain || "",
      url: metadata.source_url || metadata.sourceUri || metadata.url || "",
      evidence_id: metadata.evidence_id || item.documentId || item.document_id || "",
      snippet: String(item.text || "").slice(0, 420),
      score: item.score,
      source_type: metadata.source_type || "",
      page_category: metadata.page_category || "",
      signal_tags: Array.isArray(metadata.signal_tags) ? metadata.signal_tags : [],
    };
  });
}

function mergedK2Metadata(item) {
  const merged = {};
  for (const key of ["metadata", "customMetadata", "custom_metadata", "systemMetadata", "system_metadata"]) {
    if (item[key] && typeof item[key] === "object" && !Array.isArray(item[key])) Object.assign(merged, item[key]);
  }
  const system = item.systemMetadata || item.system_metadata || {};
  const provenance = system.provenance && typeof system.provenance === "object" ? system.provenance : {};
  Object.assign(merged, Object.fromEntries(Object.entries(provenance).filter(([key]) => merged[key] === undefined)));
  return merged;
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

async function k2WorkspaceStatus(env) {
  const baseUrl = env.K2_BASE_URL || "https://api.knowledge2.ai";
  const projectName = String(env.K2_ICP_PROJECT_NAME || K2_WORKSPACE_PROJECT_DEFAULT);
  const status = {
    configured: Boolean(env.K2_API_KEY),
    source: "blueprint",
    base_url: baseUrl,
    project_name: projectName,
    project: { key: "project", name: projectName, id: "", status: "expected", description: "" },
    corpora: blueprintRows(K2_WORKSPACE_CORPORA),
    agents: blueprintRows(K2_WORKSPACE_AGENTS),
    feeds: blueprintRows(K2_WORKSPACE_FEEDS),
    pipeline_spec: blueprintRow({ key: "pipeline_spec", name: K2_WORKSPACE_PIPELINE_NAME, description: "K2-native ICP expansion graph." }),
    research_corpus_id: String(env.K2_RESEARCH_CORPUS_ID || ""),
    research_corpus_configured: Boolean(env.K2_RESEARCH_CORPUS_ID),
    warnings: [],
  };
  if (!env.K2_API_KEY) {
    status.warnings.push("K2_API_KEY is not configured; showing expected workspace blueprint.");
    return status;
  }

  try {
    const projectPayload = await k2Request(baseUrl, env.K2_API_KEY, "GET", "/v1/projects?limit=100&offset=0");
    const project = findByName(listFromPayload(projectPayload, "projects"), projectName);
    status.source = "k2_api";
    status.project = rowFromRecord({ key: "project", name: projectName, description: "" }, project);
    if (!project?.id) {
      status.warnings.push(`K2 project '${projectName}' was not found.`);
      return status;
    }
    const projectId = encodeURIComponent(project.id);
    const [corporaPayload, agentsPayload, feedsPayload, pipelinePayload] = await Promise.all([
      k2Request(baseUrl, env.K2_API_KEY, "GET", `/v1/corpora?project_id=${projectId}&limit=100&offset=0`),
      k2Request(baseUrl, env.K2_API_KEY, "GET", `/v1/agents?project_id=${projectId}&limit=100&offset=0`),
      k2Request(baseUrl, env.K2_API_KEY, "GET", `/v1/feeds?project_id=${projectId}&limit=100&offset=0`),
      k2Request(baseUrl, env.K2_API_KEY, "GET", `/v1/pipeline-specs?project_id=${projectId}&limit=100&offset=0`),
    ]);
    status.corpora = workspaceRows(K2_WORKSPACE_CORPORA, listFromPayload(corporaPayload, "corpora"));
    await attachWorkerCorpusHealth(status.corpora, baseUrl, env.K2_API_KEY);
    status.agents = workspaceRows(K2_WORKSPACE_AGENTS, listFromPayload(agentsPayload, "agents"), "status");
    status.feeds = workspaceRows(K2_WORKSPACE_FEEDS, listFromPayload(feedsPayload, "feeds"));
    status.pipeline_spec = rowFromRecord(
      { key: "pipeline_spec", name: K2_WORKSPACE_PIPELINE_NAME, description: "K2-native ICP expansion graph." },
      findByName(listFromPayload(pipelinePayload, "pipeline_specs", "pipelineSpecs"), K2_WORKSPACE_PIPELINE_NAME),
    );
    status.warnings.push(...workspaceMissingWarnings(status));
  } catch (error) {
    status.source = "error";
    status.warnings.push(`K2 API status lookup failed: ${error instanceof Error ? error.message : String(error)}`);
  }
  return status;
}

async function k2WorkspacePipelineAction(env, payload = {}) {
  const action = String(payload.action || "").trim().toLowerCase().replaceAll("-", "_");
  if (!["dry_run", "apply", "trigger", "backfill"].includes(action)) {
    return json({ error: "Unsupported K2 pipeline action. Use dry_run, apply, trigger, or backfill." }, 400);
  }
  if (!env.K2_API_KEY) {
    return json({ error: "K2_API_KEY is not configured; pipeline actions require live K2 credentials." }, 503);
  }

  const baseUrl = env.K2_BASE_URL || "https://api.knowledge2.ai";
  const projectName = String(env.K2_ICP_PROJECT_NAME || K2_WORKSPACE_PROJECT_DEFAULT);
  try {
    const { project, pipelineSpec } = await findWorkspacePipelineSpec(baseUrl, env.K2_API_KEY, projectName);
    if (!project?.id) return json({ error: `K2 project '${projectName}' was not found.` }, 404);
    if (!pipelineSpec?.id) return json({ error: `K2 pipeline spec '${K2_WORKSPACE_PIPELINE_NAME}' was not found.` }, 404);

    const pipelineSpecId = encodeURIComponent(pipelineSpec.id);
    let result = {};
    let backfillStartFrom = "";
    if (action === "dry_run") {
      const body = payload.sample_input && typeof payload.sample_input === "object" ? { sample_input: payload.sample_input } : undefined;
      result = await k2Request(baseUrl, env.K2_API_KEY, "POST", `/v1/pipeline-specs/${pipelineSpecId}/dry-run`, body);
    } else if (action === "apply") {
      result = await k2Request(baseUrl, env.K2_API_KEY, "POST", `/v1/pipeline-specs/${pipelineSpecId}/apply`, {
        activate_entities: payload.activate_entities !== false,
      });
    } else if (action === "trigger") {
      result = await k2Request(baseUrl, env.K2_API_KEY, "POST", `/v1/pipeline-specs/${pipelineSpecId}/trigger`);
    } else {
      backfillStartFrom = String(payload.start_from || defaultPipelineBackfillStartFrom());
      result = await k2Request(baseUrl, env.K2_API_KEY, "POST", `/v1/pipeline-specs/${pipelineSpecId}/backfill`, {
        start_from: backfillStartFrom,
      });
    }

    const response = {
      status: "ok",
      action,
      project: rowFromRecord({ key: "project", name: projectName, description: "" }, project),
      pipeline_spec: rowFromRecord(
        { key: "pipeline_spec", name: K2_WORKSPACE_PIPELINE_NAME, description: "K2-native ICP expansion graph." },
        pipelineSpec,
      ),
      result,
      workspace: await k2WorkspaceStatus(env),
    };
    if (backfillStartFrom) response.backfill_start_from = backfillStartFrom;
    return json(response);
  } catch (error) {
    return json({ error: error instanceof Error ? error.message : String(error) }, 502);
  }
}

async function findWorkspacePipelineSpec(baseUrl, apiKey, projectName) {
  const projectPayload = await k2Request(baseUrl, apiKey, "GET", "/v1/projects?limit=100&offset=0");
  const project = findByName(listFromPayload(projectPayload, "projects"), projectName);
  if (!project?.id) return { project, pipelineSpec: null };
  const pipelinePayload = await k2Request(
    baseUrl,
    apiKey,
    "GET",
    `/v1/pipeline-specs?project_id=${encodeURIComponent(project.id)}&limit=100&offset=0`,
  );
  return {
    project,
    pipelineSpec: findByName(listFromPayload(pipelinePayload, "pipeline_specs", "pipelineSpecs"), K2_WORKSPACE_PIPELINE_NAME),
  };
}

function defaultPipelineBackfillStartFrom() {
  return new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString();
}

function blueprintRows(blueprints) {
  return blueprints.map(blueprintRow);
}

function blueprintRow(blueprint) {
  return {
    key: blueprint.key || "",
    name: blueprint.name || "",
    id: "",
    status: "expected",
    description: blueprint.description || "",
    health: corpusHealth({ status: "not_configured" }),
  };
}

function workspaceRows(blueprints, records, statusKey) {
  return blueprints.map((blueprint) => rowFromRecord(blueprint, findByName(records, blueprint.name), statusKey));
}

async function attachWorkerCorpusHealth(rows, baseUrl, apiKey) {
  await Promise.all((rows || []).map(async (row) => {
    const corpusId = String(row.id || "");
    if (!corpusId || ["missing", "unknown"].includes(row.status)) {
      row.health = corpusHealth({ status: "missing" });
      return;
    }
    try {
      const metadata = await k2Request(baseUrl, apiKey, "GET", `/v1/corpora/${encodeURIComponent(corpusId)}/metadata/discover?include=top_values`);
      row.health = metadataHealth(metadata);
    } catch (error) {
      row.health = corpusHealth({
        status: "error",
        warning: error instanceof Error ? error.message : String(error),
      });
    }
  }));
}

function metadataHealth(metadata) {
  const fields = Array.isArray(metadata?.fields) ? metadata.fields : [];
  const totalDocuments = numberValue(metadata?.total_documents ?? metadata?.totalDocuments);
  const totalChunks = numberValue(metadata?.total_chunks ?? metadata?.totalChunks);
  const status = totalDocuments > 0 && fields.length ? "ready" : totalDocuments === 0 ? "empty" : "metadata_pending";
  return corpusHealth({
    status,
    total_documents: totalDocuments,
    total_chunks: totalChunks,
    field_count: fields.length,
    sample_fields: fields
      .slice(0, 8)
      .map((field) => String(field?.key || field?.name || ""))
      .filter(Boolean),
  });
}

function corpusHealth({
  status,
  total_documents = 0,
  total_chunks = 0,
  field_count = 0,
  sample_fields = [],
  warning = "",
}) {
  return { status, total_documents, total_chunks, field_count, sample_fields, warning };
}

function numberValue(value) {
  const number = Number(value || 0);
  return Number.isFinite(number) ? Math.trunc(number) : 0;
}

function rowFromRecord(blueprint, record, statusKey) {
  if (!record?.id) {
    return { ...blueprintRow(blueprint), status: "missing" };
  }
  return {
    key: blueprint.key || "",
    name: record.name || blueprint.name || "",
    id: record.id || "",
    status: statusKey ? String(record[statusKey] || "found") : "found",
    description: record.description || blueprint.description || "",
  };
}

function findByName(records, name) {
  return (records || []).find((record) => record?.name === name) || null;
}

function listFromPayload(payload, ...keys) {
  for (const key of keys) {
    if (Array.isArray(payload?.[key])) return payload[key];
  }
  return [];
}

function workspaceMissingWarnings(status) {
  const warnings = [];
  for (const [group, rows] of Object.entries({ corpora: status.corpora, agents: status.agents, feeds: status.feeds })) {
    for (const row of rows || []) {
      if (["missing", "unknown"].includes(row.status)) warnings.push(`Missing K2 ${group.slice(0, -1)}: ${row.name}`);
    }
  }
  if (["missing", "unknown"].includes(status.pipeline_spec?.status)) {
    warnings.push(`Missing K2 pipeline spec: ${status.pipeline_spec.name}`);
  }
  return warnings;
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
      "user-agent": "Knowledge2ICP/0.1",
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

async function createApiSessionResponse(request, env) {
  const expected = String(env.ICP_ADMIN_TOKEN || "").trim();
  if (!expected) return json({ error: "ICP_ADMIN_TOKEN is required for API access." }, 503);
  const payload = await readJson(request);
  const token = String(payload.token || bearerToken(request) || "").trim();
  if (!constantTimeEqual(token, expected)) return unauthorized("API token required.");
  const sessionToken = await createSessionToken(expected);
  const expiresAt = new Date((Math.floor(Date.now() / 1000) + API_SESSION_TTL_SECONDS) * 1000).toISOString();
  return json({
    session_token: sessionToken,
    expires_at: expiresAt,
    expires_in_seconds: API_SESSION_TTL_SECONDS,
  });
}

async function authorizeApiRequest(request, env) {
  const expected = String(env.ICP_ADMIN_TOKEN || "").trim();
  if (!expected) return { configured: false, authorized: false, mode: "missing" };
  const token = bearerToken(request);
  if (!token) return { configured: true, authorized: false, mode: "missing" };
  if (constantTimeEqual(token, expected)) return { configured: true, authorized: true, mode: "admin_token" };
  if (await verifySessionToken(expected, token)) return { configured: true, authorized: true, mode: "session" };
  return { configured: true, authorized: false, mode: "invalid" };
}

function isPublicReadRequest(method, url) {
  if (method !== "GET") return false;
  const path = url.pathname;
  if (path === "/api/state") return true;
  if (path === "/api/sources") return true;
  if (path === "/api/expansion/runs") return true;
  if (path === "/api/criteria/versions") return true;
  if (/^\/api\/runs\/[^/]+$/.test(path)) return true;
  if (/^\/api\/runs\/[^/]+\/workflow$/.test(path)) return true;
  if (/^\/api\/runs\/[^/]+\/prospects$/.test(path)) return true;
  if (/^\/api\/runs\/[^/]+\/accounts\/[^/]+$/.test(path)) return true;
  return false;
}

function bearerToken(request) {
  const authHeader = request.headers.get("authorization") || "";
  const [scheme, ...parts] = authHeader.split(" ");
  if (scheme.toLowerCase() !== "bearer") return "";
  return parts.join(" ").trim();
}

async function createSessionToken(secret) {
  const now = Math.floor(Date.now() / 1000);
  const payload = base64urlEncodeUtf8(JSON.stringify({
    exp: now + API_SESSION_TTL_SECONDS,
    iat: now,
    nonce: crypto.randomUUID(),
  }));
  const signature = await hmacSha256Base64Url(secret, payload);
  return `${payload}.${signature}`;
}

async function verifySessionToken(secret, token) {
  const [payload, signature, extra] = String(token || "").split(".");
  if (!payload || !signature || extra !== undefined) return false;
  const expected = await hmacSha256Base64Url(secret, payload);
  if (!constantTimeEqual(signature, expected)) return false;
  try {
    const decoded = JSON.parse(base64urlDecodeUtf8(payload));
    const exp = Number(decoded.exp || 0);
    return Number.isFinite(exp) && exp > Math.floor(Date.now() / 1000);
  } catch {
    return false;
  }
}

async function hmacSha256Base64Url(secret, message) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(message));
  return base64urlEncodeBytes(new Uint8Array(signature));
}

function base64urlEncodeUtf8(value) {
  return base64urlEncodeBytes(new TextEncoder().encode(value));
}

function base64urlEncodeBytes(bytes) {
  let binary = "";
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return encodeBase64(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function base64urlDecodeUtf8(value) {
  const binary = decodeBase64(value.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(value.length / 4) * 4, "="));
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

function encodeBase64(binary) {
  if (typeof btoa === "function") return btoa(binary);
  return Buffer.from(binary, "binary").toString("base64");
}

function decodeBase64(value) {
  if (typeof atob === "function") return atob(value);
  return Buffer.from(value, "base64").toString("binary");
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
