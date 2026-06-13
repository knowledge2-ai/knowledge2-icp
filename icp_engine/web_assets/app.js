const state = {
  currentRun: null,
  selectedLeadId: null,
  prospectFocusLeadId: null,
  currentManifest: null,
  currentProspects: null,
  prospectsRunId: null,
  currentAccountDetail: null,
  accountDetailRunId: null,
  accountDetailKey: null,
  accountDetailError: "",
  previewCandidates: [],
  prompts: [],
  settings: {},
  lists: {},
  sources: [],
  sourceScans: [],
  expansionRuns: [],
  sourceCoverage: {},
  qualityFeedbackSummary: {},
  evalSummary: {},
  workspaceState: {},
  currentK2WorkspaceStatus: null,
  currentK2PipelineAction: null,
  leadViews: [],
  selectedLeadIds: new Set(),
  leadPage: 1,
  leadPageSize: 50,
  leadSortField: "score",
  leadSortDirection: "desc",
  activeSourceScan: null,
  criteriaVersions: [],
  criteriaUndoStack: [],
  criteriaRedoStack: [],
  criteriaSuppressHistory: false,
  criteriaSavedHash: "",
};

const AUTH_SESSION_KEY = "knowledge2.icp.sessionToken";
const LEGACY_AUTH_TOKEN_KEY = "knowledge2.icp.adminToken";
const ALL_PROSPECTS = "__all__";

const $ = (id) => document.getElementById(id);

function resetRunDerivedState() {
  state.currentManifest = null;
  state.currentProspects = null;
  state.prospectsRunId = null;
  state.currentAccountDetail = null;
  state.accountDetailRunId = null;
  state.accountDetailKey = null;
  state.accountDetailError = "";
  state.selectedLeadIds.clear();
  state.leadPage = 1;
}

async function authFetch(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const token = localStorage.getItem(AUTH_SESSION_KEY) || "";
  if (token) headers.Authorization = `Bearer ${token}`;
  return fetch(path, {
    ...options,
    headers,
  });
}

async function api(path, options = {}) {
  const response = await authFetch(path, options);
  const payload = await response.json();
  if (response.status === 401) {
    setAuthStatus("Admin session required or expired. Enter the admin token and save a new session.");
  }
  if (!response.ok) throw new Error(payload.error || `Request failed: ${response.status}`);
  return payload;
}

async function loadState() {
  const payload = await api("/api/state");
  state.currentRun = payload.latest_run;
  renderProviders(payload.provider_status || {});
  state.criteriaVersions = payload.criteria_versions || [];
  renderCriteria(payload.criteria || {}, state.criteriaVersions);
  state.prompts = payload.prompts || [];
  state.settings = payload.settings || {};
  state.lists = payload.lists || {};
  state.sources = payload.sources || [];
  state.sourceScans = payload.source_scans || [];
  state.expansionRuns = payload.expansion_runs || [];
  state.sourceCoverage = payload.source_coverage || {};
  state.qualityFeedbackSummary = payload.quality_feedback_summary || {};
  state.evalSummary = payload.eval_summary || {};
  state.workspaceState = payload.workspace_state || {};
  state.leadViews = payload.lead_views || [];
  applySeededDefaults();
  renderSeedSummary();
  renderSetup();
  renderSources();
  renderRuns(payload.runs || []);
  renderRun(state.currentRun);
}

function initAuthControls() {
  const tokenInput = $("admin-token");
  const savedSession = localStorage.getItem(AUTH_SESSION_KEY) || "";
  const legacyToken = localStorage.getItem(LEGACY_AUTH_TOKEN_KEY) || "";
  tokenInput.value = savedSession ? "" : legacyToken;
  if (savedSession) {
    setAuthStatus("Admin session saved in this browser.");
  } else if (legacyToken) {
    setAuthStatus("Legacy token found. Save session to convert it.");
  } else {
    setAuthStatus("No admin session saved.");
  }
}

async function saveAuthToken() {
  const value = $("admin-token").value.trim();
  if (value) {
    setAuthStatus("Creating admin session...");
    const response = await fetch("/api/auth/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: value }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || `Session failed: ${response.status}`);
    localStorage.setItem(AUTH_SESSION_KEY, payload.session_token);
    localStorage.removeItem(LEGACY_AUTH_TOKEN_KEY);
    $("admin-token").value = "";
    setAuthStatus(`Admin session active until ${formatVersionDate(payload.expires_at)}.`);
    await loadState();
  } else {
    clearAuthToken();
  }
}

function clearAuthToken() {
  localStorage.removeItem(AUTH_SESSION_KEY);
  localStorage.removeItem(LEGACY_AUTH_TOKEN_KEY);
  $("admin-token").value = "";
  setAuthStatus("No admin session saved.");
}

function setAuthStatus(message) {
  const status = $("auth-status");
  if (status) status.textContent = message;
}

function renderProviders(providers) {
  const root = $("providers");
  root.innerHTML = Object.entries(providers)
    .map(([name, value]) => {
      const ok = value.configured || value.public_fallback;
      return `<div class="provider">
        <strong>${escapeHtml(name)}</strong>
        <span class="status-pill ${ok ? "ok" : "warn"}">${ok ? "ready" : "missing"}</span>
      </div>`;
    })
    .join("");
}

function applySeededDefaults() {
  if (!$("query").value && state.settings.default_query) {
    $("query").value = state.settings.default_query;
  }
  if (state.settings.max_companies && ["6", "50"].includes($("max-companies").value)) {
    $("max-companies").value = state.settings.max_companies;
  }
  if (state.settings.max_pages && $("max-pages").value === "6") {
    $("max-pages").value = state.settings.max_pages;
  }
  if (typeof state.settings.fetch_website_evidence === "boolean") {
    $("fetch").checked = state.settings.fetch_website_evidence;
  }
  if (typeof state.settings.include_github_metadata === "boolean") {
    $("github").checked = state.settings.include_github_metadata;
  }
  if (typeof state.settings.use_apollo_enrichment === "boolean") {
    $("apollo").checked = state.settings.use_apollo_enrichment;
  }
}

function renderSeedSummary() {
  const root = $("seed-summary");
  if (!root) return;
  const accountCount = state.lists.account_universe?.length || 0;
  const verticalCount = state.lists.priority_verticals?.length || 0;
  root.innerHTML = `<div class="seed-summary">
    ${metric("Prompts", state.prompts.length)}
    ${metric("Accounts", accountCount)}
    ${metric("Verticals", verticalCount)}
    ${metric("Mode", state.settings.deployment_mode || "local")}
  </div>`;
}

function renderSetup() {
  const root = $("setup-grid");
  if (!root) return;
  const accounts = state.lists.account_universe || [];
  const verticals = state.lists.priority_verticals || [];
  root.innerHTML = `
    <section class="setup-section">
      <h3>Prompts</h3>
      <div class="prompt-list">
        ${state.prompts.map((prompt) => `<article class="prompt-item">
          <span class="status-pill">${escapeHtml(prompt.kind || "prompt")}</span>
          <strong>${escapeHtml(prompt.label || prompt.id || "")}</strong>
          <p>${escapeHtml(prompt.text || "")}</p>
        </article>`).join("") || "<p class=\"muted\">No seeded prompts.</p>"}
      </div>
    </section>
    <section class="setup-section">
      <h3>Settings</h3>
      ${settingsEditorMarkup()}
    </section>
    <section class="setup-section">
      <div class="section-minihead">
        <h3>Workspace State</h3>
        <button id="refresh-workspace-state" type="button" class="secondary">Refresh</button>
      </div>
      ${workspaceStateMarkup(state.workspaceState)}
    </section>
    <section class="setup-section">
      <h3>Account List</h3>
      <div class="account-list">
        ${accounts.map((item) => `<article class="account-item">
          <strong>${escapeHtml(item.company || "")}</strong>
          <span>${escapeHtml(item.domain || "")}</span>
          <small>${escapeHtml(item.category || "")} · ${escapeHtml(item.hq || "")}</small>
          <p>${escapeHtml(item.notes || "")}</p>
        </article>`).join("") || "<p class=\"muted\">No seeded accounts.</p>"}
      </div>
    </section>
    <section class="setup-section">
      <h3>Priority Verticals</h3>
      <div class="tag-list">${verticals.map((item) => `<span class="tag">${escapeHtml(item)}</span>`).join("")}</div>
    </section>`;
  bindSettingsControls();
  $("refresh-workspace-state")?.addEventListener("click", refreshWorkspaceState);
}

function workspaceStateMarkup(workspaceState = {}) {
  const collections = workspaceState.collections || [];
  return `<div id="workspace-state-panel" class="workspace-state-panel">
    <div class="kv-grid compact">
      ${kv("Store", workspaceState.store || "unknown")}
      ${kv("Durable", workspaceState.durable ? "yes" : "no")}
    </div>
    ${(workspaceState.warnings || []).length ? `<div class="eval-checks">${workspaceState.warnings.map((warning) => `<span class="status-pill warn-tag">${escapeHtml(warning)}</span>`).join("")}</div>` : ""}
    <div class="workspace-state-list">
      ${collections.map((item) => `<div class="workspace-state-row">
        <strong>${escapeHtml(item.key || "")}</strong>
        <span class="status-pill ${item.persisted ? "ok-tag" : "warn-tag"}">${item.persisted ? "persisted" : "seed/runtime"}</span>
        <code>${escapeHtml(item.count ?? 0)}</code>
      </div>`).join("") || "<p class=\"muted\">No workspace state collections reported.</p>"}
    </div>
  </div>`;
}

async function refreshWorkspaceState() {
  state.workspaceState = await api("/api/workspace-state");
  renderSetup();
}

function settingsEditorMarkup() {
  const settings = state.settings || {};
  const limits = settings.provider_limits || {};
  return `<form id="settings-form" class="settings-editor">
    <label>
      Default query
      <textarea id="settings-default-query" rows="3">${escapeHtml(settings.default_query || "")}</textarea>
    </label>
    <div class="inline-grid">
      ${settingsNumberInput("settings-max-companies", "Max companies", settings.max_companies || 50, 1, 1000)}
      ${settingsNumberInput("settings-max-pages", "Max pages", settings.max_pages || 6, 0, 100)}
      ${settingsNumberInput("settings-tier-a", "Tier A", settings.tier_a_threshold || 75, 0, 100)}
      ${settingsNumberInput("settings-tier-b", "Tier B", settings.tier_b_threshold || 60, 0, 100)}
    </div>
    <label>
      Employee range
      <input id="settings-employee-range" value="${escapeAttribute(settings.employee_range || "")}" />
    </label>
    <div class="settings-toggle-grid">
      ${settingsCheckbox("settings-fetch", "Fetch evidence", settings.fetch_website_evidence)}
      ${settingsCheckbox("settings-github", "GitHub metadata", settings.include_github_metadata)}
      ${settingsCheckbox("settings-apollo", "Apollo enrichment", settings.use_apollo_enrichment)}
      ${settingsCheckbox("settings-serp", "SERP discovery", settings.use_serp_discovery)}
      ${settingsCheckbox("settings-provider-limits", "Provider limits", limits.enabled !== false)}
    </div>
    <div class="settings-limit-grid">
      ${settingsLimitInput("daily", "search", "Daily search")}
      ${settingsLimitInput("daily", "source_scan", "Daily scans")}
      ${settingsLimitInput("daily", "run", "Daily runs")}
      ${settingsLimitInput("daily", "apollo_enrichment", "Daily Apollo")}
      ${settingsLimitInput("daily", "research", "Daily research")}
      ${settingsLimitInput("rate_per_minute", "search", "Search/min")}
      ${settingsLimitInput("rate_per_minute", "run", "Runs/min")}
      ${settingsLimitInput("rate_per_minute", "research", "Research/min")}
      ${settingsLimitInput("per_run", "max_companies", "Run companies")}
      ${settingsLimitInput("per_run", "max_pages", "Run pages")}
    </div>
    <div class="settings-meta">
      ${kv("Deployment mode", settings.deployment_mode || "local")}
    </div>
    <div class="button-row">
      <button id="settings-save" type="submit">Save settings</button>
      <button id="settings-apply-discover" type="button" class="secondary">Apply to Discover</button>
    </div>
    <p id="settings-status" class="muted"></p>
  </form>`;
}

function settingsNumberInput(id, label, value, min, max) {
  return `<label>
    ${escapeHtml(label)}
    <input id="${escapeAttribute(id)}" type="number" min="${escapeAttribute(min)}" max="${escapeAttribute(max)}" value="${escapeAttribute(value)}" />
  </label>`;
}

function settingsCheckbox(id, label, checked) {
  return `<label class="check-row">
    <input id="${escapeAttribute(id)}" type="checkbox"${checked ? " checked" : ""} />
    ${escapeHtml(label)}
  </label>`;
}

function settingsLimitInput(group, key, label) {
  const value = state.settings?.provider_limits?.[group]?.[key] ?? 0;
  return settingsNumberInput(`settings-limit-${group}-${key}`, label, value, 0, 100000);
}

function bindSettingsControls() {
  const form = $("settings-form");
  if (!form) return;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    await saveSettings();
  });
  $("settings-apply-discover").addEventListener("click", applySettingsToDiscovery);
}

