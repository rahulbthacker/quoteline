import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { cn } from '../lib/cn'
import { pct, when } from '../lib/format'
import { Card, Drawer, ErrorNote, Loading, Meta, Pill } from './ui'

function EvalSummary() {
  const { data, error } = useQuery({ queryKey: ['eval'], queryFn: api.evalReport, retry: false })
  if (error || !data)
    return (
      <Card className="p-3 text-ink-muted">
        No eval report yet. Run <code className="font-mono">make eval</code> to score extraction against the golden set.
      </Card>
    )
  const h = data.headline
  const stats: [string, string][] = [
    ['Value accuracy, Claude', pct(h.primary_accuracy.value, 1)],
    ['Value accuracy, Gemini', pct(h.secondary_accuracy.value, 1)],
    ['Line match', pct(h.primary_accuracy.line, 0)],
    ['Agreement', pct(h.agreement_rate, 1)],
    ['Flag precision', pct(h.flag_precision, 0)],
    ['Missed problems', String(h.missed_problems)],
    ['Free-text (judge)', pct(h.free_text_score, 0)],
    ['Quality verdicts', pct(h.quality_verdict_accuracy, 0)],
  ]
  return (
    <Card className="p-3">
      <div className="mb-2 flex items-center justify-between">
        <Meta>Eval against the golden set · {h.rows_scored_per_model} rows per model</Meta>
        <span className="text-meta text-ink-faint">{when(data.generated_at)}</span>
      </div>
      <div className="grid grid-cols-4 gap-2">
        {stats.map(([label, value]) => (
          <div key={label} className="rounded-control bg-surface-2 px-2.5 py-1.5">
            <div className="text-meta text-ink-muted">{label}</div>
            <div className="font-mono text-emphasis font-medium">{value}</div>
          </div>
        ))}
      </div>
      <p className="mt-2 text-meta text-ink-faint">{data.method}</p>
    </Card>
  )
}

export function RunInspector({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { data, error, isPending } = useQuery({ queryKey: ['traces'], queryFn: api.allTraces, enabled: open, refetchInterval: open ? 4000 : false })
  const total = data?.reduce((sum, t) => sum + (t.cost_inr ?? 0), 0) ?? 0
  const failed = data?.filter((t) => t.status !== 'ok').length ?? 0
  const num = 'px-2 py-1.5 text-right font-mono'
  return (
    <Drawer
      open={open}
      onOpenChange={onOpenChange}
      width={980}
      title="Run inspector"
      sub="Every model call ever made by this app: role, model, prompt version, tokens, latency, cost, agreement."
    >
      <div className="space-y-4">
        <EvalSummary />
        {isPending && <Loading />}
        {error && <ErrorNote error={error} />}
        {data && (
          <>
            <div className="flex gap-2">
              <Pill mono>{data.length} calls</Pill>
              <Pill mono tone={failed ? 'danger' : 'success'}>{failed} failed</Pill>
              <Pill mono>₹{total.toFixed(2)} total</Pill>
            </div>
            <Card className="overflow-x-auto">
              <table className="w-full border-collapse text-table">
                <thead>
                  <tr className="bg-surface-2 text-left text-meta font-medium uppercase text-ink-muted">
                    <th className="px-2 py-2">When</th>
                    <th className="px-2">Role</th>
                    <th className="px-2">Model</th>
                    <th className="px-2">Prompt</th>
                    <th className="px-2">Status</th>
                    <th className={num}>In</th>
                    <th className={num}>Out</th>
                    <th className={num}>Latency</th>
                    <th className={num}>Cost</th>
                    <th className={num}>Agree</th>
                  </tr>
                </thead>
                <tbody>
                  {data.map((t) => (
                    <tr key={t.call_id} className={cn('border-t border-border', t.status !== 'ok' && 'bg-danger-bg/40')}>
                      <td className="whitespace-nowrap px-2 py-1.5 text-ink-muted">{when(t.created_at)}</td>
                      <td className="px-2">{t.role}</td>
                      <td className="px-2 font-mono">{t.served_model ?? t.model}</td>
                      <td className="px-2 font-mono text-ink-muted">{t.prompt_version}</td>
                      <td className="px-2">
                        <Pill tone={t.status === 'ok' ? 'success' : 'danger'} title={t.error ?? undefined}>
                          {t.status === 'ok' ? 'ok' : `failed, try ${t.attempt}`}
                        </Pill>
                      </td>
                      <td className={num}>{t.input_tokens ?? '–'}</td>
                      <td className={num}>{t.output_tokens ?? '–'}</td>
                      <td className={num}>{(t.latency_ms / 1000).toFixed(1)}s</td>
                      <td className={num}>{t.status !== 'ok' ? '–' : t.cost_inr === null ? 'unpriced' : `₹${t.cost_inr.toFixed(2)}`}</td>
                      <td className={num}>{t.agreement === null ? '–' : pct(t.agreement, 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          </>
        )}
      </div>
    </Drawer>
  )
}
