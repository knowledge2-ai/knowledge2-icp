import { useState } from 'react'
import { Sidebar } from './components/Sidebar'
import { TopBar } from './components/TopBar'
import { LeadsView } from './views/LeadsView'
import { RunsView } from './views/RunsView'
import { ResearchView } from './views/ResearchView'
import { PlaceholderView } from './views/PlaceholderView'
import { RunProvider } from './context/RunContext'

// Tab-routed shell (no router dependency — the legacy SPA used the same flat
// tab model). Each view fetches its own data via React Query.
const VIEWS = {
  leads: LeadsView,
  prospects: () => <PlaceholderView title="Prospects" note="Reveal-on-demand contacts per qualified account." />,
  runs: RunsView,
  research: ResearchView,
  sources: () => <PlaceholderView title="Sources" note="CSV / portfolio source imports and coverage." />,
  mining: () => <PlaceholderView title="Mining" note="Metadata-filtered corpus search and lookalikes." />,
  evals: () => <PlaceholderView title="Evals" note="Scoring-quality eval runs (admin session required)." />,
  criteria: () => <PlaceholderView title="Criteria" note="Versioned ICP rubric editor." />,
  setup: () => <PlaceholderView title="Setup" note="Providers, settings, and diagnostics." />,
}

export default function App() {
  const [active, setActive] = useState('leads')
  const [, setSessionTick] = useState(0)
  const ViewComponent = VIEWS[active] || VIEWS.leads

  return (
    <RunProvider>
      <div className="min-h-screen bg-[var(--color-background)] text-foreground font-sans md:pl-64">
        <Sidebar active={active} onSelect={setActive} />
        <TopBar active={active} onSessionChange={() => setSessionTick((n) => n + 1)} />
        <main className="mx-auto max-w-7xl px-6 py-6">
          <ViewComponent />
        </main>
      </div>
    </RunProvider>
  )
}
