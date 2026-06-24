import {
  Users,
  UserSearch,
  Play,
  Telescope,
  Database,
  Pickaxe,
  FlaskConical,
  SlidersHorizontal,
  Settings,
} from 'lucide-react'
import { cn } from '../lib/utils'

// The nine workspace views, in the same order as the legacy SPA's tab bar.
export const NAV_ITEMS = [
  { id: 'leads', label: 'Leads', icon: Users },
  { id: 'prospects', label: 'Prospects', icon: UserSearch },
  { id: 'runs', label: 'Runs', icon: Play },
  { id: 'research', label: 'Research', icon: Telescope },
  { id: 'sources', label: 'Sources', icon: Database },
  { id: 'mining', label: 'Mining', icon: Pickaxe },
  { id: 'evals', label: 'Evals', icon: FlaskConical },
  { id: 'criteria', label: 'Criteria', icon: SlidersHorizontal },
  { id: 'setup', label: 'Setup', icon: Settings },
]

export function Sidebar({ active, onSelect }) {
  return (
    <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 flex-col border-r border-[var(--color-border)] bg-[var(--color-surface)] md:flex">
      <div className="flex h-16 items-center gap-2 border-b border-[var(--color-border)] px-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-primary text-primary-foreground font-heading font-bold">
          IC
        </div>
        <div className="font-heading text-sm font-semibold leading-tight">
          ICP Console
          <div className="text-xs font-normal text-muted-foreground">GTM pipeline</div>
        </div>
      </div>
      <nav className="flex-1 space-y-1 overflow-y-auto p-3">
        {NAV_ITEMS.map(({ id, label, icon: Icon }) => {
          const isActive = id === active
          return (
            <button
              key={id}
              type="button"
              onClick={() => onSelect(id)}
              className={cn(
                'flex w-full items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-primary/15 text-primary'
                  : 'text-muted-foreground hover:bg-[var(--color-surface-soft)] hover:text-foreground',
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {label}
            </button>
          )
        })}
      </nav>
      <div className="border-t border-[var(--color-border)] p-4 text-xs text-muted-foreground">
        Vertical-SaaS ICP · discovery → qualify → outreach
      </div>
    </aside>
  )
}
