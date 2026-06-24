import { Badge } from './ui/badge'

// Maps a qualifier tier (A / B / C / Reject) to the K2 score palette.
const TIER_VARIANT = {
  A: 'success',
  B: 'default',
  C: 'warning',
  Reject: 'danger',
}

export function TierBadge({ tier }) {
  const label = tier || '—'
  return <Badge variant={TIER_VARIANT[tier] || 'secondary'}>{label}</Badge>
}