async function saveSettings() {
  const button = $("settings-save");
  button.disabled = true;
  $("settings-status").textContent = "Saving settings...";
  try {
    const payload = await api("/api/settings", {
      method: "POST",
      body: JSON.stringify(settingsPayloadFromForm()),
    });
    state.settings = payload.settings || state.settings;
    renderSeedSummary();
    renderSetup();
    $("settings-status").textContent = "Settings saved.";
  } catch (error) {
    $("settings-status").textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

function settingsPayloadFromForm() {
  const daily = {};
  const ratePerMinute = {};
  const perRun = {};
  for (const key of ["search", "source_scan", "run", "apollo_enrichment", "research"]) {
    daily[key] = Number($(`settings-limit-daily-${key}`).value || 0);
  }
  for (const key of ["search", "run", "research"]) {
    ratePerMinute[key] = Number($(`settings-limit-rate_per_minute-${key}`).value || 0);
  }
  for (const key of ["max_companies", "max_pages"]) {
    perRun[key] = Number($(`settings-limit-per_run-${key}`).value || 0);
  }
  return {
    default_query: $("settings-default-query").value,
    max_companies: Number($("settings-max-companies").value || 50),
    max_pages: Number($("settings-max-pages").value || 6),
    tier_a_threshold: Number($("settings-tier-a").value || 75),
    tier_b_threshold: Number($("settings-tier-b").value || 60),
    employee_range: $("settings-employee-range").value,
    fetch_website_evidence: $("settings-fetch").checked,
    include_github_metadata: $("settings-github").checked,
    use_apollo_enrichment: $("settings-apollo").checked,
    use_serp_discovery: $("settings-serp").checked,
    provider_limits: {
      enabled: $("settings-provider-limits").checked,
      daily,
      rate_per_minute: ratePerMinute,
      per_run: perRun,
    },
  };
}

function applySettingsToDiscovery() {
  const payload = settingsPayloadFromForm();
  $("query").value = payload.default_query || "";
  $("max-companies").value = payload.max_companies;
  $("max-pages").value = payload.max_pages;
  $("fetch").checked = payload.fetch_website_evidence;
  $("github").checked = payload.include_github_metadata;
  $("apollo").checked = payload.use_apollo_enrichment;
  $("settings-status").textContent = "Applied to Discover.";
  clearCandidatePreview();
}

function renderSources() {
  renderSourceCoverage();
  renderExpansionPanel();
  renderSourceList();
  renderSourceScanDetail(state.activeSourceScan);
}

function renderSourceCoverage() {
  const root = $("source-coverage");
  if (!root) return;
  const coverage = state.sourceCoverage || {};
  root.innerHTML = `<div class="summary-strip source-summary">
    ${metric("Sources", coverage.source_count || state.sources.length || 0)}
    ${metric("Enabled", coverage.enabled_count || 0)}
    ${metric("Scans", coverage.scan_count || 0)}
    ${metric("Unique domains", coverage.unique_candidate_domains || 0)}
  </div>`;
}

function renderExpansionPanel() {
  const root = $("expansion-panel");
  if (!root) return;
  const coverage = state.sourceCoverage || {};
  const latest = coverage.latest_expansion_run || state.expansionRuns?.[state.expansionRuns.length - 1] || null;
  root.innerHTML = `<div class="expansion-header">
      <div>
        <p class="eyebrow">Expansion Loop</p>
        <h3>Scheduled Source Sweeps</h3>
      </div>
      <button id="run-expansion" type="button" class="secondary">Run due sources</button>
    </div>
    <div class="summary-strip source-summary">
      ${metric("Due sources", coverage.due_source_count || 0)}
      ${metric("Last candidates", latest?.candidate_count || 0)}
      ${metric("Last status", latest?.status || "not_run")}
    </div>
    <div class="expansion-history">
      ${(state.expansionRuns || []).slice(-5).reverse().map((run) => `<div class="expansion-run">
        <strong>${escapeHtml(run.trigger || "expansion")}</strong>
        <span>${escapeHtml(run.status || "")} · ${escapeHtml(run.candidate_count || 0)} candidates · ${escapeHtml(run.created_at || "")}</span>
      </div>`).join("") || "<p class=\"muted\">No expansion runs yet.</p>"}
    </div>`;
  $("run-expansion")?.addEventListener("click", () => runExpansion().catch((error) => {
    $("source-status").textContent = error.message;
  }));
}

function renderSourceList() {
  const root = $("source-list");
  if (!root) return;
  if (!state.sources.length) {
    root.innerHTML = `<div class="detail-panel empty">No saved discovery sources.</div>`;
    return;
  }
  root.innerHTML = state.sources
    .map((source) => `<article class="source-item" data-source-id="${escapeAttribute(source.id)}">
      <div>
        <span class="status-pill">${escapeHtml(source.type || "source")}</span>
        <strong>${escapeHtml(source.name || "")}</strong>
        <p>${escapeHtml(source.value || "")}</p>
        <small>${escapeHtml(source.source_group || "")} · ${escapeHtml(source.schedule || "manual")} · ${escapeHtml(source.last_status || "never_scanned")}</small>
      </div>
      <div class="source-item-actions">
        <span><strong>${escapeHtml(source.last_candidate_count || 0)}</strong><small>last candidates</small></span>
        <button type="button" class="secondary" data-scan-source="${escapeAttribute(source.id)}">Scan</button>
      </div>
    </article>`)
    .join("");
  root.querySelectorAll("[data-scan-source]").forEach((button) => {
    button.addEventListener("click", () => scanSource(button.dataset.scanSource || ""));
  });
}

function renderSourceScanDetail(scan) {
  const root = $("source-scan-detail");
  if (!root) return;
  if (!scan) {
    root.className = "detail-panel source-scan-detail empty";
    root.textContent = "Scan a source to review candidate companies.";
    return;
  }
  const candidates = scan.candidates || [];
  root.className = "detail-panel source-scan-detail";
  root.innerHTML = `<div class="detail-stack">
    <div class="detail-section">
      <p class="eyebrow">${escapeHtml(scan.source_type || "source scan")}</p>
      <h2>${escapeHtml(scan.source_name || "Source scan")}</h2>
      <div class="kv-grid">
        ${kv("Status", scan.status || "")}
        ${kv("Candidates", candidates.length)}
        ${kv("Warnings", (scan.warnings || []).length)}
        ${kv("Scanned", scan.scanned_at || "")}
      </div>
      <div class="button-row">
        <button id="use-source-candidates" type="button">Use candidates in run</button>
        <button id="copy-source-query" type="button" class="secondary">Copy source to Discover</button>
      </div>
    </div>
    <div class="detail-section">
      <h2>Candidate Preview</h2>
      <div class="source-candidate-list">
        ${candidates.slice(0, 25).map((item) => `<article class="source-candidate">
          <strong>${escapeHtml(item.company || "")}</strong>
          <span>${escapeHtml(item.domain || "")}</span>
          <p>${escapeHtml(item.notes || item.source_title || "")}</p>
        </article>`).join("") || "<p>No candidates returned.</p>"}
      </div>
    </div>
    ${(scan.warnings || []).length ? `<div class="detail-section"><h2>Warnings</h2>${scan.warnings.map((item) => `<p>${escapeHtml(item)}</p>`).join("")}</div>` : ""}
  </div>`;
  $("use-source-candidates")?.addEventListener("click", () => {
    state.previewCandidates = candidates;
    renderCandidatePreview();
    $("run-status").textContent = `Loaded ${candidates.length} source candidates into preview.`;
    activateView("leads");
  });
  $("copy-source-query")?.addEventListener("click", () => {
    const source = state.sources.find((item) => item.id === scan.source_id) || {};
    if (["manual_seed", "csv_upload"].includes(source.type)) {
      $("seed-text").value = source.value || "";
    } else {
      $("query").value = source.value || "";
    }
    activateView("leads");
  });
}

async function scanSource(sourceId) {
  if (!sourceId) return;
  const button = document.querySelector(`[data-scan-source="${CSS.escape(sourceId)}"]`);
  if (button) button.textContent = "Scanning...";
  $("source-status").textContent = "Scanning source with the configured discovery provider...";
  try {
    const payload = await api(`/api/sources/${encodeURIComponent(sourceId)}/scan`, {
      method: "POST",
      body: JSON.stringify({ max_companies: Number($("max-companies").value || 25) }),
    });
    state.sources = state.sources.map((source) => (source.id === sourceId ? payload.source : source));
    state.sourceCoverage = payload.coverage || state.sourceCoverage;
    state.activeSourceScan = payload.scan || null;
    state.sourceScans = [...state.sourceScans.filter((scan) => scan.id !== payload.scan?.id), payload.scan].filter(Boolean);
    renderSources();
    $("source-status").textContent = `Scan returned ${(payload.candidates || []).length} candidates.`;
  } catch (error) {
    $("source-status").textContent = error.message;
  } finally {
    if (button) button.textContent = "Scan";
  }
}

async function loadSourceCsvFile(event) {
  const file = event.currentTarget.files?.[0];
  if (!file) return;
  if (file.size > 1_000_000) {
    $("source-status").textContent = "CSV file is too large. Keep uploads under 1 MB.";
    event.currentTarget.value = "";
    return;
  }
  const text = await file.text();
  $("source-type").value = "csv_upload";
  if (!$("source-name").value.trim()) {
    $("source-name").value = file.name.replace(/\.[^.]+$/, "").replace(/[-_]+/g, " ");
  }
  $("source-value").value = text.trim();
  $("source-status").textContent = `Loaded ${text.split(/\r?\n/).filter((line) => line.trim()).length} CSV rows. Save then scan this source.`;
}

async function runExpansion() {
  $("source-status").textContent = "Running due scheduled sources...";
  const payload = await api("/api/expansion/run", {
    method: "POST",
    body: JSON.stringify({
      due_only: true,
      max_companies: Number($("max-companies").value || 25),
    }),
  });
  state.sources = payload.sources || state.sources;
  state.sourceScans = payload.scans || state.sourceScans;
  state.expansionRuns = payload.expansion_runs || state.expansionRuns;
  state.sourceCoverage = payload.coverage || state.sourceCoverage;
  state.activeSourceScan = (payload.scans || []).slice(-1)[0] || state.activeSourceScan;
  renderSources();
  $("source-status").textContent = `Expansion ${payload.run?.status || "completed"}: ${payload.run?.candidate_count || 0} candidates from ${payload.run?.scanned_source_count || 0} sources.`;
}

function runOptionsPayload() {
  return {
    query: $("query").value,
    seed_text: $("seed-text").value,
    max_companies: Number($("max-companies").value || 6),
    max_pages: Number($("max-pages").value || 6),
    fetch: $("fetch").checked,
    include_github: $("github").checked,
    use_apollo: $("apollo").checked,
  };
}

function selectedPreviewCandidates() {
  if (!state.previewCandidates.length) return [];
  const selected = new Set(
    Array.from(document.querySelectorAll("[data-candidate-index]:checked")).map((item) => Number(item.dataset.candidateIndex)),
  );
  return state.previewCandidates.filter((_, index) => selected.has(index));
}

function renderCandidatePreview(candidates = state.previewCandidates, warnings = []) {
  const root = $("candidate-panel");
  if (!root) return;
  if (!candidates.length && !warnings.length) {
    root.innerHTML = "";
    return;
  }
  const rows = candidates
    .map((candidate, index) => {
      const refs = [
        ...(candidate.linkedin_urls || []),
        ...(candidate.github_urls || []),
        ...(candidate.other_urls || []),
      ];
      return `<label class="candidate-row">
        <input type="checkbox" data-candidate-index="${index}" checked />
        <span>
          <strong>${escapeHtml(candidate.company || "")}</strong>
          <small>${escapeHtml(candidate.domain || "")}</small>
          ${candidate.source_title ? `<small>${escapeHtml(candidate.source_title)}</small>` : ""}
          ${refs.length ? `<small>${refs.length} public refs</small>` : ""}
        </span>
      </label>`;
    })
    .join("");
  root.innerHTML = `<div class="candidate-actions">
      <strong>${candidates.length} candidate${candidates.length === 1 ? "" : "s"}</strong>
      <button id="select-all-candidates" type="button" class="secondary">All</button>
      <button id="clear-candidates" type="button" class="secondary">None</button>
    </div>
    ${warnings.map((item) => `<p class="muted">${escapeHtml(item)}</p>`).join("")}
    <div class="candidate-list">${rows || "<p class=\"muted\">No candidates discovered.</p>"}</div>`;
  $("select-all-candidates")?.addEventListener("click", () => {
    document.querySelectorAll("[data-candidate-index]").forEach((item) => {
      item.checked = true;
    });
  });
  $("clear-candidates")?.addEventListener("click", () => {
    document.querySelectorAll("[data-candidate-index]").forEach((item) => {
      item.checked = false;
    });
  });
}

function clearCandidatePreview() {
  if (!state.previewCandidates.length) return;
  state.previewCandidates = [];
  renderCandidatePreview();
  $("run-status").textContent = "Candidate preview cleared after search inputs changed.";
}

function renderCriteria(criteria, versions = state.criteriaVersions, lint = null) {
  state.criteriaVersions = Array.isArray(versions) ? versions : [];
  state.criteriaSavedHash = criteria.hash || "";
  state.criteriaUndoStack = [];
  state.criteriaRedoStack = [];
  setCriteriaMarkdown(criteria.markdown || "", { capture: false, renderLint: false });
  renderCriteriaVersions(criteria.hash || "");
  renderCriteriaLint(lint || lintCriteriaMarkdown(criteria.markdown || ""));
  renderCriteriaImpact(null);
  $("criteria-status").textContent = criteria.source
    ? `Loaded from ${criteria.source}; active hash ${criteria.hash || "unknown"}`
    : "";
  updateCriteriaEditorControls();
}

function criteriaInput() {
  return $("criteria-markdown");
}

function setCriteriaMarkdown(value, options = {}) {
  const input = criteriaInput();
  if (!input) return;
  const capture = options.capture !== false;
  const renderLint = options.renderLint !== false;
  if (capture && !state.criteriaSuppressHistory && input.value !== value) {
    pushCriteriaUndo(input.value);
    state.criteriaRedoStack = [];
  }
  state.criteriaSuppressHistory = true;
  input.value = value;
  state.criteriaSuppressHistory = false;
  if (renderLint) renderCriteriaLint(lintCriteriaMarkdown(input.value));
  updateCriteriaEditorControls();
}

function pushCriteriaUndo(value) {
  const stack = state.criteriaUndoStack;
  if (!stack.length || stack[stack.length - 1] !== value) {
    stack.push(value);
  }
  if (stack.length > 100) stack.shift();
}

function undoCriteriaEdit() {
  const input = criteriaInput();
  if (!input || !state.criteriaUndoStack.length) return;
  const previous = state.criteriaUndoStack.pop();
  state.criteriaRedoStack.push(input.value);
  setCriteriaMarkdown(previous, { capture: false });
  $("criteria-status").textContent = "Moved back one edit.";
}

function redoCriteriaEdit() {
  const input = criteriaInput();
  if (!input || !state.criteriaRedoStack.length) return;
  const next = state.criteriaRedoStack.pop();
  pushCriteriaUndo(input.value);
  setCriteriaMarkdown(next, { capture: false });
  $("criteria-status").textContent = "Moved forward one edit.";
}

function renderCriteriaVersions(selectedHash = "") {
  const select = $("criteria-version-select");
  if (!select) return;
  const versions = state.criteriaVersions || [];
  select.innerHTML = versions.length
    ? versions.map((version, index) => `<option value="${escapeAttribute(version.hash || version.id || "")}">
        ${escapeHtml(criteriaVersionLabel(version, index))}
      </option>`).join("")
    : "<option value=\"\">No saved versions</option>";
  const hash = selectedHash || state.criteriaSavedHash || versions[versions.length - 1]?.hash || "";
  if (hash && Array.from(select.options).some((option) => option.value === hash)) {
    select.value = hash;
  } else if (versions.length) {
    select.selectedIndex = versions.length - 1;
  }
  updateCriteriaEditorControls();
}

function selectedCriteriaVersion() {
  const select = $("criteria-version-select");
  if (!select) return null;
  const id = select.value;
  return (state.criteriaVersions || []).find((version) => version.hash === id || version.id === id) || null;
}

function loadSelectedCriteriaVersion(offset = 0) {
  const select = $("criteria-version-select");
  if (!select || !select.options.length || select.value === "") return;
  if (offset) {
    const nextIndex = Math.max(0, Math.min(select.options.length - 1, select.selectedIndex + offset));
    select.selectedIndex = nextIndex;
  }
  const version = selectedCriteriaVersion();
  if (!version) return;
  setCriteriaMarkdown(version.markdown || "", { capture: true });
  const active = version.hash === state.criteriaSavedHash ? "active" : "preview";
  $("criteria-status").textContent = `Loaded ${active} version ${shortHash(version.hash || version.id)} from ${formatVersionDate(version.updated_at)}.`;
  updateCriteriaEditorControls();
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
  lines.forEach((line, index) => {
    const lineNumber = index + 1;
    const trimmed = line.trim();
    if (trimmed.startsWith("```")) inFence = !inFence;
    if (inFence) return;
    if (line.replace(/\s+$/g, "") !== line) diagnostics.push(criteriaDiagnostic("warning", lineNumber, "trailing-whitespace", "Remove trailing whitespace."));
    if (line.includes("\t")) diagnostics.push(criteriaDiagnostic("warning", lineNumber, "tab-indentation", "Use spaces instead of tabs."));
    if (/^[*+]\s+/.test(trimmed)) diagnostics.push(criteriaDiagnostic("info", lineNumber, "bullet-style", "Use '-' for markdown bullets."));
    const heading = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      const level = heading[1].length;
      headings.push({ line: lineNumber, level });
      if (level === 1) h1Count += 1;
    }
  });
  if (text.trim() && !lines.some((line) => line.startsWith("# "))) {
    diagnostics.push(criteriaDiagnostic("warning", 1, "missing-h1", "Add a top-level '# ...' heading."));
  }
  if (h1Count > 1) diagnostics.push(criteriaDiagnostic("warning", 1, "multiple-h1", "Use one top-level H1 heading."));
  let previousLevel = 0;
  headings.forEach((heading) => {
    if (previousLevel && heading.level > previousLevel + 1) {
      diagnostics.push(criteriaDiagnostic("warning", heading.line, "heading-jump", "Do not skip heading levels."));
    }
    previousLevel = heading.level;
  });
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

function renderCriteriaLint(lint) {
  const panel = $("criteria-lint-panel");
  if (!panel) return;
  const diagnostics = lint?.diagnostics || [];
  const summary = `${lint?.error_count || 0} errors · ${lint?.warning_count || 0} warnings · ${lint?.info_count || 0} notes`;
  panel.innerHTML = `<div class="criteria-lint-summary">
      <strong>${escapeHtml(summary)}</strong>
      <span>${lint?.changed ? "Formatting changes available" : "Formatting is clean"}</span>
    </div>
    <div class="criteria-lint-list">
      ${diagnostics.length
        ? diagnostics.map((item) => `<div class="criteria-lint-item ${escapeAttribute(item.severity)}">
            <span>${escapeHtml(item.severity)}</span>
            <p><strong>Line ${escapeHtml(item.line)} · ${escapeHtml(item.rule)}</strong>${escapeHtml(item.message)}</p>
          </div>`).join("")
        : "<div class=\"criteria-lint-item ok\"><span>ok</span><p><strong>No lint issues</strong>The criteria markdown passes the current checks.</p></div>"}
    </div>`;
  updateCriteriaMeta(lint);
}

function renderCriteriaImpact(impact) {
  const panel = $("criteria-impact-panel");
  if (!panel) return;
  if (!impact) {
    panel.innerHTML = "";
    return;
  }
  const tiers = ["A", "B", "C", "Reject"];
  const countCards = tiers.map((tier) => {
    const current = impact.current_counts?.[tier] || 0;
    const proposed = impact.proposed_counts?.[tier] || 0;
    const delta = impact.deltas?.[tier] || 0;
    const deltaText = delta > 0 ? `+${delta}` : String(delta);
    return `<div class="impact-card">
      <span>Tier ${escapeHtml(tier)}</span>
      <strong>${escapeHtml(current)} -> ${escapeHtml(proposed)}</strong>
      <small class="${delta === 0 ? "" : delta > 0 ? "positive" : "negative"}">${escapeHtml(deltaText)}</small>
    </div>`;
  }).join("");
  const changes = (impact.changes || []).slice(0, 12);
  panel.innerHTML = `<div class="criteria-impact-summary">
      ${countCards}
      <div class="impact-card">
        <span>Changed</span>
        <strong>${escapeHtml(impact.changed_count || 0)}</strong>
        <small>${escapeHtml(impact.lead_count || 0)} leads</small>
      </div>
    </div>
    ${(impact.warnings || []).length ? `<div class="criteria-impact-warnings">${impact.warnings.map((item) => `<span class="tag warn">${escapeHtml(item)}</span>`).join("")}</div>` : ""}
    <div class="criteria-impact-list">
      ${changes.length
        ? changes.map((item) => `<div class="criteria-impact-row">
            <strong>${escapeHtml(item.company || item.domain || "Lead")}</strong>
            <span>${escapeHtml(item.current_tier)} -> ${escapeHtml(item.proposed_tier)}</span>
            <span>${escapeHtml(item.current_score)} -> ${escapeHtml(item.proposed_score)} (${escapeHtml(item.score_delta > 0 ? `+${item.score_delta}` : item.score_delta)})</span>
            <p>${escapeHtml(item.reason || "")}</p>
          </div>`).join("")
        : "<p class=\"muted\">No tier or score changes for the active run.</p>"}
    </div>`;
}

async function previewCriteriaImpact() {
  if (!state.currentRun?.id) {
    $("criteria-status").textContent = "Run research before previewing criteria impact.";
    return;
  }
  $("criteria-status").textContent = "Calculating criteria impact...";
  try {
    const payload = await api("/api/criteria/impact", {
      method: "POST",
      body: JSON.stringify({
        run_id: state.currentRun.id,
        markdown: $("criteria-markdown").value,
      }),
    });
    renderCriteriaImpact(payload);
    $("criteria-status").textContent = `Impact preview: ${payload.changed_count || 0} changed leads across ${payload.lead_count || 0}.`;
  } catch (error) {
    $("criteria-status").textContent = error.message;
  }
}

function updateCriteriaMeta(lint = lintCriteriaMarkdown(criteriaInput()?.value || "")) {
  const input = criteriaInput();
  const meta = $("criteria-editor-meta");
  if (!input || !meta) return;
  const lineCount = input.value ? input.value.split(/\n/).length : 0;
  const wordCount = (input.value.trim().match(/\S+/g) || []).length;
  const selected = selectedCriteriaVersion();
  const versionText = selected ? `selected ${shortHash(selected.hash || selected.id)}` : "no saved version";
  meta.textContent = `${lineCount} lines · ${wordCount} words · ${lint.error_count || 0} errors · ${lint.warning_count || 0} warnings · active ${shortHash(state.criteriaSavedHash)} · ${versionText}`;
}

function updateCriteriaEditorControls() {
  const input = criteriaInput();
  const select = $("criteria-version-select");
  const selectedIndex = select ? select.selectedIndex : -1;
  const versionCount = select?.options.length || 0;
  if ($("criteria-undo")) $("criteria-undo").disabled = !state.criteriaUndoStack.length;
  if ($("criteria-redo")) $("criteria-redo").disabled = !state.criteriaRedoStack.length;
  if ($("criteria-format")) $("criteria-format").disabled = !input?.value.trim();
  if ($("criteria-lint")) $("criteria-lint").disabled = !input;
  if ($("criteria-save")) $("criteria-save").disabled = !input?.value.trim();
  if ($("criteria-version-back")) $("criteria-version-back").disabled = selectedIndex <= 0;
  if ($("criteria-version-forward")) $("criteria-version-forward").disabled = selectedIndex < 0 || selectedIndex >= versionCount - 1;
  if ($("criteria-restore")) $("criteria-restore").disabled = !selectedCriteriaVersion();
}

function criteriaVersionLabel(version, index) {
  const prefix = index + 1;
  const date = formatVersionDate(version.updated_at);
  const source = version.source ? ` · ${version.source}` : "";
  return `${prefix}. ${shortHash(version.hash || version.id)} · ${date}${source}`;
}

function formatVersionDate(value) {
  if (!value) return "unknown time";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function shortHash(value) {
  const text = String(value || "");
  return text ? text.slice(0, 10) : "unknown";
}

function renderRuns(runs) {
  const root = $("run-list");
  if (!runs.length) {
    root.innerHTML = `<div class="detail-panel empty">No research runs yet.</div>`;
    return;
  }
  root.innerHTML = runs
    .map(
      (run) => `<button class="run-item secondary" data-run-id="${escapeHtml(run.id)}">
        <strong>${escapeHtml(run.query || "Manual seed run")}</strong>
        <span>${escapeHtml(run.created_at || "")}</span>
        <span>${run.lead_count || 0} leads, top score ${run.top_score || 0}</span>
      </button>`,
    )
    .join("");
  root.querySelectorAll("[data-run-id]").forEach((item) => {
    item.addEventListener("click", async () => {
      state.currentRun = await api(`/api/runs/${item.dataset.runId}`);
      state.selectedLeadId = null;
      state.prospectFocusLeadId = null;
      resetRunDerivedState();
      renderRun(state.currentRun);
      activateView("leads");
    });
  });
}

function renderRun(run) {
  const leads = run?.leads || [];
  const selected = leads.find((lead) => lead.id === state.selectedLeadId) || leads[0] || null;
  state.selectedLeadId = selected?.id || null;
  state.selectedLeadIds.forEach((leadId) => {
    if (!leads.some((lead) => lead.id === leadId)) state.selectedLeadIds.delete(leadId);
  });
  if (
    state.prospectFocusLeadId &&
    state.prospectFocusLeadId !== ALL_PROSPECTS &&
    !leads.some((lead) => lead.id === state.prospectFocusLeadId)
  ) {
    state.prospectFocusLeadId = null;
  }
  renderSummary(run, leads);
  renderLeadControls(leads);
  renderLeadRows(leads);
  renderK2Panel();
  renderEvalPanel();
  renderLeadDetail(selected);
  renderProspectsPanel();
  if (run && state.prospectsRunId !== run.id) {
    refreshProspects({ silent: true }).catch((error) => {
      $("prospect-summary").className = "detail-panel empty";
      $("prospect-summary").textContent = error.message;
    });
  }
}

function renderSummary(run, leads) {
  const tierCounts = leads.reduce((acc, lead) => {
    const tier = lead.score?.tier || "Unknown";
    acc[tier] = (acc[tier] || 0) + 1;
    return acc;
  }, {});
  const topScore = leads.reduce((max, lead) => Math.max(max, lead.score?.total_score || 0), 0);
  $("summary-strip").innerHTML = [
    metric("Runs", run ? "1 active" : "none"),
    metric("Leads", leads.length),
    metric("Top score", topScore),
    metric("Tier A", tierCounts.A || 0),
    metric("Feedback", state.qualityFeedbackSummary.total || 0),
    metric("Eval", state.evalSummary.latest_status || "not_run"),
    metric("Selected", state.selectedLeadIds.size),
  ].join("");
}

function metric(label, value) {
  return `<div class="metric"><strong>${escapeHtml(value)}</strong><span>${escapeHtml(label)}</span></div>`;
}

function renderLeadControls(leads) {
  renderLeadStatusOptions();
  renderLeadSourceOptions(leads);
  renderLeadViews();
  if ($("lead-sort-field")) $("lead-sort-field").value = state.leadSortField;
  if ($("lead-sort-direction")) $("lead-sort-direction").textContent = state.leadSortDirection === "desc" ? "Desc" : "Asc";
  if ($("lead-page-size")) $("lead-page-size").value = String(state.leadPageSize);
  updateBulkControls();
}

function renderLeadStatusOptions() {
  const select = $("status-filter");
  if (!select) return;
  const current = select.value;
  const statuses = state.currentRun?.workflow?.lead_statuses || ["New", "Review", "Qualified", "Rejected", "Exported"];
  select.innerHTML = `<option value="">All statuses</option>${statuses.map((status) => `<option value="${escapeAttribute(status)}">${escapeHtml(status)}</option>`).join("")}`;
  select.value = statuses.includes(current) ? current : "";
}

function renderLeadSourceOptions(leads) {
  const select = $("source-filter");
  if (!select) return;
  const current = select.value;
  const sources = [...new Set(leads.map((lead) => leadSourceLabel(lead)).filter(Boolean))].sort((left, right) => left.localeCompare(right));
  select.innerHTML = `<option value="">All sources</option>${sources.map((source) => `<option value="${escapeAttribute(source)}">${escapeHtml(source)}</option>`).join("")}`;
  select.value = sources.includes(current) ? current : "";
}

function renderLeadViews() {
  const select = $("lead-view-select");
  if (!select) return;
  const current = select.value;
  select.innerHTML = `<option value="">Saved views</option>${(state.leadViews || []).map((view) => `<option value="${escapeAttribute(view.id)}">${escapeHtml(view.name || view.id)}</option>`).join("")}`;
  select.value = (state.leadViews || []).some((view) => view.id === current) ? current : "";
}

function filteredSortedLeads(leads) {
  const filter = $("lead-filter").value.toLowerCase();
  const tier = $("tier-filter").value;
  const status = $("status-filter")?.value || "";
  const source = $("source-filter")?.value || "";
  const filtered = leads.filter((lead) => {
    const workflow = lead.workflow || {};
    const haystack = JSON.stringify({
      company: lead.score?.company,
      tier: lead.score?.tier,
      status: workflow.status || "New",
      warnings: lead.score?.warnings,
      strategy: lead.strategy,
      source: leadSourceLabel(lead),
    }).toLowerCase();
    return (
      (!tier || lead.score?.tier === tier) &&
      (!status || (workflow.status || "New") === status) &&
      (!source || leadSourceLabel(lead) === source) &&
      (!filter || haystack.includes(filter))
    );
  });
  return filtered.sort(compareLeadsForQueue);
}

function compareLeadsForQueue(left, right) {
  const direction = state.leadSortDirection === "asc" ? 1 : -1;
  const field = state.leadSortField || "score";
  if (field === "score") {
    return direction * (Number(left.score?.total_score || 0) - Number(right.score?.total_score || 0)) || leadCompanyName(left).localeCompare(leadCompanyName(right));
  }
  if (field === "tier") {
    return direction * (tierRank(left.score?.tier) - tierRank(right.score?.tier)) || leadCompanyName(left).localeCompare(leadCompanyName(right));
  }
  if (field === "status") {
    return direction * workflowStatusRank(left).localeCompare(workflowStatusRank(right)) || leadCompanyName(left).localeCompare(leadCompanyName(right));
  }
  if (field === "source") {
    return direction * leadSourceLabel(left).localeCompare(leadSourceLabel(right)) || leadCompanyName(left).localeCompare(leadCompanyName(right));
  }
  return direction * leadCompanyName(left).localeCompare(leadCompanyName(right));
}

function currentLeadPageSize() {
  const value = Number($("lead-page-size")?.value || state.leadPageSize || 50);
  state.leadPageSize = Number.isFinite(value) ? Math.max(10, Math.min(value, 500)) : 50;
  return state.leadPageSize;
}

function renderLeadPagination(total, pageCount) {
  const root = $("lead-pagination");
  if (!root) return;
  const pageSize = currentLeadPageSize();
  const start = total ? (state.leadPage - 1) * pageSize + 1 : 0;
  const end = Math.min(total, state.leadPage * pageSize);
  root.innerHTML = `<button id="lead-page-prev" type="button" class="secondary small"${state.leadPage <= 1 ? " disabled" : ""}>Prev</button>
    <span>${escapeHtml(start)}-${escapeHtml(end)} of ${escapeHtml(total)}</span>
    <button id="lead-page-next" type="button" class="secondary small"${state.leadPage >= pageCount ? " disabled" : ""}>Next</button>`;
  $("lead-page-prev")?.addEventListener("click", () => {
    state.leadPage = Math.max(1, state.leadPage - 1);
    renderRun(state.currentRun);
  });
  $("lead-page-next")?.addEventListener("click", () => {
    state.leadPage = Math.min(pageCount, state.leadPage + 1);
    renderRun(state.currentRun);
  });
}

function syncSelectPageCheckbox(pageLeads) {
  const box = $("select-page-leads");
  if (!box) return;
  const selectable = pageLeads.filter((lead) => lead.id);
  const selectedCount = selectable.filter((lead) => state.selectedLeadIds.has(lead.id)).length;
  box.checked = Boolean(selectable.length && selectedCount === selectable.length);
  box.indeterminate = Boolean(selectedCount && selectedCount < selectable.length);
  updateBulkControls();
}

function updateBulkControls() {
  if ($("bulk-update-leads")) $("bulk-update-leads").disabled = !state.selectedLeadIds.size;
}

function leadCompanyName(lead) {
  return String(lead.score?.company?.company || lead.company || "");
}

function leadSourceLabel(lead) {
  const company = lead.score?.company || {};
  return String(company.source_group || lead.candidate?.source_title || company.source || "unknown");
}

function tierRank(tier) {
  return { A: 4, B: 3, C: 2, Reject: 1 }[String(tier || "")] ?? 0;
}

function workflowStatusRank(lead) {
  const status = String(lead.workflow?.status || "New");
  const rank = ["New", "Review", "Qualified", "Rejected", "Exported"].indexOf(status);
  return `${rank >= 0 ? rank : 99}`.padStart(2, "0");
}

function renderLeadRows(leads) {
  const root = $("lead-rows");
  const filtered = filteredSortedLeads(leads);
  const pageSize = currentLeadPageSize();
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  state.leadPage = Math.max(1, Math.min(state.leadPage, pageCount));
  const start = (state.leadPage - 1) * pageSize;
  const pageLeads = filtered.slice(start, start + pageSize);
  renderLeadPagination(filtered.length, pageCount);
  if (!filtered.length) {
    root.innerHTML = `<div class="lead-row"><span>No matching leads.</span></div>`;
    syncSelectPageCheckbox([]);
    return;
  }
  root.innerHTML = pageLeads
    .map((lead) => {
      const company = lead.score.company || {};
      const workflow = lead.workflow || {};
      const selected = lead.id === state.selectedLeadId ? " selected" : "";
      return `<div class="lead-row${selected}" data-lead-id="${escapeHtml(lead.id)}">
        <span><input class="lead-select" type="checkbox" data-select-lead-id="${escapeAttribute(lead.id)}"${state.selectedLeadIds.has(lead.id) ? " checked" : ""} aria-label="Select ${escapeAttribute(company.company || lead.id)}" /></span>
        <span><strong>${escapeHtml(company.company || "")}</strong><small>${escapeHtml(company.domain || "")}</small></span>
        <span class="${tierClass(lead.score.tier)}">${escapeHtml(lead.score.tier || "")}</span>
        <span class="score">${lead.score.total_score || 0}<small>${escapeHtml(workflow.status || "New")}</small></span>
        <span>${escapeHtml(lead.strategy?.wedge || lead.score.next_action || "")}</span>
      </div>`;
    })
    .join("");
  root.querySelectorAll("[data-select-lead-id]").forEach((box) => {
    box.addEventListener("change", (event) => {
      const leadId = event.currentTarget.dataset.selectLeadId;
      if (event.currentTarget.checked) state.selectedLeadIds.add(leadId);
      else state.selectedLeadIds.delete(leadId);
      syncSelectPageCheckbox(pageLeads);
      renderSummary(state.currentRun, state.currentRun?.leads || []);
    });
  });
  root.querySelectorAll("[data-lead-id]").forEach((row) => {
    row.addEventListener("click", (event) => {
      if (event.target.closest("input")) return;
      state.selectedLeadId = row.dataset.leadId;
      state.prospectFocusLeadId = row.dataset.leadId;
      renderRun(state.currentRun);
      activateView("prospects");
    });
  });
  syncSelectPageCheckbox(pageLeads);
}

function renderLeadDetail(lead) {
  const root = $("lead-detail");
  if (!lead) {
    root.className = "detail-panel empty";
    root.textContent = "Run a search or select a lead to inspect.";
    return;
  }
  root.className = "detail-panel";
  const score = lead.score || {};
  const company = score.company || {};
  const strategy = lead.strategy || {};
  const personas = strategy.personas || [];
  const gates = score.gates || [];
  const evidence = lead.evidence || [];
  const warnings = score.warnings || [];
  const metadata = lead.metadata || {};
  const sourceCounts = metadata.source_counts || {};
  const sourceRefs = metadata.source_refs || {};
  const coverage = metadata.intelligence_coverage || {};
  const criteria = state.currentRun?.criteria || {};
  const criteriaProfile = criteria.profile || metadata.criteria_profile || {};
  root.innerHTML = `<div class="detail-stack">
    <div class="detail-section">
      <p class="eyebrow">${escapeHtml(company.domain || "")}</p>
      <h2>${escapeHtml(company.company || "")}</h2>
      <div class="kv-grid">
        ${kv("Tier", score.tier || "")}
        ${kv("Total score", `${score.total_score || 0}/100`)}
        ${kv("AI posture", `${score.classification?.ai_posture ?? ""}/5`)}
        ${kv("Evidence", `${evidence.length} sources`)}
      </div>
    </div>
    <div class="detail-section">
      <h2>Strategy</h2>
      <p>${escapeHtml(strategy.outreach_angle || "")}</p>
      <p><strong>Offer:</strong> ${escapeHtml(strategy.offer || "")}</p>
      <p><strong>First step:</strong> ${escapeHtml(strategy.first_step || "")}</p>
    </div>
    <div class="detail-section">
      <h2>Active Criteria</h2>
      <div class="kv-grid">
        ${kv("Criteria hash", criteria.hash || criteriaProfile.hash || "")}
        ${kv("Tier A", `>= ${criteriaProfile.tier_a_threshold ?? 75}`)}
        ${kv("Tier B", `>= ${criteriaProfile.tier_b_threshold ?? 60}`)}
        ${kv("Budget range", `${criteriaProfile.min_employee_count ?? 25}-${criteriaProfile.max_employee_count ?? 2000} employees`)}
      </div>
      <div class="tag-list">${(criteriaProfile.priority_terms || []).slice(0, 8).map((term) => `<span class="tag">${escapeHtml(term)}</span>`).join("")}</div>
    </div>
    <div class="detail-section">
      <h2>Personas</h2>
      <div class="tag-list">${personas.map((item) => `<span class="tag">${escapeHtml(item.title)} - ${escapeHtml(item.priority)}</span>`).join("")}</div>
    </div>
    <div class="detail-section">
      <h2>Source Metadata</h2>
      <div class="metadata-grid">
        ${Object.entries(sourceCounts).map(([key, value]) => `<span><strong>${escapeHtml(value)}</strong>${escapeHtml(key)}</span>`).join("") || "<p>No source metadata captured.</p>"}
        ${metadata.public_profile_count !== undefined ? `<span><strong>${escapeHtml(metadata.public_profile_count)}</strong>public profiles</span>` : ""}
        ${metadata.public_resource_count !== undefined ? `<span><strong>${escapeHtml(metadata.public_resource_count)}</strong>public resources</span>` : ""}
      </div>
      <div class="tag-list">${coverageTags(coverage)}</div>
      <div class="ref-list">
        ${sourceRefBlock("LinkedIn", sourceRefs.linkedin_urls)}
        ${sourceRefBlock("GitHub", sourceRefs.github_urls)}
        ${sourceRefBlock("Social", sourceRefs.social_urls)}
        ${sourceRefBlock("Marketplaces", sourceRefs.marketplace_urls)}
        ${sourceRefBlock("Docs", sourceRefs.docs_urls)}
        ${sourceRefBlock("Pricing", sourceRefs.pricing_urls)}
        ${sourceRefBlock("Careers", sourceRefs.careers_urls)}
        ${sourceRefBlock("Contact", sourceRefs.contact_urls)}
        ${sourceRefBlock("Other", sourceRefs.other_urls)}
      </div>
    </div>
    <div class="detail-section">
      <h2>Hard Gates</h2>
      ${gates.map((gate) => `<p><strong>${escapeHtml(gate.status)}:</strong> ${escapeHtml(gate.name)} - ${escapeHtml(gate.reason)}</p>`).join("")}
    </div>
    <div class="detail-section">
      <h2>Review Flags</h2>
      ${warnings.length ? warnings.map((item) => `<p>${escapeHtml(item)}</p>`).join("") : "<p>No review flags.</p>"}
    </div>
    <div class="detail-section">
      <h2>Evidence</h2>
      <div class="evidence-list">
        ${evidence.slice(0, 8).map(evidenceItem).join("") || "<p>No website evidence stored.</p>"}
      </div>
    </div>
  </div>`;
}

function kv(label, value) {
  return `<div class="kv"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function evidenceItem(item) {
  const metadata = item.metadata || {};
  const tags = [item.source_type || metadata.source_type, metadata.page_category].filter(Boolean);
  return `<div class="evidence-item">
    <a href="${escapeAttribute(item.url || "#")}" target="_blank" rel="noreferrer">${escapeHtml(item.title || item.url || "Evidence")}</a>
    <div class="tag-list">${tags.map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}</div>
    <p>${escapeHtml((item.text || "").slice(0, 360))}</p>
  </div>`;
}

function coverageTags(coverage = {}) {
  return Object.entries(coverage)
    .filter(([, value]) => value)
    .map(([key]) => `<span class="tag">${escapeHtml(key.replaceAll("_", " "))}</span>`)
    .join("");
}

function sourceRefBlock(label, values = []) {
  if (!values || !values.length) return "";
  return `<div><strong>${escapeHtml(label)}</strong>${values
    .slice(0, 4)
    .map((url) => `<a href="${escapeAttribute(url)}" target="_blank" rel="noreferrer">${escapeHtml(url)}</a>`)
    .join("")}</div>`;
}

function renderK2Panel(manifest = state.currentManifest) {
  const root = $("k2-panel");
  if (!root) return;
  if (!state.currentRun) {
    root.className = "detail-panel empty";
    root.textContent = "Run research before exporting a K2 manifest.";
    return;
  }
  root.className = "detail-panel";
  if (!manifest) {
    const documentCount = state.currentRun.k2?.document_count ?? 0;
    root.innerHTML = `<div class="detail-stack">
      <div class="detail-section">
        <h2>Current Run</h2>
        <div class="kv-grid">
          ${kv("Run", state.currentRun.id)}
          ${kv("K2 status", state.currentRun.k2?.status || "unknown")}
          ${kv("Prepared documents", documentCount)}
          ${kv("Leads", state.currentRun.leads?.length || 0)}
        </div>
      </div>
      <p class="muted">Preview the manifest to inspect K2 metadata keys and document payloads.</p>
    </div>`;
    return;
  }
  root.innerHTML = `<div class="detail-stack">
    <div class="detail-section">
      <h2>Manifest Summary</h2>
      <div class="kv-grid">
        ${kv("Run", manifest.run_id || "")}
        ${kv("Documents", manifest.document_count || 0)}
        ${kv("K2 configured", manifest.k2_configured ? "yes" : "no")}
        ${kv("Export path", manifest.export_path || "not exported")}
      </div>
    </div>
    <div class="detail-section">
      <h2>Metadata Keys</h2>
      <div class="tag-list">${(manifest.metadata_keys || []).map((key) => `<span class="tag">${escapeHtml(key)}</span>`).join("")}</div>
    </div>
    <div class="detail-section">
      <h2>Document Preview</h2>
      <pre class="manifest-preview">${escapeHtml(JSON.stringify((manifest.documents || []).slice(0, 2), null, 2))}</pre>
    </div>
  </div>`;
}

function renderK2SyncResult(result) {
  const root = $("k2-panel");
  root.className = "detail-panel";
  root.innerHTML = `<div class="detail-stack">
    <div class="detail-section">
      <h2>K2 Sync Result</h2>
      <div class="kv-grid">
        ${kv("Status", result.status || "")}
        ${kv("Project", result.project_name || result.project_id || "")}
        ${kv("Corpus", result.corpus_name || result.corpus_id || "")}
        ${kv("Documents", result.document_count || 0)}
      </div>
      ${result.reason ? `<p class="muted">${escapeHtml(result.reason)}</p>` : ""}
    </div>
    <div class="detail-section">
      <h2>Raw Result</h2>
      <pre class="manifest-preview">${escapeHtml(JSON.stringify(result, null, 2))}</pre>
    </div>
  </div>`;
}

function renderK2PipelineActionResult(result) {
  renderK2WorkspaceStatus(result.workspace || state.currentK2WorkspaceStatus || {}, result);
}

function renderK2WorkspaceStatus(status, actionResult = null) {
  const root = $("k2-panel");
  if (!root) return;
  status = status || {};
  state.currentK2WorkspaceStatus = status;
  if (actionResult) state.currentK2PipelineAction = actionResult;
  root.className = "detail-panel";
  const warnings = status.warnings || [];
  root.innerHTML = `<div class="detail-stack">
    ${actionResult ? k2PipelineActionMarkup(actionResult) : ""}
    <div class="detail-section">
      <h2>K2 Workspace</h2>
      <div class="kv-grid">
        ${kv("Project", status.project?.name || status.project_name || "")}
        ${kv("Project status", status.project?.status || "")}
        ${kv("Source", status.source || "")}
        ${kv("K2 configured", status.configured ? "yes" : "no")}
        ${kv("Research corpus", status.research_corpus_id || "not configured")}
        ${kv("Base URL", status.base_url || "")}
      </div>
      ${warnings.length ? `<div class="eval-checks">${warnings.map((warning) => `<span class="status-pill warn-tag">${escapeHtml(warning)}</span>`).join("")}</div>` : ""}
    </div>
    ${workspaceStatusSection("Corpora", status.corpora || [])}
    ${workspaceStatusSection("Agents", status.agents || [])}
    ${workspaceStatusSection("Feeds", status.feeds || [])}
    ${workspaceStatusSection("Pipeline", status.pipeline_spec ? [status.pipeline_spec] : [])}
  </div>`;
}

function k2PipelineActionMarkup(actionResult) {
  const result = actionResult.result || {};
  const childRunIds = Array.isArray(result.child_run_ids || result.childRunIds) ? (result.child_run_ids || result.childRunIds) : [];
  return `<div class="detail-section">
    <h2>Pipeline Action Result</h2>
    <div class="kv-grid">
      ${kv("Action", actionResult.action || "")}
      ${kv("Status", actionResult.status || "")}
      ${kv("Pipeline", actionResult.pipeline_spec?.name || "")}
      ${kv("Pipeline status", actionResult.pipeline_spec?.status || "")}
      ${kv("Run", result.pipeline_run_id || result.pipelineRunId || result.run_id || "")}
      ${kv("Child jobs", childRunIds.length || result.child_run_count || 0)}
      ${kv("Valid", typeof result.valid === "boolean" ? (result.valid ? "yes" : "no") : "n/a")}
      ${kv("Backfill from", actionResult.backfill_start_from || "")}
    </div>
    ${actionResult.error ? `<p class="muted">${escapeHtml(actionResult.error)}</p>` : ""}
    <pre class="manifest-preview">${escapeHtml(JSON.stringify(result, null, 2))}</pre>
  </div>`;
}

function workspaceStatusSection(title, rows) {
  return `<div class="detail-section">
    <h2>${escapeHtml(title)}</h2>
    <div class="workspace-status-list">
      ${rows.map((row) => {
        const statusClass = ["found", "active"].includes(row.status) ? "ok-tag" : row.status === "expected" ? "" : "warn-tag";
        const health = row.health || {};
        const healthClass = health.status === "ready" || health.status === "summary" ? "ok-tag" : health.status ? "warn-tag" : "";
        const healthLine = title === "Corpora" && health.status
          ? `<small class="workspace-health">
              <span class="status-pill ${healthClass}">${escapeHtml(health.status)}</span>
              ${escapeHtml(`${health.total_documents ?? 0} docs · ${health.total_chunks ?? 0} chunks · ${health.field_count ?? 0} fields`)}
            </small>`
          : "";
        return `<div class="workspace-status-row">
          <div>
            <strong>${escapeHtml(row.name || "")}</strong>
            <small>${escapeHtml(row.description || "")}</small>
            ${healthLine}
          </div>
          <span class="status-pill ${statusClass}">${escapeHtml(row.status || "")}</span>
          <code>${escapeHtml(row.id || "not created")}</code>
        </div>`;
      }).join("") || "<p>No K2 workspace records returned.</p>"}
    </div>
  </div>`;
}

function renderEvalPanel(summary = state.evalSummary) {
  const root = $("eval-panel");
  if (!root) return;
  const latest = summary.latest_run || null;
  if (!latest) {
    root.className = "detail-panel empty";
    root.textContent = state.currentRun
      ? "Run an eval to validate loaded data, qualification output, prospect trees, and outreach readiness."
      : "Run research before validating quality.";
    return;
  }
  const metrics = latest.metrics || {};
  const checks = latest.checks || {};
  const failures = latest.failures || [];
  root.className = "detail-panel";
  root.innerHTML = `<div class="detail-stack">
    <div class="detail-section">
      <h2>Latest Eval</h2>
      <div class="kv-grid">
        ${kv("Status", latest.status || "")}
        ${kv("Run", latest.run_id || "")}
        ${kv("Cases", latest.case_count || 0)}
        ${kv("Criteria", shortHash(latest.criteria_hash || ""))}
      </div>
    </div>
    <div class="detail-section">
      <h2>Quality Metrics</h2>
      <div class="metadata-grid eval-metrics">
        ${evalMetric("Leads", metrics.lead_count)}
        ${evalMetric("Metadata", pct(metrics.required_metadata_completeness))}
        ${evalMetric("Evidence", pct(metrics.evidence_coverage))}
        ${evalMetric("Gold cases", pct(metrics.qualification_case_pass_rate))}
        ${evalMetric("Role tree", pct(metrics.prospect_role_coverage))}
        ${evalMetric("Outreach", pct(metrics.outreach_draft_coverage))}
        ${evalMetric("Ready drafts", pct(metrics.outreach_ready_rate))}
        ${evalMetric("Contacts", pct(metrics.contact_detail_rate))}
      </div>
    </div>
    <div class="detail-section">
      <h2>Gate Checks</h2>
      <div class="eval-checks">
        ${Object.entries(checks).map(([name, check]) => `<span class="tag ${check.passed ? "ok-tag" : "warn-tag"}">${escapeHtml(name.replaceAll("_", " "))}: ${check.skipped ? "skipped" : check.passed ? "pass" : "review"}</span>`).join("")}
      </div>
    </div>
    <div class="detail-section">
      <h2>Review Queue</h2>
      ${failures.length ? failures.slice(0, 12).map(evalFailureMarkup).join("") : "<p>No eval failures in the latest run.</p>"}
    </div>
    <div class="detail-section">
      <h2>K2 Alignment</h2>
      <div class="tag-list">${(latest.k2_alignment?.primitives || []).map((item) => `<span class="tag">${escapeHtml(item)}</span>`).join("")}</div>
      <p class="muted">${escapeHtml(latest.k2_alignment?.native_eval_status?.reason || "K2 quality primitives remain the target system of record.")}</p>
    </div>
  </div>`;
}

function evalMetric(label, value) {
  return `<span><strong>${escapeHtml(value ?? 0)}</strong>${escapeHtml(label)}</span>`;
}

function evalFailureMarkup(failure) {
  const title = failure.metric || failure.case_id || failure.domain || failure.type || "failure";
  const detail = failure.reason || failure.threshold || failure.value || "";
  return `<p class="audit-item"><strong>${escapeHtml(failure.type || "eval")}</strong> ${escapeHtml(title)}${detail ? ` · ${escapeHtml(detail)}` : ""}</p>`;
}

function pct(value) {
  const number = Number(value || 0);
  return `${Math.round(number * 100)}%`;
}

function renderProspectsPanel(payload = state.currentProspects) {
  const summary = $("prospect-summary");
  const rows = $("prospect-rows");
  if (!summary || !rows) return;
  if (!state.currentRun) {
    summary.className = "detail-panel empty";
    summary.textContent = "Run research before inspecting prospects.";
    rows.innerHTML = "";
    return;
  }
  if (!payload) {
    summary.className = "detail-panel empty";
    summary.textContent = "Loading prospect targets...";
    rows.innerHTML = "";
    return;
  }
  summary.className = "detail-panel";
  const prospects = payload.prospects || [];
  const focusLead = currentProspectFocusLead();
  const visibleProspects = focusLead ? prospectsForLead(prospects, focusLead) : prospects;
  const counts = prospectSourceCounts(visibleProspects);
  const focusCompany = focusLead ? leadCompany(focusLead) : null;
  renderAccountDrilldown(focusLead);
  summary.innerHTML = `<div class="prospect-focus">
    <div class="prospect-summary">
      ${metric(focusLead ? "Company prospects" : "All prospects", visibleProspects.length)}
      ${metric("Apollo", counts.apollo || 0)}
      ${metric("Persona targets", counts.strategy || 0)}
      ${metric("Scope", focusCompany?.company || "All companies")}
    </div>
    ${
      focusLead
        ? `<button id="clear-prospect-focus" type="button" class="secondary">All companies</button>`
        : ""
    }
  </div>`;
  $("clear-prospect-focus")?.addEventListener("click", () => {
    state.prospectFocusLeadId = ALL_PROSPECTS;
    renderProspectsPanel();
  });
  if (!visibleProspects.length) {
    rows.innerHTML = `<div class="prospect-row"><span>No prospects available${focusCompany?.company ? ` for ${escapeHtml(focusCompany.company)}` : ""}.</span></div>`;
    return;
  }
  rows.innerHTML = renderProspectTree(visibleProspects, focusLead);
}

function renderAccountDrilldown(focusLead) {
  const root = $("account-drilldown");
  if (!root) return;
  if (!state.currentRun) {
    root.className = "detail-panel account-drilldown empty";
    root.textContent = "Run research before inspecting account context.";
    return;
  }
  if (!focusLead) {
    root.className = "detail-panel account-drilldown empty";
    root.textContent = "Select a company to inspect account context.";
    clearAccountDetailState();
    return;
  }
  const key = accountKey(focusLead);
  if (!key) {
    root.className = "detail-panel account-drilldown empty";
    root.textContent = "This account is missing a domain or lead identifier.";
    clearAccountDetailState();
    return;
  }
  ensureAccountDetail(key).catch((error) => {
    if (state.accountDetailKey !== key) return;
    state.accountDetailError = error.message;
    root.className = "detail-panel account-drilldown empty";
    root.textContent = error.message;
  });
  if (state.accountDetailError && state.accountDetailKey === key) {
    root.className = "detail-panel account-drilldown empty";
    root.textContent = state.accountDetailError;
    return;
  }
  if (!state.currentAccountDetail || state.accountDetailKey !== key || state.accountDetailRunId !== state.currentRun.id) {
    const company = leadCompany(focusLead);
    root.className = "detail-panel account-drilldown loading";
    root.innerHTML = `<div>
      <p class="eyebrow">${escapeHtml(company.domain || "")}</p>
      <h2>${escapeHtml(company.company || "Loading account")}</h2>
      <p class="muted">Loading account context, workflow state, evidence, and prospect roles...</p>
    </div>`;
    return;
  }
  root.className = "detail-panel account-drilldown";
  root.innerHTML = accountDetailMarkup(state.currentAccountDetail);
  $("account-workflow-form")?.addEventListener("submit", saveAccountWorkflow);
  $("account-feedback-form")?.addEventListener("submit", saveAccountQualityFeedback);
  $("account-feedback-export")?.addEventListener("click", downloadQualityFeedback);
  $("account-outreach-export")?.addEventListener("click", downloadOutreachDrafts);
  root.querySelectorAll(".draft-status-form").forEach((form) => {
    form.addEventListener("submit", saveOutreachDraftStatus);
  });
}

async function ensureAccountDetail(key) {
  if (
    state.currentAccountDetail &&
    state.accountDetailKey === key &&
    state.accountDetailRunId === state.currentRun?.id
  ) {
    return;
  }
  if (state.accountDetailKey !== key || state.accountDetailRunId !== state.currentRun?.id) {
    state.currentAccountDetail = null;
    state.accountDetailError = "";
    state.accountDetailKey = key;
    state.accountDetailRunId = state.currentRun?.id || null;
  }
  const payload = await api(`/api/runs/${encodeURIComponent(state.currentRun.id)}/accounts/${encodeURIComponent(key)}`);
  if (state.accountDetailKey === key && state.accountDetailRunId === state.currentRun?.id) {
    state.currentAccountDetail = payload;
    state.accountDetailError = "";
    renderAccountDrilldown(currentProspectFocusLead());
  }
}

function clearAccountDetailState() {
  state.currentAccountDetail = null;
  state.accountDetailRunId = null;
  state.accountDetailKey = null;
  state.accountDetailError = "";
}

function accountDetailMarkup(detail) {
  const company = detail.company || {};
  const score = detail.score || {};
  const workflow = detail.workflow || {};
  const criteria = detail.criteria_snapshot || {};
  const criteriaProfile = criteria.profile || {};
  const roleGroups = detail.role_groups || [];
  const evidence = detail.evidence_timeline || [];
  const auditEvents = detail.audit_events || [];
  const qualitySummary = detail.quality_summary || {};
  const qualityFeedback = detail.quality_feedback || [];
  const outreachSummary = detail.outreach_summary || {};
  const outreachDrafts = detail.outreach_drafts || [];
  return `<div class="account-detail-stack">
    <section class="account-hero">
      <div>
        <p class="eyebrow">${escapeHtml(company.domain || workflow.domain || "")}</p>
        <h2 class="account-title">${escapeHtml(company.company || workflow.company || "Account")}</h2>
        <div class="tag-list">
          <span class="${tierClass(score.tier)}">${escapeHtml(score.tier || "Unknown tier")}</span>
          <span class="status-pill">${escapeHtml(workflow.status || "New")}</span>
          ${workflow.owner ? `<span class="tag">Owner: ${escapeHtml(workflow.owner)}</span>` : ""}
        </div>
      </div>
      <div class="account-metrics">
        ${metric("Score", `${score.total_score || 0}/100`)}
        ${metric("Prospects", detail.prospects?.length || 0)}
        ${metric("Evidence", evidence.length)}
        ${metric("Criteria", shortHash(criteria.hash || ""))}
      </div>
    </section>
    <section class="account-workflow">
      <form id="account-workflow-form" class="workflow-form" data-domain="${escapeAttribute(workflow.domain || company.domain || "")}" data-company="${escapeAttribute(company.company || workflow.company || "")}">
        <label>
          Status
          <select id="account-status">${(detail.lead_statuses || []).map((status) => `<option value="${escapeAttribute(status)}"${status === workflow.status ? " selected" : ""}>${escapeHtml(status)}</option>`).join("")}</select>
        </label>
        <label>
          Owner
          <input id="account-owner" value="${escapeAttribute(workflow.owner || "")}" placeholder="Owner" />
        </label>
        <label>
          Tags
          <input id="account-tags" value="${escapeAttribute((workflow.tags || []).join(", "))}" placeholder="tier-a, fleet, apollo" />
        </label>
        <label class="workflow-note">
          Notes
          <textarea id="account-note" rows="3" placeholder="Qualification notes and next action">${escapeHtml(workflow.note || "")}</textarea>
        </label>
        <button type="submit">Save account</button>
      </form>
    </section>
    <section class="account-columns">
      <div class="account-card">
        <h3>Strategy</h3>
        <p>${escapeHtml(detail.strategy?.outreach_angle || "")}</p>
        <p><strong>Offer:</strong> ${escapeHtml(detail.strategy?.offer || "")}</p>
        <p><strong>First step:</strong> ${escapeHtml(detail.strategy?.first_step || "")}</p>
      </div>
      <div class="account-card">
        <h3>Criteria Snapshot</h3>
        <div class="kv-grid compact">
          ${kv("Hash", criteria.hash || "")}
          ${kv("Tier A", `>= ${criteriaProfile.tier_a_threshold ?? 75}`)}
          ${kv("Tier B", `>= ${criteriaProfile.tier_b_threshold ?? 60}`)}
          ${kv("Budget", `${criteriaProfile.min_employee_count ?? 25}-${criteriaProfile.max_employee_count ?? 2000}`)}
        </div>
      </div>
    </section>
    <section class="account-card account-role-tree">
      <h3>Prospect Role Tree</h3>
      ${roleGroups.length ? roleGroups.map(accountRoleGroupMarkup).join("") : "<p>No prospects or personas available for this account.</p>"}
    </section>
    <section class="account-card outreach-card">
      <div class="card-heading-row">
        <h3>Outreach Drafts</h3>
        <button id="account-outreach-export" type="button" class="secondary small">Export CSV</button>
      </div>
      <div class="account-metrics compact">
        ${metric("Drafts", outreachSummary.total || outreachDrafts.length || 0)}
        ${metric("Approved", outreachSummary.status_counts?.Approved || 0)}
        ${metric("Exported", outreachSummary.status_counts?.Exported || 0)}
        ${metric("Ready", outreachSummary.ready_count || 0)}
      </div>
      <div class="outreach-draft-list">
        ${outreachDrafts.length ? outreachDrafts.map(accountOutreachDraftMarkup).join("") : "<p>No outreach drafts available for this account.</p>"}
      </div>
    </section>
    <section class="account-card quality-feedback-card">
      <div class="card-heading-row">
        <h3>Quality Feedback</h3>
        <button id="account-feedback-export" type="button" class="secondary small">Export CSV</button>
      </div>
      <div class="account-metrics compact">
        ${metric("Total", qualitySummary.total || 0)}
        ${metric("Positive", qualitySummary.rating_counts?.positive || 0)}
        ${metric("Neutral", qualitySummary.rating_counts?.neutral || 0)}
        ${metric("Negative", qualitySummary.rating_counts?.negative || 0)}
      </div>
      <form id="account-feedback-form" class="feedback-form" data-domain="${escapeAttribute(workflow.domain || company.domain || "")}" data-company="${escapeAttribute(company.company || workflow.company || "")}">
        <label>
          Dimension
          <select id="account-feedback-dimension">
            <option value="score">Score fit</option>
            <option value="persona">Persona fit</option>
            <option value="outreach">Outreach angle</option>
          </select>
        </label>
        <label>
          Rating
          <select id="account-feedback-rating">
            <option value="positive">Positive</option>
            <option value="neutral">Neutral</option>
            <option value="negative">Negative</option>
          </select>
        </label>
        <label class="feedback-note">
          Note
          <textarea id="account-feedback-note" rows="3" placeholder="What should this label teach future scoring or targeting?"></textarea>
        </label>
        <button type="submit">Save feedback</button>
      </form>
      <div class="feedback-list">
        ${qualityFeedback.length ? qualityFeedback.slice().reverse().map(accountFeedbackMarkup).join("") : "<p>No quality labels yet.</p>"}
      </div>
    </section>
    <section class="account-card evidence-timeline">
      <h3>Evidence Timeline</h3>
      ${evidence.length ? evidence.slice(0, 10).map(accountEvidenceMarkup).join("") : "<p>No evidence captured for this account.</p>"}
    </section>
    <section class="account-card">
      <h3>Source Coverage</h3>
      <div class="metadata-grid">
        ${Object.entries(detail.source_counts || {}).map(([key, value]) => `<span><strong>${escapeHtml(value)}</strong>${escapeHtml(key)}</span>`).join("") || "<p>No source metadata captured.</p>"}
      </div>
      <div class="tag-list">${coverageTags(detail.coverage || {})}</div>
      <div class="ref-list">${Object.entries(detail.source_refs || {}).map(([label, values]) => sourceRefBlock(label.replaceAll("_", " "), values)).join("")}</div>
    </section>
    <section class="account-card">
      <h3>Account History</h3>
      ${auditEvents.length ? auditEvents.map(accountAuditMarkup).join("") : "<p>No workflow history yet.</p>"}
    </section>
  </div>`;
}

function accountOutreachDraftMarkup(draft) {
  const evidenceLinks = (draft.evidence || []).filter((item) => item.url).map((item) => (
    `<a href="${escapeAttribute(item.url)}" target="_blank" rel="noreferrer">${escapeHtml(item.title || item.url)}</a>`
  ));
  return `<article class="outreach-draft">
    <div class="outreach-draft-heading">
      <div>
        <span class="status-pill">${escapeHtml(draft.status || "Draft")}</span>
        <strong>${escapeHtml(draft.prospect_name || draft.persona || draft.title || "Prospect")}</strong>
        <small>${escapeHtml(draft.title || draft.persona || "")} · ${escapeHtml(draft.source || "")}</small>
      </div>
      <span class="muted">${escapeHtml(draft.updated_at || "")}</span>
    </div>
    <p><strong>Subject:</strong> ${escapeHtml(draft.subject || "")}</p>
    <pre class="draft-body">${escapeHtml(draft.body || "")}</pre>
    <p><strong>CTA:</strong> ${escapeHtml(draft.cta || draft.first_step || "")}</p>
    <div class="draft-evidence">${evidenceLinks.length ? evidenceLinks.join("") : "<span class=\"muted\">No citation link captured.</span>"}</div>
    <form class="draft-status-form" data-prospect-id="${escapeAttribute(draft.prospect_id || "")}" data-domain="${escapeAttribute(draft.domain || "")}" data-company="${escapeAttribute(draft.company || "")}">
      <label>
        Status
        <select name="status">
          ${["Draft", "Approved", "Rejected", "Exported"].map((status) => `<option value="${escapeAttribute(status)}"${status === draft.status ? " selected" : ""}>${escapeHtml(status)}</option>`).join("")}
        </select>
      </label>
      <label class="draft-note">
        Review note
        <input name="note" value="${escapeAttribute(draft.approval_note || "")}" placeholder="Why approve, reject, or export?" />
      </label>
      <button type="submit" class="secondary">Save</button>
    </form>
  </article>`;
}

function accountFeedbackMarkup(item) {
  return `<article class="feedback-item">
    <div>
      <span class="feedback-rating rating-${escapeAttribute(item.rating || "neutral")}">${escapeHtml(item.rating || "neutral")}</span>
      <strong>${escapeHtml((item.dimension || "score").replaceAll("_", " "))}</strong>
      <small>${escapeHtml(item.created_at || "")}</small>
    </div>
    ${item.note ? `<p>${escapeHtml(item.note)}</p>` : ""}
  </article>`;
}

function accountRoleGroupMarkup(group) {
  return `<details class="account-role-group" open>
    <summary><strong>${escapeHtml(group.role || "Role")}</strong><small>${escapeHtml(group.priority || "")} · ${(group.prospects || []).length} target(s)</small></summary>
    <div class="account-role-rows">${(group.prospects || []).map(accountProspectMarkup).join("")}</div>
  </details>`;
}

function accountProspectMarkup(prospect) {
  return `<div class="account-prospect-row">
    <span><strong>${escapeHtml(prospect.name || prospect.persona || prospect.title || "")}</strong><small>${escapeHtml(prospect.title || prospect.persona || "")}</small></span>
    <span>${escapeHtml(prospect.source || "")}</span>
    <span>${prospectContactLink(prospect)}</span>
  </div>`;
}

function accountEvidenceMarkup(item) {
  const tags = [item.source_type, item.page_category].filter(Boolean);
  return `<article class="timeline-item">
    <div>
      <a href="${escapeAttribute(item.url || "#")}" target="_blank" rel="noreferrer">${escapeHtml(item.title || "Evidence")}</a>
      <div class="tag-list">${tags.map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}</div>
    </div>
    <p>${escapeHtml((item.text || "").slice(0, 280))}</p>
  </article>`;
}

function accountAuditMarkup(event) {
  const details = event.details || {};
  return `<p class="audit-item"><strong>${escapeHtml(event.action || "event")}</strong> ${escapeHtml(event.created_at || "")}${details.status ? ` · ${escapeHtml(details.previous_status || "")} to ${escapeHtml(details.status)}` : ""}</p>`;
}

async function saveAccountWorkflow(event) {
  event.preventDefault();
  if (!state.currentRun || !state.currentAccountDetail) return;
  const form = event.currentTarget;
  const domain = form.dataset.domain || state.currentAccountDetail.workflow?.domain || state.currentAccountDetail.company?.domain || "";
  const company = form.dataset.company || state.currentAccountDetail.company?.company || "";
  const tags = $("account-tags").value.split(",").map((tag) => tag.trim()).filter(Boolean);
  const payload = await api(`/api/runs/${state.currentRun.id}/lead-state`, {
    method: "POST",
    body: JSON.stringify({
      domain,
      company,
      status: $("account-status").value,
      owner: $("account-owner").value,
      tags,
      note: $("account-note").value,
    }),
  });
  state.currentAccountDetail.workflow = payload.lead_state;
  if (state.currentRun.workflow) state.currentRun.workflow.status_counts = payload.status_counts || state.currentRun.workflow.status_counts;
  const lead = (state.currentRun.leads || []).find((item) => normalizeText(leadCompany(item).domain) === normalizeText(domain));
  if (lead) lead.workflow = payload.lead_state;
  clearAccountDetailState();
  renderRun(state.currentRun);
}

async function saveAccountQualityFeedback(event) {
  event.preventDefault();
  if (!state.currentRun || !state.currentAccountDetail) return;
  const form = event.currentTarget;
  const domain = form.dataset.domain || state.currentAccountDetail.workflow?.domain || state.currentAccountDetail.company?.domain || "";
  const company = form.dataset.company || state.currentAccountDetail.company?.company || "";
  const payload = await api(`/api/runs/${state.currentRun.id}/quality-feedback`, {
    method: "POST",
    body: JSON.stringify({
      domain,
      company,
      dimension: $("account-feedback-dimension").value,
      rating: $("account-feedback-rating").value,
      note: $("account-feedback-note").value,
    }),
  });
  state.qualityFeedbackSummary = payload.summary || state.qualityFeedbackSummary;
  state.currentAccountDetail.quality_summary = payload.account_summary || state.currentAccountDetail.quality_summary || {};
  state.currentAccountDetail.quality_feedback = [
    ...(state.currentAccountDetail.quality_feedback || []),
    payload.feedback,
  ].filter(Boolean);
  $("account-feedback-note").value = "";
  renderSummary(state.currentRun, state.currentRun.leads || []);
  renderAccountDrilldown(currentProspectFocusLead());
}

async function downloadQualityFeedback() {
  if (!state.currentRun) return;
  const response = await authFetch(`/api/runs/${encodeURIComponent(state.currentRun.id)}/quality-feedback.csv`, {
    headers: { Accept: "text/csv" },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || `Export failed: ${response.status}`);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${state.currentRun.id}-quality-feedback.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function saveOutreachDraftStatus(event) {
  event.preventDefault();
  if (!state.currentRun || !state.currentAccountDetail) return;
  const form = event.currentTarget;
  const payload = await api(`/api/runs/${state.currentRun.id}/outreach-drafts/status`, {
    method: "POST",
    body: JSON.stringify({
      prospect_id: form.dataset.prospectId || "",
      domain: form.dataset.domain || state.currentAccountDetail.workflow?.domain || state.currentAccountDetail.company?.domain || "",
      company: form.dataset.company || state.currentAccountDetail.company?.company || "",
      status: form.elements.status.value,
      note: form.elements.note.value,
    }),
  });
  const record = payload.outreach_status || {};
  state.currentAccountDetail.outreach_summary = payload.account_summary || state.currentAccountDetail.outreach_summary || {};
  state.currentAccountDetail.outreach_drafts = (state.currentAccountDetail.outreach_drafts || []).map((draft) => (
    draft.prospect_id === record.prospect_id
      ? { ...draft, status: record.status || draft.status, approval_note: record.note || "", updated_at: record.updated_at || "" }
      : draft
  ));
  renderAccountDrilldown(currentProspectFocusLead());
}

async function downloadOutreachDrafts() {
  if (!state.currentRun) return;
  await downloadWithAuth(
    `/api/runs/${encodeURIComponent(state.currentRun.id)}/outreach-drafts.csv`,
    `${state.currentRun.id}-outreach-drafts.csv`,
    "text/csv",
  );
}

async function bulkUpdateSelectedLeads() {
  if (!state.currentRun || !state.selectedLeadIds.size) return;
  const selected = (state.currentRun.leads || []).filter((lead) => state.selectedLeadIds.has(lead.id));
  const domains = selected.map((lead) => leadCompany(lead).domain).filter(Boolean);
  if (!domains.length) return;
  const payload = await api(`/api/runs/${state.currentRun.id}/lead-state/bulk`, {
    method: "POST",
    body: JSON.stringify({
      domains,
      status: $("bulk-status").value,
      note: $("bulk-note").value,
    }),
  });
  const statesByDomain = new Map((payload.lead_states || []).map((item) => [normalizeText(item.domain), item]));
  for (const lead of state.currentRun.leads || []) {
    const record = statesByDomain.get(normalizeText(leadCompany(lead).domain));
    if (record) lead.workflow = record;
  }
  if (state.currentRun.workflow) state.currentRun.workflow.status_counts = payload.status_counts || state.currentRun.workflow.status_counts;
  state.selectedLeadIds.clear();
  $("bulk-note").value = "";
  clearAccountDetailState();
  renderRun(state.currentRun);
}

async function saveCurrentLeadView() {
  const name = $("lead-view-name").value.trim();
  if (!name) return;
  const payload = await api("/api/lead-views", {
    method: "POST",
    body: JSON.stringify({
      name,
      filters: currentLeadFilters(),
      sort: { field: state.leadSortField, direction: state.leadSortDirection },
      page_size: currentLeadPageSize(),
    }),
  });
  state.leadViews = payload.views || state.leadViews;
  $("lead-view-name").value = "";
  renderLeadViews();
}

function currentLeadFilters() {
  return {
    text: $("lead-filter").value,
    tier: $("tier-filter").value,
    status: $("status-filter")?.value || "",
    source: $("source-filter")?.value || "",
  };
}

function applyLeadView(viewId) {
  const view = (state.leadViews || []).find((item) => item.id === viewId);
  if (!view) return;
  const filters = view.filters || {};
  $("lead-filter").value = filters.text || "";
  $("tier-filter").value = filters.tier || "";
  $("status-filter").value = filters.status || "";
  $("source-filter").value = filters.source || "";
  state.leadSortField = view.sort?.field || "score";
  state.leadSortDirection = view.sort?.direction === "asc" ? "asc" : "desc";
  state.leadPageSize = Number(view.page_size || state.leadPageSize || 50);
  state.leadPage = 1;
  renderRun(state.currentRun);
}

function visibleLeadPage() {
  const leads = filteredSortedLeads(state.currentRun?.leads || []);
  const pageSize = currentLeadPageSize();
  const pageCount = Math.max(1, Math.ceil(leads.length / pageSize));
  state.leadPage = Math.max(1, Math.min(state.leadPage, pageCount));
  return leads.slice((state.leadPage - 1) * pageSize, state.leadPage * pageSize);
}

function leadQueueControlsChanged() {
  state.leadPage = 1;
  renderRun(state.currentRun);
}

function accountKey(lead) {
  const company = leadCompany(lead);
  return company.domain || lead?.domain || lead?.id || company.company || "";
}

function currentProspectFocusLead() {
  if (!state.currentRun || state.prospectFocusLeadId === ALL_PROSPECTS) return null;
  const leads = state.currentRun.leads || [];
  const focusId = state.prospectFocusLeadId || state.selectedLeadId;
  return leads.find((lead) => lead.id === focusId) || leads.find((lead) => lead.id === state.selectedLeadId) || leads[0] || null;
}

function leadCompany(lead) {
  return lead?.score?.company || {};
}

function prospectsForLead(prospects, lead) {
  const company = leadCompany(lead);
  const leadId = normalizeText(lead?.id);
  const domain = normalizeText(company.domain);
  const companyName = normalizeText(company.company);
  return prospects.filter((prospect) => {
    return (
      normalizeText(prospect.lead_id) === leadId ||
      (domain && normalizeText(prospect.domain) === domain) ||
      (companyName && normalizeText(prospect.company) === companyName)
    );
  });
}

function prospectSourceCounts(prospects) {
  return prospects.reduce((acc, prospect) => {
    const source = prospect.source || "unknown";
    acc[source] = (acc[source] || 0) + 1;
    return acc;
  }, {});
}

function renderProspectTree(prospects, focusLead) {
  const companyGroups = focusLead
    ? [{ company: leadCompany(focusLead), prospects }]
    : groupProspectsByCompany(prospects);
  return `<div class="prospect-tree">
    ${companyGroups.map((group) => renderProspectCompanyNode(group.company, group.prospects)).join("")}
  </div>`;
}

function groupProspectsByCompany(prospects) {
  const groups = new Map();
  prospects.forEach((prospect) => {
    const key = `${normalizeText(prospect.company)}|${normalizeText(prospect.domain)}`;
    if (!groups.has(key)) {
      groups.set(key, {
        company: { company: prospect.company || "Unknown company", domain: prospect.domain || "" },
        prospects: [],
      });
    }
    groups.get(key).prospects.push(prospect);
  });
  return Array.from(groups.values()).sort((a, b) => String(a.company.company || "").localeCompare(String(b.company.company || "")));
}

function renderProspectCompanyNode(company, prospects) {
  const roleGroups = groupProspectsByRole(prospects);
  return `<section class="prospect-company-node">
    <div class="prospect-company-title">
      <span><strong>${escapeHtml(company.company || "Unknown company")}</strong><small>${escapeHtml(company.domain || "")}</small></span>
      <span class="status-pill">${prospects.length} ${prospects.length === 1 ? "target" : "targets"}</span>
    </div>
    ${roleGroups.map(renderProspectRoleGroup).join("")}
  </section>`;
}

function groupProspectsByRole(prospects) {
  const groups = new Map();
  [...prospects].sort(compareProspects).forEach((prospect) => {
    const role = prospect.persona || prospect.title || "Other role";
    if (!groups.has(role)) groups.set(role, []);
    groups.get(role).push(prospect);
  });
  return Array.from(groups.entries()).map(([role, items]) => ({ role, prospects: items }));
}

function renderProspectRoleGroup(group) {
  const primary = group.prospects[0] || {};
  const priority = primary.persona_priority || primary.source || "";
  return `<details class="prospect-role-group" open>
    <summary>
      <span><strong>${escapeHtml(group.role)}</strong><small>${escapeHtml(priority)} · ${group.prospects.length} ${group.prospects.length === 1 ? "target" : "targets"}</small></span>
    </summary>
    <div class="prospect-role-rows">
      ${group.prospects.map(renderProspectRow).join("")}
    </div>
  </details>`;
}

function renderProspectRow(prospect) {
  return `<div class="prospect-row prospect-tree-row">
      <span>
        <strong>${escapeHtml(prospect.name || prospect.persona || "")}</strong>
        <small>${escapeHtml(prospect.company || "")} · ${escapeHtml(prospect.domain || "")}</small>
      </span>
      <span>${escapeHtml(prospect.title || "")}</span>
      <span><strong>${escapeHtml(prospect.priority_score || 0)}</strong><small>${escapeHtml(prospect.source || "")}</small></span>
      <span class="link-stack">${prospectContactLink(prospect)}</span>
      <span>${escapeHtml(prospect.outreach_angle || "")}</span>
    </div>`;
}

function compareProspects(a, b) {
  return (
    personaPriorityRank(a.persona_priority) - personaPriorityRank(b.persona_priority) ||
    sourceRank(a.source) - sourceRank(b.source) ||
    Number(b.priority_score || 0) - Number(a.priority_score || 0) ||
    String(a.name || a.title || "").localeCompare(String(b.name || b.title || ""))
  );
}

function personaPriorityRank(value) {
  const priority = normalizeText(value);
  if (priority === "primary") return 0;
  if (priority === "secondary") return 1;
  if (priority === "tertiary") return 2;
  return 3;
}

function sourceRank(value) {
  return normalizeText(value) === "apollo" ? 0 : 1;
}

function normalizeText(value) {
  return String(value || "").trim().toLowerCase();
}

function prospectContactLink(prospect) {
  const links = [];
  if (prospect.linkedin_url) {
    links.push(`<a href="${escapeAttribute(prospect.linkedin_url)}" target="_blank" rel="noreferrer">LinkedIn</a>`);
  }
  if (prospect.email) {
    links.push(`<a href="mailto:${escapeAttribute(prospect.email)}">${escapeHtml(prospect.email)}</a>`);
  }
  if (prospect.phone) {
    links.push(`<a href="tel:${escapeAttribute(prospect.phone)}">${escapeHtml(prospect.phone)}</a>`);
  }
  return links.length ? links.join("<br>") : escapeHtml(prospectContactLabel(prospect));
}

function prospectContactLabel(prospect) {
  if (prospect.status === "persona_target") return "Persona";
  if (prospect.status === "person_found") return "Apollo";
  return String(prospect.status || prospect.source || "").replaceAll("_", " ");
}

async function refreshProspects({ silent = false } = {}) {
  if (!state.currentRun) return;
  if (!silent) {
    state.currentProspects = null;
    renderProspectsPanel();
  }
  state.prospectsRunId = state.currentRun.id;
  const payload = await api(`/api/runs/${state.currentRun.id}/prospects`);
  state.currentProspects = payload;
  renderProspectsPanel(payload);
}

async function downloadWithAuth(path, filename, contentType) {
  const response = await authFetch(path, { headers: { Accept: contentType } });
  if (!response.ok) {
    let message = `Request failed: ${response.status}`;
    try {
      const payload = await response.json();
      message = payload.error || message;
    } catch {
      // Keep the HTTP status fallback when the response is not JSON.
    }
    throw new Error(message);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function tierClass(tier) {
  const normalized = String(tier || "").toLowerCase();
  if (normalized === "a") return "tier tier-a";
  if (normalized === "b") return "tier tier-b";
  if (normalized === "c") return "tier tier-c";
  return "tier tier-reject";
}

function activateView(name) {
  document.querySelectorAll(".tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.view === name));
  document.querySelectorAll(".view").forEach((view) => view.classList.toggle("active", view.id === `view-${name}`));
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttribute(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => activateView(tab.dataset.view));
});

initAuthControls();
$("save-admin-token").addEventListener("click", () => {
  saveAuthToken().catch((error) => {
    setAuthStatus(error.message);
  });
});
$("clear-admin-token").addEventListener("click", clearAuthToken);
$("lead-filter").addEventListener("input", leadQueueControlsChanged);
$("tier-filter").addEventListener("change", leadQueueControlsChanged);
$("status-filter").addEventListener("change", leadQueueControlsChanged);
$("source-filter").addEventListener("change", leadQueueControlsChanged);
$("lead-page-size").addEventListener("change", leadQueueControlsChanged);
$("lead-sort-field").addEventListener("change", (event) => {
  state.leadSortField = event.currentTarget.value || "score";
  leadQueueControlsChanged();
});
$("lead-sort-direction").addEventListener("click", () => {
  state.leadSortDirection = state.leadSortDirection === "desc" ? "asc" : "desc";
  leadQueueControlsChanged();
});
$("select-page-leads").addEventListener("change", (event) => {
  const pageLeads = visibleLeadPage();
  for (const lead of pageLeads) {
    if (!lead.id) continue;
    if (event.currentTarget.checked) state.selectedLeadIds.add(lead.id);
    else state.selectedLeadIds.delete(lead.id);
  }
  renderRun(state.currentRun);
});
$("bulk-update-leads").addEventListener("click", () => {
  bulkUpdateSelectedLeads().catch((error) => {
    $("run-status").textContent = error.message;
  });
});
$("save-lead-view").addEventListener("click", () => {
  saveCurrentLeadView().catch((error) => {
    $("run-status").textContent = error.message;
  });
});
$("lead-view-select").addEventListener("change", (event) => applyLeadView(event.currentTarget.value));
["query", "seed-text", "max-companies"].forEach((id) => {
  $(id).addEventListener("input", clearCandidatePreview);
});

$("preview-button").addEventListener("click", async () => {
  const button = $("preview-button");
  const status = $("run-status");
  button.disabled = true;
  status.textContent = "Discovering candidate companies...";
  try {
    const payload = await api("/api/search", {
      method: "POST",
      body: JSON.stringify(runOptionsPayload()),
    });
    state.previewCandidates = payload.candidates || [];
    renderCandidatePreview(state.previewCandidates, payload.warnings || []);
    status.textContent = state.previewCandidates.length
      ? `Previewed ${state.previewCandidates.length} candidates. Uncheck weak fits before running.`
      : "No candidates found.";
  } catch (error) {
    status.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

$("run-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("run-button");
  const status = $("run-status");
  button.disabled = true;
  status.textContent = "Running discovery, enrichment, and scoring...";
  try {
    const selectedCandidates = selectedPreviewCandidates();
    if (state.previewCandidates.length && !selectedCandidates.length) {
      throw new Error("Select at least one preview candidate or clear the preview before running.");
    }
    const requestPayload = runOptionsPayload();
    if (selectedCandidates.length) {
      requestPayload.candidates = selectedCandidates;
      requestPayload.max_companies = selectedCandidates.length;
    }
    const run = await api("/api/runs", {
      method: "POST",
      body: JSON.stringify(requestPayload),
    });
    state.currentRun = run;
    state.selectedLeadId = null;
    state.prospectFocusLeadId = null;
    resetRunDerivedState();
    state.previewCandidates = [];
    renderCandidatePreview();
    renderRun(run);
    status.textContent = `Completed ${run.leads.length} leads.`;
    activateView("leads");
  } catch (error) {
    status.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

$("source-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("source-status").textContent = "Saving source...";
  try {
    const payload = await api("/api/sources", {
      method: "POST",
      body: JSON.stringify({
        name: $("source-name").value,
        type: $("source-type").value,
        value: $("source-value").value,
        source_group: $("source-group").value,
        schedule: $("source-schedule").value,
        enabled: true,
      }),
    });
    state.sources = payload.sources || state.sources;
    state.sourceCoverage = payload.coverage || state.sourceCoverage;
    state.activeSourceScan = null;
    renderSources();
    $("source-form").reset();
    $("source-status").textContent = `Saved source ${payload.source?.name || ""}.`;
  } catch (error) {
    $("source-status").textContent = error.message;
  }
});
$("source-csv-file").addEventListener("change", (event) => {
  loadSourceCsvFile(event).catch((error) => {
    $("source-status").textContent = error.message;
  });
});

$("criteria-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("criteria-save");
  button.disabled = true;
  $("criteria-status").textContent = "Saving criteria...";
  try {
    const payload = await api("/api/criteria", {
      method: "POST",
      body: JSON.stringify({ markdown: $("criteria-markdown").value }),
    });
    renderCriteria(payload.criteria || {}, payload.versions || state.criteriaVersions, payload.lint || null);
    $("criteria-status").textContent = `Saved criteria hash ${payload.criteria?.hash || ""}`;
  } catch (error) {
    $("criteria-status").textContent = error.message;
  } finally {
    updateCriteriaEditorControls();
  }
});

$("criteria-markdown").addEventListener("beforeinput", () => {
  if (state.criteriaSuppressHistory) return;
  pushCriteriaUndo($("criteria-markdown").value);
});

$("criteria-markdown").addEventListener("input", () => {
  if (!state.criteriaSuppressHistory) state.criteriaRedoStack = [];
  renderCriteriaLint(lintCriteriaMarkdown($("criteria-markdown").value));
  $("criteria-status").textContent = "Unsaved criteria edits.";
  updateCriteriaEditorControls();
});

$("criteria-undo").addEventListener("click", undoCriteriaEdit);
$("criteria-redo").addEventListener("click", redoCriteriaEdit);

$("criteria-format").addEventListener("click", () => {
  const lint = lintCriteriaMarkdown($("criteria-markdown").value);
  setCriteriaMarkdown(lint.formatted, { capture: true });
  $("criteria-status").textContent = lint.changed ? "Formatted locally. Save to publish the formatted criteria." : "Criteria formatting is already clean.";
});

$("criteria-lint").addEventListener("click", async () => {
  $("criteria-status").textContent = "Linting criteria...";
  try {
    const lint = await api("/api/criteria/lint", {
      method: "POST",
      body: JSON.stringify({ markdown: $("criteria-markdown").value }),
    });
    renderCriteriaLint(lint);
    $("criteria-status").textContent = `Lint complete: ${lint.error_count || 0} errors, ${lint.warning_count || 0} warnings.`;
  } catch (error) {
    renderCriteriaLint(lintCriteriaMarkdown($("criteria-markdown").value));
    $("criteria-status").textContent = error.message;
  }
});
$("criteria-impact").addEventListener("click", previewCriteriaImpact);

$("criteria-version-select").addEventListener("change", () => loadSelectedCriteriaVersion());
$("criteria-version-back").addEventListener("click", () => loadSelectedCriteriaVersion(-1));
$("criteria-version-forward").addEventListener("click", () => loadSelectedCriteriaVersion(1));

$("criteria-restore").addEventListener("click", async () => {
  const version = selectedCriteriaVersion();
  if (!version) return;
  $("criteria-status").textContent = "Restoring criteria version...";
  try {
    const payload = await api("/api/criteria/restore", {
      method: "POST",
      body: JSON.stringify({ id: version.id || version.hash }),
    });
    renderCriteria(payload.criteria || {}, payload.versions || state.criteriaVersions, payload.lint || null);
    $("criteria-status").textContent = `Restored criteria hash ${payload.criteria?.hash || ""}`;
  } catch (error) {
    $("criteria-status").textContent = error.message;
  }
});

$("research-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const answerRoot = $("research-answer");
  if (!state.currentRun) {
    answerRoot.innerHTML = "Run research first.";
    return;
  }
  answerRoot.innerHTML = "Researching stored evidence...";
  const payload = await api("/api/research", {
    method: "POST",
    body: JSON.stringify({
      run_id: state.currentRun.id,
      question: $("research-question").value,
    }),
  });
    answerRoot.innerHTML = `<div class="detail-stack">
    <div class="detail-section">
      <h2>Answer</h2>
      <p class="muted">${escapeHtml(researchProviderLabel(payload))}</p>
      <div class="research-answer-text">${escapeHtml(payload.answer || "")}</div>
    </div>
    ${researchMetadataSection(payload.metadata_used)}
    <div class="detail-section">
      <h2>Matched Leads</h2>
      <div class="tag-list">${(payload.matched_leads || []).map((item) => `<span class="tag">${escapeHtml(item)}</span>`).join("") || "<span class=\"tag\">none</span>"}</div>
    </div>
    <div class="detail-section">
      <h2>Citations</h2>
      ${(payload.citations || []).map((item) => `<div class="evidence-item">
        <a href="${escapeAttribute(item.url || "#")}" target="_blank" rel="noreferrer">${escapeHtml(item.company || item.url || "")}</a>
        <div class="tag-list">${[item.source_type, item.page_category, ...(item.signal_tags || [])]
          .filter(Boolean)
          .map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`)
          .join("")}</div>
        <p>${escapeHtml(item.snippet || "")}</p>
      </div>`).join("") || "<p>No direct citations found.</p>"}
    </div>
  </div>`;
});

function researchMetadataSection(metadata = {}) {
  const groups = [
    ["Signals", metadata.signal_tags],
    ["Sources", metadata.source_types],
    ["Categories", metadata.page_categories],
    ["Coverage", metadata.coverage],
    ["Personas", metadata.persona_titles],
    ["Criteria", metadata.criteria_hashes],
  ];
  const rows = groups
    .filter(([, values]) => values && values.length)
    .map(([label, values]) => `<div class="metadata-chip-row"><strong>${escapeHtml(label)}</strong><div class="tag-list">${values
      .slice(0, 10)
      .map((value) => `<span class="tag">${escapeHtml(value)}</span>`)
      .join("")}</div></div>`)
    .join("");
  if (!rows) return "";
  return `<div class="detail-section">
    <h2>Metadata Used</h2>
    <div class="metadata-chip-list">${rows}</div>
  </div>`;
}

function researchProviderLabel(payload) {
  if (payload.provider === "k2") {
    const parts = ["K2-backed research"];
    if (payload.corpus_id) parts.push(`corpus ${payload.corpus_id}`);
    if (payload.model) parts.push(String(payload.model));
    return parts.join(" · ");
  }
  return "Local stored-evidence research";
}

async function runK2PipelineAction(action, buttonId) {
  const confirmations = {
    apply: "Apply the K2 PipelineSpec now? This can create or update K2 agents, feeds, and subscriptions.",
    trigger: "Trigger the K2 PipelineSpec now? This can enqueue K2 feed and agent jobs.",
    backfill: "Backfill the K2 PipelineSpec for the last 30 days? This can enqueue multiple K2 jobs.",
  };
  if (confirmations[action] && !window.confirm(confirmations[action])) return;
  const button = $(buttonId);
  if (button) button.disabled = true;
  try {
    const result = await api("/api/k2-workspace/pipeline", {
      method: "POST",
      body: JSON.stringify({ action }),
    });
    renderK2PipelineActionResult(result);
  } catch (error) {
    renderK2PipelineActionResult({
      status: "error",
      action,
      error: error.message,
      result: { error: error.message },
      workspace: state.currentK2WorkspaceStatus || { warnings: [error.message] },
    });
  } finally {
    if (button) button.disabled = false;
  }
}

$("k2-preview").addEventListener("click", async () => {
  if (!state.currentRun) return;
  state.currentManifest = await api(`/api/runs/${state.currentRun.id}/k2-manifest`);
  renderK2Panel(state.currentManifest);
});

$("k2-workspace-status").addEventListener("click", async () => {
  const status = await api("/api/k2-workspace");
  renderK2WorkspaceStatus(status);
});

$("k2-pipeline-dry-run").addEventListener("click", () => runK2PipelineAction("dry_run", "k2-pipeline-dry-run"));
$("k2-pipeline-apply").addEventListener("click", () => runK2PipelineAction("apply", "k2-pipeline-apply"));
$("k2-pipeline-trigger").addEventListener("click", () => runK2PipelineAction("trigger", "k2-pipeline-trigger"));
$("k2-pipeline-backfill").addEventListener("click", () => runK2PipelineAction("backfill", "k2-pipeline-backfill"));

$("k2-export").addEventListener("click", async () => {
  if (!state.currentRun) return;
  state.currentManifest = await api(`/api/runs/${state.currentRun.id}/k2-export`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  renderK2Panel(state.currentManifest);
});

$("k2-sync-dry-run").addEventListener("click", async () => {
  if (!state.currentRun) return;
  const result = await api(`/api/runs/${state.currentRun.id}/k2-sync`, {
    method: "POST",
    body: JSON.stringify({ apply: false }),
  });
  renderK2SyncResult(result);
});

$("k2-sync-apply").addEventListener("click", async () => {
  if (!state.currentRun) return;
  if (!window.confirm("Apply this run to K2 now? This can create or update remote project and corpus data.")) return;
  try {
    const result = await api(`/api/runs/${state.currentRun.id}/k2-sync`, {
      method: "POST",
      body: JSON.stringify({ apply: true }),
    });
    renderK2SyncResult(result);
  } catch (error) {
    renderK2SyncResult({ status: "error", reason: error.message });
  }
});

$("run-eval").addEventListener("click", async () => {
  if (!state.currentRun) return;
  const button = $("run-eval");
  button.disabled = true;
  $("eval-panel").className = "detail-panel";
  $("eval-panel").textContent = "Running deterministic ICP eval...";
  try {
    const payload = await api("/api/evals/runs", {
      method: "POST",
      body: JSON.stringify({ run_id: state.currentRun.id }),
    });
    state.evalSummary = payload.summary || state.evalSummary;
    renderEvalPanel(state.evalSummary);
    renderSummary(state.currentRun, state.currentRun.leads || []);
  } catch (error) {
    $("eval-panel").className = "detail-panel empty";
    $("eval-panel").textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

$("download-evals").addEventListener("click", () => {
  downloadWithAuth("/api/evals/runs.csv", "icp-eval-runs.csv", "text/csv").catch((error) => {
    $("eval-panel").className = "detail-panel empty";
    $("eval-panel").textContent = error.message;
  });
});

$("refresh-prospects").addEventListener("click", () => {
  refreshProspects().catch((error) => {
    $("prospect-summary").className = "detail-panel empty";
    $("prospect-summary").textContent = error.message;
  });
});

$("download-prospects").addEventListener("click", () => {
  if (!state.currentRun) return;
  downloadWithAuth(`/api/runs/${state.currentRun.id}/prospects.csv`, `${state.currentRun.id}-prospects.csv`, "text/csv").catch((error) => {
    $("prospect-summary").className = "detail-panel empty";
    $("prospect-summary").textContent = error.message;
  });
});

$("download-prospects-json").addEventListener("click", () => {
  if (!state.currentRun) return;
  downloadWithAuth(`/api/runs/${state.currentRun.id}/prospects`, `${state.currentRun.id}-prospects.json`, "application/json").catch((error) => {
    $("prospect-summary").className = "detail-panel empty";
    $("prospect-summary").textContent = error.message;
  });
});

loadState().catch((error) => {
  $("run-status").textContent = error.message;
});
