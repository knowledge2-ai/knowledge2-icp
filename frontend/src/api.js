// Thin API client mirroring the legacy SPA's auth model: an admin token is
// exchanged once at /api/auth/session for a session token kept in localStorage
// and sent as `Authorization: Bearer <token>` on every call. Without a session,
// the read-only demo endpoints still return data (the public-read allowlist in
// web.py), so the console renders leads/sources/runs unauthenticated.

const AUTH_SESSION_KEY = 'knowledge2.icp.sessionToken'
const LEGACY_AUTH_TOKEN_KEY = 'knowledge2.icp.adminToken'

export function getSessionToken() {
  return localStorage.getItem(AUTH_SESSION_KEY) || ''
}

export function hasSession() {
  return Boolean(getSessionToken())
}

export function clearSession() {
  localStorage.removeItem(AUTH_SESSION_KEY)
  localStorage.removeItem(LEGACY_AUTH_TOKEN_KEY)
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

async function authFetch(path, options = {}) {
  const headers = { ...(options.headers || {}) }
  if (!(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json'
  }
  const token = getSessionToken()
  if (token) headers.Authorization = `Bearer ${token}`
  return fetch(path, { ...options, headers })
}

export async function api(path, options = {}) {
  const response = await authFetch(path, options)
  const text = await response.text()
  const payload = text ? JSON.parse(text) : {}
  if (!response.ok) {
    throw new ApiError(payload.error || `Request failed: ${response.status}`, response.status)
  }
  return payload
}

export async function apiCsv(path) {
  const response = await authFetch(path, { headers: { Accept: 'text/csv' } })
  if (!response.ok) throw new ApiError(`Export failed: ${response.status}`, response.status)
  return response.text()
}

/** Exchange an admin token for a session token and persist it. */
export async function createSession(adminToken) {
  const response = await fetch('/api/auth/session', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token: adminToken }),
  })
  const payload = await response.json()
  if (!response.ok) throw new ApiError(payload.error || `Session failed: ${response.status}`, response.status)
  localStorage.setItem(AUTH_SESSION_KEY, payload.session_token)
  localStorage.removeItem(LEGACY_AUTH_TOKEN_KEY)
  return payload
}

// --- Endpoint helpers (named to match web.py routes) -----------------------

export const fetchState = () => api('/api/state')
export const fetchRun = (runId) => api(`/api/runs/${encodeURIComponent(runId)}`)
export const fetchRunProspects = (runId) => api(`/api/runs/${encodeURIComponent(runId)}/prospects`)
export const fetchAccount = (runId, key) =>
  api(`/api/runs/${encodeURIComponent(runId)}/accounts/${encodeURIComponent(key)}`)
export const fetchCriteria = () => api('/api/criteria')
export const fetchCriteriaVersions = () => api('/api/criteria/versions')
export const fetchSources = () => api('/api/sources')
export const fetchExpansionRuns = () => api('/api/expansion/runs')
export const fetchK2Workspace = () => api('/api/k2-workspace')
export const fetchSettings = () => api('/api/settings')
export const fetchMiningProfiles = () => api('/api/mining/profiles')
export const runMiningSearch = (body) =>
  api('/api/mining/search', { method: 'POST', body: JSON.stringify(body) })
export const runLookalikes = (body) =>
  api('/api/mining/lookalikes', { method: 'POST', body: JSON.stringify(body) })
export const fetchEvalRuns = () => api('/api/evals/runs')

export const createRun = (body) =>
  api('/api/runs', { method: 'POST', body: JSON.stringify(body) })
export const runResearch = (body) =>
  api('/api/research', { method: 'POST', body: JSON.stringify(body) })
