import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowUpDown, Inbox } from 'lucide-react'
import { fetchState, fetchRun } from '../api'
import { Card, CardContent } from '../components/ui/card'
import { TierBadge } from '../components/TierBadge'
import { useActiveRun, resolveRunId } from '../context/RunContext'
import { cn } from '../lib/utils'

const TIER_ORDER = { A: 0, B: 1, C: 2, Reject: 3 }

function leadFields(lead) {
  const score = lead.score || {}
  const company = score.company || {}
  return {
    id: lead.id || company.domain,
    name: company.company || company.domain || '—',
    domain: company.domain || '',
    category: company.category || lead.category || '',
    tier: score.tier || '—',
    total: typeof score.total_score === 'number' ? score.total_score : null,
    action: score.next_action || '',
  }
}

export function LeadsView() {
  const { activeRunId } = useActiveRun()
  const { data, isLoading, isError, error } = useQuery({ queryKey: ['state'], queryFn: fetchState })
  const [sortKey, setSortKey] = useState('score')

  const runId = resolveRunId(activeRunId, data)
  const landingRun = data?.latest_run
  const needsFetch = Boolean(runId) && runId !== landingRun?.id
  // Only hit /api/runs/{id} when the selected run isn't the one already inlined
  // in /api/state (the landing run), so the common case stays a single request.
  const selected = useQuery({
    queryKey: ['run', runId],
    queryFn: () => fetchRun(runId),
    enabled: needsFetch,
  })

  const run = needsFetch ? selected.data : landingRun
  const leads = useMemo(() => (run?.leads || []).map(leadFields), [run])

  const sorted = useMemo(() => {
    const rows = [...leads]
    if (sortKey === 'score') {
      rows.sort((a, b) => (b.total ?? -1) - (a.total ?? -1))
    } else if (sortKey === 'tier') {
      rows.sort((a, b) => (TIER_ORDER[a.tier] ?? 9) - (TIER_ORDER[b.tier] ?? 9))
    } else if (sortKey === 'name') {
      rows.sort((a, b) => a.name.localeCompare(b.name))
    }
    return rows
  }, [leads, sortKey])

  const tierCounts = useMemo(() => {
    const counts = { A: 0, B: 0, C: 0, Reject: 0 }
    for (const l of leads) if (l.tier in counts) counts[l.tier] += 1
    return counts
  }, [leads])

  if (isLoading || (needsFetch && selected.isLoading)) return <SkeletonTable />
  if (isError) {
    return (
      <Card>
        <CardContent className="p-6 text-sm text-score-low">
          Failed to load leads: {error?.message}
        </CardContent>
      </Card>
    )
  }
  if (!run || leads.length === 0) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-2 p-12 text-center text-muted-foreground">
          <Inbox className="h-8 w-8" />
          <p className="text-sm">No leads yet. Kick off a discovery run from the Research tab.</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <SummaryStat label="Leads" value={leads.length} />
        <SummaryStat label="Tier A" value={tierCounts.A} accent="text-score-high" />
        <SummaryStat label="Tier B" value={tierCounts.B} accent="text-primary" />
        <SummaryStat label="Tier C" value={tierCounts.C} accent="text-score-medium" />
        <SummaryStat label="Reject" value={tierCounts.Reject} accent="text-score-low" />
        <div className="ml-auto text-xs text-muted-foreground">
          Run <span className="font-mono">{run.id}</span>
        </div>
      </div>

      <Card>
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--color-border)] text-left text-xs uppercase tracking-wide text-muted-foreground">
                <SortableTh label="Company" active={sortKey === 'name'} onClick={() => setSortKey('name')} />
                <th className="px-4 py-3 font-medium">Vertical</th>
                <SortableTh label="Tier" active={sortKey === 'tier'} onClick={() => setSortKey('tier')} />
                <SortableTh label="Score" active={sortKey === 'score'} onClick={() => setSortKey('score')} align="right" />
                <th className="px-4 py-3 font-medium">Next action</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((lead) => (
                <tr
                  key={lead.id}
                  className="border-b border-[var(--color-border)] last:border-0 transition-colors hover:bg-[var(--color-surface-soft)]"
                >
                  <td className="px-4 py-3">
                    <div className="font-medium text-foreground">{lead.name}</div>
                    {lead.domain && <div className="text-xs text-muted-foreground">{lead.domain}</div>}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{lead.category || '—'}</td>
                  <td className="px-4 py-3"><TierBadge tier={lead.tier} /></td>
                  <td className="px-4 py-3 text-right font-numeric font-semibold">
                    {lead.total ?? '—'}
                  </td>
                  <td className="px-4 py-3 max-w-md truncate text-xs text-muted-foreground" title={lead.action}>
                    {lead.action || '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  )
}

function SummaryStat({ label, value, accent }) {
  return (
    <div className="rounded-2xl border border-[var(--color-border)] bg-card px-4 py-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={cn('font-numeric text-xl font-semibold', accent)}>{value}</div>
    </div>
  )
}

function SortableTh({ label, active, onClick, align = 'left' }) {
  return (
    <th className={cn('px-4 py-3 font-medium', align === 'right' && 'text-right')}>
      <button
        type="button"
        onClick={onClick}
        className={cn(
          'inline-flex items-center gap-1 hover:text-foreground',
          active && 'text-foreground',
        )}
      >
        {label}
        <ArrowUpDown className="h-3 w-3" />
      </button>
    </th>
  )
}

function SkeletonTable() {
  return (
    <Card>
      <CardContent className="space-y-3 p-6">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-10 animate-pulse rounded-xl bg-[var(--color-surface-soft)]" />
        ))}
      </CardContent>
    </Card>
  )
}
