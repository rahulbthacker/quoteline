import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Check, Download, Lock } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { AssumptionsBar } from '../components/assumptions-bar'
import { Button, Card, ErrorNote, inputClass, Loading, Meta, PageHeader, Pill } from '../components/ui'
import { api, fileUrl } from '../lib/api'
import { cn } from '../lib/cn'
import { compact, rupees, when } from '../lib/format'
import { usePersona } from '../lib/persona'
import type { AwardComputed, AwardView, Preset, Scenario } from '../lib/types'

const STATUS: Record<string, { label: string; tone: 'neutral' | 'info' | 'success' | 'warning' }> = {
  draft: { label: 'Draft', tone: 'neutral' },
  sent_for_approval: { label: 'Awaiting approval', tone: 'info' },
  approved: { label: 'Approved', tone: 'success' },
  changes_requested: { label: 'Changes requested', tone: 'warning' },
}

function Stat({ label, value, sub, tone }: { label: string; value: string; sub: string; tone?: 'warning' | 'success' }) {
  return (
    <Card className={cn('p-3.5', tone === 'warning' && 'border-warning-border bg-warning-bg text-warning-ink')}>
      <div className={cn('text-table', tone === 'warning' ? '' : 'text-ink-muted')}>{label}</div>
      <div className={cn('font-mono text-[22px] font-medium leading-tight', tone === 'success' && 'text-success-ink')}>{value}</div>
      <div className={cn('text-meta', tone === 'warning' ? '' : 'text-ink-muted')}>{sub}</div>
    </Card>
  )
}

function ScenarioCard({ name, computed, by, onPick, busy, disabled }: { name: string; computed: AwardComputed; by?: string; onPick: () => void; busy: boolean; disabled: boolean }) {
  return (
    <Card className="flex flex-col gap-2 p-4">
      <div className="font-medium">{name}</div>
      <div className="font-mono text-[22px] font-medium">{compact(computed.total_inr)}</div>
      <div className="text-table text-ink-muted">
        {computed.lines_allocated} lines · {computed.vendors_awarded} vendor{computed.vendors_awarded === 1 ? '' : 's'}
        {computed.unallocated.length ? ` · ${computed.unallocated.length} unallocated` : ''}
      </div>
      <div className="text-table text-ink-muted">{computed.allocations.map((a) => `${a.vendor.split(' ')[0]} ${a.line_count}`).join(' · ')}</div>
      {by && <div className="text-meta text-ink-faint">saved by {by}</div>}
      <Button className="mt-auto" variant="primary" busy={busy} disabled={disabled} onClick={onPick}>Draft the award from this</Button>
    </Card>
  )
}

function Picker({ rfxId }: { rfxId: string }) {
  const queryClient = useQueryClient()
  const { can } = usePersona()
  const { data, error, isPending } = useQuery({ queryKey: ['scenarios', rfxId], queryFn: () => api.scenarios(rfxId) })
  const pick = useMutation({
    mutationFn: async (choice: { saved?: Scenario; preset?: Preset }) => {
      const scenario = choice.saved ?? (await api.saveScenario(rfxId, { name: choice.preset!.name, filters: choice.preset!.filters, single_vendor: choice.preset!.single_vendor }))
      return api.setAward(rfxId, scenario.id)
    },
    onSuccess: () => { toast.success('Award drafted.'); void queryClient.invalidateQueries() },
    onError: (e) => toast.error(e.message),
  })
  if (isPending) return <Loading />
  if (error) return <ErrorNote error={error} />
  return (
    <div>
      <PageHeader title="Award" sub="Choose the scenario to recommend. Totals are computed by the award engine from the current grid, not saved figures." />
      <Meta className="mb-2">Standard options</Meta>
      <div className="mb-5 grid grid-cols-3 gap-3">
        {data.presets.map((p) => <ScenarioCard key={p.key} name={p.name} computed={p.computed} busy={pick.isPending} disabled={!can('buyer')} onPick={() => pick.mutate({ preset: p })} />)}
      </div>
      <Meta className="mb-2">Saved from the analyst</Meta>
      {data.saved.length ? (
        <div className="grid grid-cols-3 gap-3">
          {data.saved.map((s) => <ScenarioCard key={s.id} name={s.name} computed={s.computed} by={s.created_by} busy={pick.isPending} disabled={!can('buyer')} onPick={() => pick.mutate({ saved: s })} />)}
        </div>
      ) : (
        <p className="text-ink-muted">None yet. Ask a split-award question in <Link className="text-accent-ink underline" to={`/rfx/${rfxId}/analyse`}>Analyse</Link> and save the answer as a scenario.</p>
      )}
      {!can('buyer') && <p className="mt-4 text-table text-ink-muted">Only the category buyer drafts the award.</p>}
    </div>
  )
}

