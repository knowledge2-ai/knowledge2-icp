import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Loader2, Search, ExternalLink, Sparkles } from 'lucide-react'
import { toast } from 'sonner'
import { fetchState, runResearch, hasSession } from '../api'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { Badge } from '../components/ui/badge'
import { useActiveRun, resolveRunId } from '../context/RunContext'

// Grounded Q&A over the active run's stored evidence. Mirrors the legacy SPA's
// research tab: POST /api/research {run_id, question} -> answer + provider +
// matched leads + citations.
export function ResearchView() {
  const { activeRunId } = useActiveRun()
  const { data: state } = useQuery({ queryKey: ['state'], queryFn: fetchState })
  const runId = resolveRunId(activeRunId, state)
  const [question, setQuestion] = useState('')
  const authed = hasSession()

  const mutation = useMutation({
    mutationFn: () => runResearch({ run_id: runId, question: question.trim() }),
    onError: (err) => {
      if (err?.status === 401 || err?.status === 403) {
        toast.error('Research requires an admin session — unlock with a token (top-right).')
      } else {
        toast.error(err?.message || 'Research failed')
      }
    },
  })

  const result = mutation.data

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4" /> Research the run
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {!runId && (
            <p className="text-sm text-muted-foreground">
              No active run. Select or start one on the Runs tab first.
            </p>
          )}
          <form
            onSubmit={(e) => {
              e.preventDefault()
              if (runId) mutation.mutate()
            }}
            className="space-y-3"
          >
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              rows={3}
              placeholder="e.g. Which leads show the strongest AI-platform signal, and why?"
              className="w-full rounded-xl border border-[var(--color-border-strong)] bg-[var(--color-surface-soft)] px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
            <div className="flex items-center justify-between gap-3">
              <span className="text-xs text-muted-foreground">
                {runId ? <>Grounded in run <span className="font-mono">{runId}</span></> : null}
                {!authed && runId ? ' · read-only demo (unlock to run)' : null}
              </span>
              <Button type="submit" disabled={!runId || mutation.isPending || !question.trim()}>
                {mutation.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" /> Asking…
                  </>
                ) : (
                  <>
                    <Search className="h-4 w-4" /> Ask
                  </>
                )}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {result && <Answer result={result} />}
    </div>
  )
}

function Answer({ result }) {
  const citations = result.citations || []
  const matched = result.matched_leads || []
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-2">
        <CardTitle>Answer</CardTitle>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {result.provider && <Badge variant="outline">{result.provider}</Badge>}
          {result.model && <span className="font-mono">{result.model}</span>}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">{result.answer}</p>

        {matched.length > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-muted-foreground">Matched leads:</span>
            {matched.map((name) => (
              <Badge key={name} variant="secondary">
                {name}
              </Badge>
            ))}
          </div>
        )}

        {citations.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Citations ({citations.length})
            </h3>
            {citations.map((c, i) => (
              <a
                key={`${c.url}-${i}`}
                href={c.url}
                target="_blank"
                rel="noreferrer"
                className="block rounded-xl border border-[var(--color-border)] px-3 py-2 transition-colors hover:bg-[var(--color-surface-soft)]"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium text-foreground">
                    {c.company || c.url}
                  </span>
                  <ExternalLink className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                </div>
                {c.snippet && (
                  <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{c.snippet}</p>
                )}
                <div className="mt-1 flex flex-wrap gap-1.5 text-[10px] text-muted-foreground">
                  {c.source_type && <span>{c.source_type}</span>}
                  {c.page_category && <span>· {c.page_category}</span>}
                </div>
              </a>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
