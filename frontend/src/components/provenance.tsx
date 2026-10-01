import * as Popover from '@radix-ui/react-popover'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Check, ExternalLink, FileQuestion, Mail, X } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { toast } from 'sonner'
import { api, fileUrl } from '../lib/api'
import { cn } from '../lib/cn'
import { num, rupees, shortModel, when } from '../lib/format'
import { usePersona } from '../lib/persona'
import type { CellDetail, ModelReading, ReviewItem, SourceRef, Step } from '../lib/types'
import { Button, inputClass, Loading, Meta, Pill } from './ui'

const STATE_LABEL: Record<string, string> = { confident: 'confident', needs_review: 'needs review', not_quoted: 'not quoted', overridden: 'overridden' }
const OP: Record<string, string> = { unit_factor: 'unit', pack_factor: 'pack', weight_factor: 'board weight', fx: 'FX', discount: 'discount', carry_forward: 'carried forward' }

/** The verbatim snippet with the value that was read highlighted. */
export function Snippet({ source, value }: { source: SourceRef; value?: number | null }) {
  const text = source.snippet
  let parts: ReactNode = text
  if (value !== null && value !== undefined) {
    const match = [...text.matchAll(/\d[\d,]*(?:\.\d+)?/g)].find((m) => Math.abs(Number(m[0].replace(/,/g, '')) - value) < 1e-6)
    if (match && match.index !== undefined) {
      parts = (
        <>
          {text.slice(0, match.index)}
          <mark className="rounded-sm bg-warning-bg px-0.5 font-medium text-warning-ink">{match[0]}</mark>
          {text.slice(match.index + match[0].length)}
        </>
      )
    }
  }
  return <blockquote className="rounded-control bg-surface-2 px-2.5 py-2 font-mono text-table leading-relaxed">“{parts}”</blockquote>
}

export function Verified({ source }: { source: SourceRef }) {
  if (source.snippet_verified === true)
    return <Pill tone="success" title="Checked without a model: the value is in the file at this location"><Check className="size-3" /> found in file</Pill>
  if (source.snippet_verified === false)
    return <Pill tone="danger" title="The value could not be found at the cited location"><X className="size-3" /> not found in file</Pill>
  return <Pill title="A photo has no text layer to check against, so this relies on two models agreeing"><FileQuestion className="size-3" /> photo: no text check</Pill>
}

export function ReadingBox({ reading }: { reading: ModelReading }) {
  const value = reading.not_quoted ? 'declined' : reading.raw_value === null ? 'no legible value' : `${num(reading.raw_value)} ${reading.raw_currency ?? ''} / ${reading.raw_unit ?? reading.unit_code}`
  return (
    <div className="flex-1 rounded-control border border-border px-2.5 py-1.5">
      <div className="flex items-center justify-between text-meta text-ink-muted">
        <span>{shortModel(reading.model)} read</span>
        <span className="font-mono">{reading.confidence.toFixed(2)}</span>
      </div>
      <div className="font-mono text-table font-medium">{value}</div>
      {reading.alternatives.length > 0 && (
        <div className="font-mono text-meta text-warning-ink">or {reading.alternatives.slice(0, 5).map(num).join(', ')}</div>
      )}
    </div>
  )
}

export function Arithmetic({ steps }: { steps: Step[] }) {
  if (!steps.length) return null
  return (
    <div className="space-y-0.5 rounded-control bg-surface-2 px-2.5 py-2 font-mono text-table">
      {steps.map((step, index) => (
        <div key={index} title={step.source}>
          {num(step.value_in)} × {num(step.factor)} = <span className="font-medium">{num(step.value_out)}</span>
          <span className="text-ink-faint"> · {OP[step.op] ?? step.op}: {step.source}</span>
        </div>
      ))}
    </div>
  )
}

function useCellActions(rfxId: string, onDone: () => void) {
  const queryClient = useQueryClient()
  const done = (message: string) => {
    toast.success(message)
    void queryClient.invalidateQueries()
    onDone()
  }
  const fail = (error: Error) => toast.error(error.message)
  return {
    resolve: useMutation({
      mutationFn: (v: { item: string; option: string }) => api.resolve(rfxId, v.item, { option_id: v.option }),
      onSuccess: () => done('Resolved. The cell now counts in the totals.'),
      onError: fail,
    }),
    override: useMutation({
      mutationFn: (v: { vendor: string; line: string; value?: number; exclude?: boolean; reason: string }) =>
        api.override(rfxId, v.vendor, v.line, { value: v.value, exclude: v.exclude, reason: v.reason }),
      onSuccess: () => done('Saved with your reason in the audit log.'),
      onError: fail,
    }),
    revert: useMutation({
      mutationFn: (v: { vendor: string; line: string }) => api.revert(rfxId, v.vendor, v.line),
      onSuccess: () => done('Override reverted.'),
      onError: fail,
    }),
    ask: useMutation({
      mutationFn: (itemIds: string[]) => api.askVendor(rfxId, itemIds),
      onSuccess: (email) => done(`Clarification drafted to ${email.to}. It is in the outbox, not sent.`),
      onError: fail,
    }),
  }
}

