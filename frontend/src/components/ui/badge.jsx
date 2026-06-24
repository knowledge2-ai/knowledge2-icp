import { cva } from 'class-variance-authority'
import { cn } from '../../lib/utils'

const badgeVariants = cva(
  'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors',
  {
    variants: {
      variant: {
        default: 'border-transparent bg-primary/15 text-primary',
        secondary: 'border-transparent bg-[var(--color-surface-strong)] text-foreground',
        outline: 'border-[var(--color-border-strong)] text-foreground',
        success: 'border-transparent bg-score-high-bg text-score-high',
        warning: 'border-transparent bg-score-medium-bg text-score-medium',
        danger: 'border-transparent bg-score-low-bg text-score-low',
      },
    },
    defaultVariants: { variant: 'default' },
  },
)

export function Badge({ className, variant, ...props }) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />
}

export { badgeVariants }
