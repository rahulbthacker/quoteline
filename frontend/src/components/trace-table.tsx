import { useQuery } from '@tanstack/react-query'
import { api, type Trace } from '../lib/api'

const inr = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
})

function StatusPill({ trace }: { trace: Trace }) {
  const ok = trace.status === 'ok'
  return (
    <span
      title={trace.error ?? undefined}
      className={`rounded-full px-2 py-0.5 text-meta font-medium ${
        ok ? 'bg-success-bg text-success-ink' : 'bg-danger-bg text-danger-ink'
      }`}
    >
      {ok ? 'ok' : 'failed'}
    </span>
  )
}

export function TraceTable() {
  const { data, error, isPending } = useQuery({
    queryKey: ['traces'],
    queryFn: api.traces,
    refetchInterval: 5000,
  })

  if (isPending) return <p className="text-ink-muted">Loading model calls…</p>
  if (error)
    return (
      <p className="rounded-card border border-warning-border bg-warning-bg p-3 text-warning-ink">
        Cannot reach the API ({error.message}). Start it with <code>make api</code>.
      </p>
    )
  if (data.length === 0)
    return (
      <p className="text-ink-muted">
        No model calls yet. Run <code className="font-mono">make check-a</code>.
      </p>
    )

  const num = 'px-3 text-right font-mono'
  return (
    <div className="overflow-x-auto rounded-card border border-border bg-surface-1">
      <table className="w-full border-collapse text-table">
        <thead>
          <tr className="h-10 bg-surface-2 text-left text-meta font-medium uppercase text-ink-muted">
            <th className="px-3">Role</th>
            <th className="px-3">Model</th>
            <th className="px-3">Prompt</th>
            <th className="px-3">Status</th>
            <th className={num}>Try</th>
            <th className={num}>In</th>
            <th className={num}>Out</th>
            <th className={num}>Latency</th>
            <th className={num}>Cost</th>
          </tr>
        </thead>
        <tbody>
          {data.map((trace) => (
            <tr key={trace.call_id} className="h-10 border-t border-border">
              <td className="px-3">{trace.role}</td>
              <td className="px-3 font-mono">{trace.served_model ?? trace.model}</td>
              <td className="px-3 font-mono text-ink-muted">{trace.prompt_version}</td>
              <td className="px-3">
                <StatusPill trace={trace} />
              </td>
              <td className={num}>{trace.attempt}</td>
              <td className={num}>{trace.input_tokens ?? '–'}</td>
              <td className={num}>{trace.output_tokens ?? '–'}</td>
              <td className={num}>{trace.latency_ms} ms</td>
              <td className={num}>
                {trace.status !== 'ok' ? '–' : trace.cost_inr === null ? 'unpriced' : inr.format(trace.cost_inr)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
