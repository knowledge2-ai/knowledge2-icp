import { createContext, useContext, useMemo, useState } from 'react'

// Shared "active run" so the Runs, Leads, and Research views agree on which run
// the operator is working in. When nothing is explicitly selected the views fall
// back to the server's landing run (`state.latest_run`), matching the legacy SPA.
const RunContext = createContext(null)

export function RunProvider({ children }) {
  const [activeRunId, setActiveRunId] = useState(null)
  const value = useMemo(() => ({ activeRunId, setActiveRunId }), [activeRunId])
  return <RunContext.Provider value={value}>{children}</RunContext.Provider>
}

export function useActiveRun() {
  const ctx = useContext(RunContext)
  if (!ctx) throw new Error('useActiveRun must be used within a RunProvider')
  return ctx
}

/** Resolve the run id a view should read: explicit selection, else the landing run. */
export function resolveRunId(activeRunId, state) {
  return activeRunId || state?.latest_run?.id || null
}