function Detail({ rfxId, detail, onClose }: { rfxId: string; detail: CellDetail; onClose: () => void }) {
  const { can } = usePersona()
  const editable = can('buyer')
  const actions = useCellActions(rfxId, onClose)
  const [mode, setMode] = useState<'none' | 'override' | 'exclude'>('none')
  const [value, setValue] = useState('')
  const [reason, setReason] = useState('')
  const { cell, line, vendor } = detail
  const open = detail.review_items.filter((item) => item.status !== 'resolved')
  const blocking = open.filter((item) => item.blocks_cells)
  const lead = cell.readings[0]
  const flagged = cell.state === 'needs_review'
  const weakest = cell.readings.length ? Math.min(...cell.readings.map((r) => r.confidence)) : null
  const submit = () =>
    actions.override.mutate({ vendor: vendor.vendor_id, line: line.line_id, reason, ...(mode === 'exclude' ? { exclude: true } : { value: Number(value) }) })

  return (
    <div className="max-h-[78vh] overflow-y-auto">
      <div className={cn('flex items-center gap-2 border-b px-3.5 py-2.5', flagged ? 'border-warning-border bg-warning-bg text-warning-ink' : 'border-border')}>
        {flagged && <AlertTriangle className="size-4 shrink-0" />}
        <span className="font-medium">{line.line_id} · {vendor.name} · {cell.excluded ? 'excluded' : STATE_LABEL[cell.state]}</span>
        {weakest !== null && <Pill mono tone={flagged ? 'warning' : 'neutral'} className="ml-auto">confidence {weakest.toFixed(2)}</Pill>}
      </div>
      <div className="space-y-3 p-3.5">
        <p className="text-table text-ink-muted">{line.description}</p>

        {lead ? (
          <section className="space-y-1.5">
            <div className="flex items-center justify-between gap-2">
              <Meta>Source</Meta>
              <Verified source={lead.source_ref} />
            </div>
            <div className="flex items-center gap-1.5 text-table">
              <span className="font-medium">{lead.source_ref.file}</span>
              <span className="text-ink-muted">· {lead.source_ref.locator}</span>
              {vendor.file_url && (
                <a href={fileUrl(vendor.file_url)} target="_blank" rel="noreferrer" className="ml-auto inline-flex items-center gap-1 text-accent-ink underline underline-offset-2">
                  Open file <ExternalLink className="size-3" />
                </a>
              )}
            </div>
            <Snippet source={lead.source_ref} value={lead.raw_value} />
            {vendor.format === 'image' && vendor.file_url && (
              <a href={fileUrl(vendor.file_url)} target="_blank" rel="noreferrer">
                <img src={fileUrl(vendor.file_url)} alt={`${vendor.file} as received`} className="max-h-[150px] w-full rounded-control border border-border object-cover object-top" />
              </a>
            )}
          </section>
        ) : (
          <section>
            <Meta>Source</Meta>
            <p className="text-table">
              {cell.how === 'carry_forward' || cell.how === 'carry_forward_unresolved'
                ? 'No price for this line in the reply. The vendor wrote "rest same as last year", so the value is last year’s contract price from the RFx.'
                : 'No price for this line was found in the vendor’s reply by either model.'}
            </p>
          </section>
        )}

        {cell.readings.length > 0 && (
          <section className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Meta>Readings</Meta>
              {cell.agreement !== null && (
                <Pill mono tone={cell.agreement === 1 ? 'success' : 'warning'}>{cell.agreement === 1 ? 'models agree' : 'models disagree'}</Pill>
              )}
            </div>
            <div className="flex gap-2">{cell.readings.map((r) => <ReadingBox key={r.role} reading={r} />)}</div>
            {lead?.notes && <p className="text-meta text-ink-muted">Model note: {lead.notes}</p>}
          </section>
        )}

        {(cell.flag_reason || open.length > 0) && (
          <section className="space-y-1">
            <Meta>Why flagged</Meta>
            {open.map((item) => (
              <p key={item.id} className="text-table"><span className="font-medium">{item.title}.</span> {item.reason}</p>
            ))}
          </section>
        )}

        <section className="space-y-1.5">
          <Meta>Arithmetic</Meta>
          {cell.normalization_trace.length > 0 ? <Arithmetic steps={cell.normalization_trace} /> : <p className="text-table text-ink-muted">Nothing computed for this cell.</p>}
          {blocking.flatMap((item) => item.options).filter((o) => o.inr_per_base !== null).map((option) => (
            <div key={option.option_id} className="rounded-control border border-border px-2.5 py-1.5 text-table">
              <div className="font-medium">{option.label}</div>
              {option.note && <div className="text-meta text-ink-muted">{option.note}</div>}
            </div>
          ))}
          <div className="flex justify-between text-table">
            <span className="text-ink-muted">{cell.inr_per_base !== null ? 'Counted in totals' : 'Not counted in any total'}</span>
            <span className="font-mono font-medium">
              {cell.inr_per_base !== null ? `${rupees(cell.inr_per_base)} per 1,000` : cell.display_inr !== null ? `provisional ${rupees(cell.display_inr)}` : '–'}
            </span>
          </div>
        </section>

        {cell.override && (
          <section className="rounded-control border border-accent/40 bg-accent-bg px-2.5 py-2 text-table text-accent-ink">
            <div className="font-medium">{cell.override.action === 'exclude' ? 'Excluded' : `Overridden to ${rupees(cell.override.value)}`} by {cell.override.actor}</div>
            <div>Reason: {cell.override.reason}</div>
            {cell.display_inr !== null && cell.override.action === 'override' && <div className="text-meta">System value was {rupees(cell.display_inr)}</div>}
          </section>
        )}
        {cell.resolution_note && <p className="text-meta text-ink-muted">Resolved: {cell.resolution_note}</p>}

        <section className="space-y-2 border-t border-border pt-3">
          <Meta>Actions</Meta>
          {!editable && <p className="text-table text-ink-muted">Read-only for this persona. Switch to Category buyer to resolve or override.</p>}
          {editable && mode === 'none' && (
            <div className="flex flex-wrap gap-2">
              {blocking.flatMap((item: ReviewItem) =>
                item.options.map((option, index) => (
                  <Button
                    key={item.id + option.option_id}
                    variant={index === 0 ? 'primary' : 'secondary'}
                    busy={actions.resolve.isPending}
                    onClick={() => actions.resolve.mutate({ item: item.id, option: option.option_id })}
                    title={option.note ?? undefined}
                  >
                    {option.label}
                  </Button>
                )),
              )}
              {cell.override ? (
                <Button busy={actions.revert.isPending} onClick={() => actions.revert.mutate({ vendor: vendor.vendor_id, line: line.line_id })}>Revert override</Button>
              ) : (
                <>
                  {cell.state !== 'not_quoted' || cell.how !== 'not_quoted' ? <Button onClick={() => setMode('override')}>Override…</Button> : <Button onClick={() => setMode('override')}>Enter a value…</Button>}
                  {open.length > 0 && (
                    <Button busy={actions.ask.isPending} onClick={() => actions.ask.mutate(open.map((item) => item.id))}>
                      <Mail className="size-3.5" /> Ask vendor
                    </Button>
                  )}
                  {cell.state !== 'not_quoted' && <Button variant="ghost" onClick={() => setMode('exclude')}>Exclude line</Button>}
                </>
              )}
            </div>
          )}
          {editable && mode !== 'none' && (
            <div className="space-y-2">
              {mode === 'override' && (
                <input autoFocus className={cn(inputClass, 'font-mono')} inputMode="decimal" placeholder="₹ per 1,000 pcs" aria-label="Override value in rupees per 1,000" value={value} onChange={(e) => setValue(e.target.value)} />
              )}
              <input className={inputClass} placeholder="Reason (required, goes in the audit log)" aria-label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} />
              <div className="flex gap-2">
                <Button variant="primary" busy={actions.override.isPending} disabled={!reason.trim() || (mode === 'override' && !(Number(value) > 0))} onClick={submit}>
                  {mode === 'override' ? 'Save override' : 'Exclude from comparison'}
                </Button>
                <Button onClick={() => setMode('none')}>Cancel</Button>
              </div>
            </div>
          )}
        </section>

        {detail.history.length > 0 && (
          <section className="space-y-1 border-t border-border pt-3">
            <Meta>History</Meta>
            {detail.history.slice(0, 5).map((event) => (
              <div key={event.id} className="text-meta text-ink-muted">
                <span className="font-mono">{when(event.at)}</span> · {event.actor} · {event.summary}
              </div>
            ))}
          </section>
        )}
      </div>
    </div>
  )
}

/** Every figure is one click from its source. Wrap any grid cell with this. */
export function ProvenancePopover({ rfxId, vendorId, lineId, children }: { rfxId: string; vendorId: string; lineId: string; children: ReactNode }) {
  const [open, setOpen] = useState(false)
  const { data, isPending, error } = useQuery({ queryKey: ['cell', rfxId, vendorId, lineId], queryFn: () => api.cell(rfxId, vendorId, lineId), enabled: open })
  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>{children}</Popover.Trigger>
      <Popover.Portal>
        <Popover.Content side="left" align="start" sideOffset={6} collisionPadding={12} className="z-50 w-[420px] rounded-panel border border-border bg-surface-1 shadow-popover focus:outline-none">
          {isPending && <Loading label="Loading provenance…" />}
          {error && <div className="p-3 text-danger-ink">{error.message}</div>}
          {data && <Detail rfxId={rfxId} detail={data} onClose={() => setOpen(false)} />}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}
