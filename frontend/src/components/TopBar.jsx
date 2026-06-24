import { useState } from 'react'
import { ShieldCheck, ShieldAlert, KeyRound } from 'lucide-react'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { NAV_ITEMS } from './Sidebar'
import { createSession, clearSession, hasSession } from '../api'

const TITLES = Object.fromEntries(NAV_ITEMS.map((n) => [n.id, n.label]))

// Sticky glass header. Mirrors the legacy SPA's admin-session model: paste an
// admin token to unlock writes/providers; without one the read-only demo data
// still renders.
export function TopBar({ active, onSessionChange }) {
  const [authed, setAuthed] = useState(hasSession())
  const [token, setToken] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function saveToken() {
    const value = token.trim()
    if (!value) return
    setBusy(true)
    setError('')
    try {
      await createSession(value)
      setAuthed(true)
      setToken('')
      onSessionChange?.(true)
    } catch (err) {
      setError(err.message || 'Session failed')
    } finally {
      setBusy(false)
    }
  }

  function signOut() {
    clearSession()
    setAuthed(false)
    onSessionChange?.(false)
  }

  return (
    <header className="sticky top-0 z-30 border-b border-[var(--color-border)] bg-[var(--color-background)]/80 backdrop-blur-md">
      <div className="flex h-16 items-center justify-between gap-4 px-6">
        <h1 className="font-heading text-lg font-semibold">{TITLES[active] || 'ICP Console'}</h1>
        <div className="flex items-center gap-3">
          {authed ? (
            <>
              <span className="flex items-center gap-1.5 text-sm text-score-high">
                <ShieldCheck className="h-4 w-4" /> Admin session
              </span>
              <Button variant="ghost" size="sm" onClick={signOut}>
                Sign out
              </Button>
            </>
          ) : (
            <>
              <span className="hidden items-center gap-1.5 text-sm text-muted-foreground sm:flex">
                <ShieldAlert className="h-4 w-4" /> Read-only demo
              </span>
              <div className="flex items-center gap-2">
                <Input
                  type="password"
                  placeholder="Admin token"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && saveToken()}
                  className="h-8 w-40"
                />
                <Button size="sm" onClick={saveToken} disabled={busy || !token.trim()}>
                  <KeyRound className="h-4 w-4" /> Unlock
                </Button>
              </div>
            </>
          )}
        </div>
      </div>
      {error && <div className="px-6 pb-2 text-xs text-score-low">{error}</div>}
    </header>
  )
}
