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
  criteriaVersions: [],
  criteriaUndoStack: [],
  criteriaRedoStack: [],
  criteriaSuppressHistory: false,
  criteriaSavedHash: "",
};

const AUTH_TOKEN_KEY = "knowledge2.icp.adminToken";
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
}

async function authFetch(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const token = localStorage.getItem(AUTH_TOKEN_KEY) || "";
  if (token) headers.Authorization = `Bearer ${token}`;
  return fetch(path, {
    ...options,
    headers,
  });
}

async function api(path, options = {}) {
  const response = await authFetch(path, options);
  const payload = await response.json();
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
  applySeededDefaults();
  renderSeedSummary();
  renderSetup();
  renderRuns(payload.runs || []);
  renderRun(state.currentRun);
}

function initAuthControls() {
  const tokenInput = $("admin-token");
  const saved = localStorage.getItem(AUTH_TOKEN_KEY) || "";
  tokenInput.value = saved;
  $("auth-status").textContent = saved ? "K2 apply token saved in this browser." : "No K2 apply token saved.";
}

function saveAuthToken() {
  const value = $("admin-token").value.trim();
  if (value) {
    localStorage.setItem(AUTH_TOKEN_KEY, value);
    $("auth-status").textContent = "K2 apply token saved in this browser.";
  } else {
    localStorage.removeItem(AUTH_TOKEN_KEY);
    $("auth-status").textContent = "No K2 apply token saved.";
  }
}

function clearAuthToken() {
  localStorage.removeItem(AUTH_TOKEN_KEY);
  $("admin-token").value = "";
  $("auth-status").textContent = "No K2 apply token saved.";
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
  const settings = Object.entries(state.settings || {});
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
      <div class="settings-grid">
        ${settings.map(([key, value]) => `${kv(key.replaceAll("_", " "), formatSettingValue(value))}`).join("")}
      </div>
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
}

function formatSettingValue(value) {
  if (typeof value === "boolean") return value ? "on" : "off";
  if (Array.isArray(value)) return value.join(", ");
  return String(value ?? "");
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
  if (
    state.prospectFocusLeadId &&
    state.prospectFocusLeadId !== ALL_PROSPECTS &&
    !leads.some((lead) => lead.id === state.prospectFocusLeadId)
  ) {
    state.prospectFocusLeadId = null;
  }
  renderSummary(run, leads);
  renderLeadRows(leads);
  renderK2Panel();
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
  ].join("");
}

function metric(label, value) {
  return `<div class="metric"><strong>${escapeHtml(value)}</strong><span>${escapeHtml(label)}</span></div>`;
}

function renderLeadRows(leads) {
  const filter = $("lead-filter").value.toLowerCase();
  const tier = $("tier-filter").value;
  const root = $("lead-rows");
  const filtered = leads.filter((lead) => {
    const haystack = JSON.stringify({
      company: lead.score?.company,
      tier: lead.score?.tier,
      warnings: lead.score?.warnings,
      strategy: lead.strategy,
    }).toLowerCase();
    return (!tier || lead.score?.tier === tier) && (!filter || haystack.includes(filter));
  });
  if (!filtered.length) {
    root.innerHTML = `<div class="lead-row"><span>No matching leads.</span></div>`;
    return;
  }
  root.innerHTML = filtered
    .map((lead) => {
      const company = lead.score.company || {};
      const selected = lead.id === state.selectedLeadId ? " selected" : "";
      return `<div class="lead-row${selected}" data-lead-id="${escapeHtml(lead.id)}">
        <span><strong>${escapeHtml(company.company || "")}</strong><small>${escapeHtml(company.domain || "")}</small></span>
        <span class="${tierClass(lead.score.tier)}">${escapeHtml(lead.score.tier || "")}</span>
        <span class="score">${lead.score.total_score || 0}</span>
        <span>${escapeHtml(lead.strategy?.wedge || lead.score.next_action || "")}</span>
      </div>`;
    })
    .join("");
  root.querySelectorAll("[data-lead-id]").forEach((row) => {
    row.addEventListener("click", () => {
      state.selectedLeadId = row.dataset.leadId;
      state.prospectFocusLeadId = row.dataset.leadId;
      renderRun(state.currentRun);
      activateView("prospects");
    });
  });
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
  renderLeadRows(state.currentRun.leads || []);
  renderLeadDetail((state.currentRun.leads || []).find((item) => item.id === state.selectedLeadId) || null);
  clearAccountDetailState();
  renderAccountDrilldown(currentProspectFocusLead());
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
$("save-admin-token").addEventListener("click", saveAuthToken);
$("clear-admin-token").addEventListener("click", clearAuthToken);
$("lead-filter").addEventListener("input", () => renderRun(state.currentRun));
$("tier-filter").addEventListener("change", () => renderRun(state.currentRun));
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

$("k2-preview").addEventListener("click", async () => {
  if (!state.currentRun) return;
  state.currentManifest = await api(`/api/runs/${state.currentRun.id}/k2-manifest`);
  renderK2Panel(state.currentManifest);
});

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
