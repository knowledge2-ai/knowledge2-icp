import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Loader2, Play, History } from 'lucide-react'
import { toast } from 'sonner'
import { fetchState, createRun, hasSession } from '../api'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { useActiveRun, resolveRunId } from '../context/RunContext'
import { cn } from '../lib/utils'

const TIER_KEYS = ['A', 'B', 'C', 'Reject']

export function RunsView() {
  const queryClient = useQueryClient()
  const { activeRunId, setActiveRunId } = useActiveRun()
  const { data: state, isLoading, isError, error } = useQuery({ queryKey: ['state'], queryFn: fetchState })

  const runs = state?.runs || []
  const effectiveRunId = resolveRunId(activeRunId, state)
  const authed = hasSession()

  const mutation = useMutation({
    mutationFn: createRun,
    onSuccess: (run) => {
      toast.success(`Run created — ${run?.leads?.length ?? 0} leads`)
      if (run?.id) setActiveRunId(run.id)
      queryClient.invalidateQueries({ queryKey: ['state'] })
    },
    onError: (err) => {
      if (err?.status === 401 || err?.status === 403) {
        toast.error('Creating a run requires an admin session — unlock with a token (top-right).')
      } else {
        toast.error(err?.message || 'Run failed')
      }
    },
  })

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading runs…</p>
  if (isError) return <p className="text-sm text-score-low">Failed to load runs: {error?.message}</p>

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
      <Card>
        <CardHeader className="flex-row items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2">
            <History className="h-4 w-4" /> Runs
          </CardTitle>
          <span className="text-xs text-muted-foreground">{runs.length} total</span>
        </CardHeader>
        <CardContent className="space-y-2">
          {runs.length === 0 && (
            <p className="text-sm text-muted-foreground">No runs yet. Start one on the right.</p>
          )}
          {runs.map((run) => (
            <RunRow
              key={run.id}
              run={run}
              active={run.id === effectiveRunId}
              onSelect={() => setActiveRunId(run.id)}
            />
          ))}
        </CardContent>
      </Card>

      <NewRunForm authed={authed} mutation={mutation} />
    </div>
  )
}

function RunRow({ run, active, onSelect }) {
  const tiers = run.tier_counts || {}
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        'w-full rounded-xl border px-4 py-3 text-left transition-colors',
        active
          ? 'border-primary bg-[var(--color-surface-soft)]'
          : 'border-[var(--color-border)] hover:bg-[var(--color-surface-soft)]',
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="truncate font-medium text-foreground">{run.query || '(seeded run)'}</span>
        {active && <CheckCircle2 className="h-4 w-4 shrink-0 text-primary" />}
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
        <span className="font-mono">{run.id}</span>
        <span>{run.lead_count} leads</span>
        {run.created_at && <span>{formatDate(run.created_at)}</span>}
        <span className="flex gap-1.5">
          {TIER_KEYS.filter((t) => tiers[t]).map((t) => (
            <span key={t} className="font-numeric">
              {t}:{tiers[t]}
            </span>
          ))}
        </span>
      </div>
    </button>
  )
}

function NewRunForm({ authed, mutation }) {
  const [query, setQuery] = useState('')
  const [maxCompanies, setMaxCompanies] = useState(20)
  const [fetch, setFetch] = useState(true)

  const submit = (e) => {
    e.preventDefault()
    mutation.mutate({
      query: query.trim(),
      max_companies: Number(maxCompanies) || 20,
      fetch,
      include_github: false,
      use_apollo: false,
    })
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Play className="h-4 w-4" /> New run
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-3">
          <label className="block text-sm">
            <span className="mb-1 block text-xs text-muted-foreground">ICP brief / discovery query</span>
            <textarea
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              rows={4}
              placeholder="e.g. Vertical SaaS companies serving construction with an AI roadmap"
              className="w-full rounded-xl border border-[var(--color-border-strong)] bg-[var(--color-surface-soft)] px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block text-xs text-muted-foreground">Max companies</span>
            <Input
              type="number"
              min={1}
              max={100}
              value={maxCompanies}
              onChange={(e) => setMaxCompanies(e.target.value)}
              className="w-28"
            />
          </label>
          <label className="flex items-center gap-2 text-sm text-foreground">
            <input type="checkbox" checked={fetch} onChange={(e) => setFetch(e.target.checked)} />
            Fetch website evidence
          </label>
          {!authed && (
            <p className="text-xs text-score-medium">
              Read-only demo — unlock with an admin token (top-right) to start a run.
            </p>
          )}
          <Button type="submit" disabled={mutation.isPending || !query.trim()} className="w-full">
            {mutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" /> Running…
              </>
            ) : (
              <>
                <Play className="h-4 w-4" /> Start run
              </>
            )}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}

function formatDate(value) {
  const ms = Date.parse(value)
  return Number.isNaN(ms) ? value : new Date(ms).toLocaleDateString()
}