function Recommendation({ rfxId, view }: { rfxId: string; view: AwardView }) {
  const queryClient = useQueryClient()
  const { can } = usePersona()
  const [note, setNote] = useState('')
  const { data: grid } = useQuery({ queryKey: ['grid', rfxId], queryFn: () => api.grid(rfxId) })
  const award = view.award!
  const c = view.computed!
  const act = useMutation({
    mutationFn: (action: 'send-for-approval' | 'approve' | 'request-changes') => api.awardAction(award.id, action, note || undefined),
    onSuccess: (_, action) => { toast.success(action === 'approve' ? 'Award approved.' : action === 'request-changes' ? 'Changes requested.' : 'Sent for approval.'); setNote(''); void queryClient.invalidateQueries() },
    onError: (e) => toast.error(e.message),
  })
  const status = STATUS[award.status] ?? STATUS.draft
  const blocked = c.approval_blocked
  const ly = c.last_year
  return (
    <div>
      {grid && <AssumptionsBar rfxId={rfxId} assumptions={grid.assumptions} />}
      <PageHeader
        title="Award recommendation"
        sub={<>Scenario: {view.scenario!.name} · prepared by {view.scenario!.created_by} · for approval by VP Supply Chain <Pill tone={status.tone} className="ml-1">{status.label}</Pill></>}
      >
        <a href={fileUrl(`/rfx/${rfxId}/award/export.pdf`)}><Button><Download className="size-3.5" /> Download award pack (PDF)</Button></a>
        {award.status !== 'approved' && (
          <Button variant="primary" busy={act.isPending && act.variables === 'send-for-approval'} disabled={!can('buyer') || blocked || award.status === 'sent_for_approval'} title={blocked ? 'Blocked while review items are open' : undefined} onClick={() => act.mutate('send-for-approval')}>
            {blocked && <Lock className="size-3.5" />} Send for approval
          </Button>
        )}
      </PageHeader>

      <div className="mb-4 grid grid-cols-4 gap-3">
        <Stat label="Recommended total" value={compact(c.total_inr)} sub={`${c.lines_allocated} lines · ${c.vendors_awarded} vendors${c.filters.freight_inclusive ? ' · freight included' : ''}`} />
        <Stat
          label="vs best single vendor"
          value={c.vs_best_single_inr === null ? '–' : compact(c.vs_best_single_inr)}
          sub={c.best_single_vendor ? `${Math.abs(c.vs_best_single_pct ?? 0)}% ${c.vs_best_single_inr! <= 0 ? 'below' : 'above'} ${c.best_single_vendor.vendor} on the same lines` : 'no single vendor covers every allocated line'}
          tone={c.vs_best_single_inr !== null && c.vs_best_single_inr < 0 ? 'success' : undefined}
        />
        <Stat label="vs last year's contract" value={ly.delta_pct === null ? '–' : compact(ly.delta_inr)} sub={`${Math.abs(ly.delta_pct ?? 0)}% ${ly.delta_inr <= 0 ? 'reduction' : 'increase'} on ${ly.lines_compared} like-for-like lines`} tone={ly.delta_inr < 0 ? 'success' : undefined} />
        {blocked ? (
          <Stat tone="warning" label="Still open" value={`${c.open_items.length} item${c.open_items.length === 1 ? '' : 's'}`} sub={c.cells_in_review.length ? `${c.cells_in_review.join(', ')} · not in this total` : 'to acknowledge before approval'} />
        ) : (
          <Stat label="Review queue" value="Clear" sub="every cell counts; nothing is open" tone="success" />
        )}
      </div>

      <div className="grid grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)] gap-4">
        <div className="space-y-4">
          <Card className="overflow-hidden">
            <table className="w-full border-collapse text-table">
              <thead>
                <tr className="bg-surface-2 text-meta font-medium uppercase text-ink-muted">
                  <th scope="col" className="px-3 py-2 text-left">Vendor</th><th scope="col" className="px-3 text-left">Quality</th>
                  <th scope="col" className="px-3 text-right">Lines</th><th scope="col" className="px-3 text-right">Extended ₹</th>
                  <th scope="col" className="px-3 text-right">Freight</th><th scope="col" className="px-3 text-right">Share</th>
                </tr>
              </thead>
              <tbody>
                {c.allocations.map((a) => (
                  <tr key={a.vendor_id} className="h-10 border-t border-border">
                    <td className="px-3 font-medium">{a.vendor}</td>
                    <td className="px-3"><Pill tone={a.quality === 'Pass' ? 'success' : a.quality === 'Partial' ? 'warning' : a.quality === 'Fail' ? 'danger' : 'neutral'}>{a.quality ?? 'n/a'}</Pill></td>
                    <td className="px-3 text-right font-mono" title={a.lines.join(', ')}>{a.line_count}</td>
                    <td className="px-3 text-right font-mono">{rupees(a.extended_inr).slice(1)}</td>
                    <td className={cn('px-3 text-right font-mono', (a.freight.kind === 'extra_unpriced' || a.freight.kind === 'not_stated') && 'text-warning-ink')}>
                      {a.freight.kind === 'included' ? 'included' : a.freight.amount_inr ? rupees(a.freight.amount_inr).slice(1) : 'unpriced'}
                    </td>
                    <td className="px-3 text-right font-mono">{a.share_pct}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {c.unallocated.length > 0 && <p className="border-t border-border bg-warning-bg px-3 py-2 text-table text-warning-ink">Not allocated: {c.unallocated.map((u) => u.line_id).join(', ')} (no eligible vendor has a counted price).</p>}
          </Card>
          <Card className="p-3.5">
            <h2 className="mb-2 text-emphasis font-medium">Rules applied</h2>
            <ul className="space-y-1.5">
              {c.rules_applied.map((rule) => <li key={rule} className="flex gap-2"><Check className="mt-0.5 size-3.5 shrink-0 text-success-ink" />{rule}</li>)}
            </ul>
          </Card>
          <details className="rounded-card border border-border bg-surface-1">
            <summary className="cursor-pointer px-3.5 py-2.5 font-medium">Line-by-line allocation <span className="font-normal text-ink-muted">· {c.line_allocations.length} lines</span></summary>
            <table className="w-full border-collapse text-table">
              <tbody>
                {c.line_allocations.map((l) => (
                  <tr key={l.line_id} className="border-t border-border">
                    <td className="px-3.5 py-1.5 font-mono text-ink-muted">{l.line_id}</td><td className="px-3">{l.vendor}</td>
                    <td className="px-3 text-right font-mono">{rupees(l.inr_per_1000)}</td><td className="px-3.5 text-right font-mono">{rupees(l.extended_inr)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </div>

        <div className="space-y-4">
          <Card className="p-3.5">
            <h2 className="mb-2 text-emphasis font-medium">Excluded and why</h2>
            {c.exclusions.length ? (
              <ul className="space-y-2">
                {c.exclusions.map((e) => <li key={e.vendor_id} className="flex gap-2"><AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-danger-ink" /><span><span className="font-medium">{e.vendor}</span> · {e.reason}</span></li>)}
              </ul>
            ) : <p className="text-ink-muted">No vendor is excluded under this scenario.</p>}
            {c.rule_cost_text && <p className="mt-2 border-t border-border pt-2 text-table text-ink-muted">{c.rule_cost_text}</p>}
            {c.freight_unpriced_vendors.length > 0 && <p className="mt-2 text-table text-warning-ink">Pre-award condition: freight is unpriced for {c.freight_unpriced_vendors.join(', ')}.</p>}
          </Card>
          <Card className="p-3.5">
            <h2 className="mb-2 text-emphasis font-medium">Audit log</h2>
            <ul className="max-h-[230px] space-y-1.5 overflow-y-auto text-table">
              {view.audit.map((e) => (
                <li key={e.id} className="grid grid-cols-[92px_128px_minmax(0,1fr)] gap-2">
                  <span className="font-mono text-ink-muted">{when(e.at)}</span><span className="truncate text-ink-muted" title={e.actor}>{e.actor}</span><span>{e.summary}</span>
                </li>
              ))}
            </ul>
          </Card>
          <Card className="bg-surface-2 p-3.5">
            <h2 className="text-emphasis font-medium">Approver sign-off</h2>
            <p className="mb-2 text-table text-ink-muted">
              The VP sees this page read-only, with every figure traceable to its source cell in <Link className="text-accent-ink underline" to={`/rfx/${rfxId}/compare`}>Compare</Link>. Approval is blocked while review items are open.
            </p>
            {award.approvals.length > 0 && (
              <ul className="mb-2 space-y-1 text-table">
                {award.approvals.map((a, i) => <li key={i}><span className="font-mono text-ink-muted">{when(a.at)}</span> · {a.actor} · {a.decision.replace(/_/g, ' ')}{a.note ? ` · “${a.note}”` : ''}</li>)}
              </ul>
            )}
            {award.status === 'approved' ? (
              <Pill tone="success"><Check className="size-3" /> Approved</Pill>
            ) : (
              <>
                <input className={cn(inputClass, 'mb-2')} aria-label="Note" placeholder="Note (optional)" value={note} disabled={!can('vp')} onChange={(e) => setNote(e.target.value)} />
                <div className="flex items-center gap-2">
                  <Button variant="primary" busy={act.isPending && act.variables === 'approve'} disabled={!can('vp') || blocked} onClick={() => act.mutate('approve')}>{blocked && <Lock className="size-3.5" />} Approve</Button>
                  <Button busy={act.isPending && act.variables === 'request-changes'} disabled={!can('vp')} onClick={() => act.mutate('request-changes')}>Request changes</Button>
                  {!can('vp') && <span className="text-meta text-ink-faint">Switch to VP Supply Chain to sign off.</span>}
                  {can('vp') && blocked && <span className="text-meta text-warning-ink">{c.open_items.length} review item(s) open.</span>}
                </div>
              </>
            )}
          </Card>
        </div>
      </div>
    </div>
  )
}

export function Award() {
  const { rfxId = '' } = useParams()
  const { data, error, isPending } = useQuery({ queryKey: ['award', rfxId], queryFn: () => api.award(rfxId) })
  if (isPending) return <Loading />
  if (error) return <ErrorNote error={error} />
  return data.award ? <Recommendation rfxId={rfxId} view={data} /> : <Picker rfxId={rfxId} />
}
