import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'

// Temporary stub for views not yet ported from the legacy SPA. Keeps the shell
// navigable while each view is migrated to React in turn.
export function PlaceholderView({ title, note }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">{note}</p>
        <p className="mt-3 text-xs text-muted-foreground">
          This view is being migrated to the new K2-styled console. The legacy implementation remains
          available until the port reaches parity.
        </p>
      </CardContent>
    </Card>
  )
}
