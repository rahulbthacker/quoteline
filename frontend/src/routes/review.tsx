import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Mail, RotateCcw } from 'lucide-react'
import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { ReadingBox, Snippet, Verified } from '../components/provenance'
import { Button, Card, Empty, ErrorNote, inputClass, Loading, Modal, PageHeader, Pill, Segmented } from '../components/ui'
import { api } from '../lib/api'
import { cn } from '../lib/cn'
import { rupees } from '../lib/format'
import { usePersona } from '../lib/persona'
import type { ReviewItem } from '../lib/types'

type Tab = 'open' | 'resolved' | 'all'
type Draft = { to: string; subject: string; body: string; path: string }

function linesLabel(item: ReviewItem): string {
  const lines = item.cells.map((c) => c.line_id)
  if (!lines.length) return 'Whole quote'
  return lines.length <= 4 ? lines.join(', ') : `${lines.length} lines`
}

function ReviewCard({ rfxId, item, onDraft }: { rfxId: string; item: ReviewItem; onDraft: (draft: Draft) => void }) {
  const queryClient = useQueryClient()
  const { can } = usePersona()
  const editable = can('buyer')
  const [mode, setMode] = useState<'none' | 'value' | 'amount'>('none')
  const [value, setValue] = useState('')
  const [reason, setReason] = useState('')
  const refresh = (message: string) => {
    toast.success(message)
    void queryClient.invalidateQueries()
    setMode('none')
  }
  const fail = (error: Error) => toast.error(error.message)
  const resolve = useMutation({
    mutationFn: (body: { option_id?: string; value?: number; amount?: number; reason?: string }) => api.resolve(rfxId, item.id, body),
    onSuccess: () => refresh('Resolved and logged.'),
    onError: fail,
  })
  const reopen = useMutation({ mutationFn: () => api.reopen(rfxId, item.id), onSuccess: () => refresh('Reopened.'), onError: fail })
  const ask = useMutation({
    mutationFn: () => api.askVendor(rfxId, [item.id]),
    onSuccess: (email) => {
      void queryClient.invalidateQueries()
      onDraft(email)
    },
    onError: fail,
  })
  const weakest = item.readings.length ? Math.min(...item.readings.map((r) => r.confidence)) : null
  const resolved = item.status === 'resolved'
  const resolution = item.resolution as { label?: string; option_id?: string; actor?: string; value?: number; reason?: string; amount?: number } | null
  const single = item.cells.length === 1 && item.blocks_cells

  return (
    <Card className={cn('grid grid-cols-[170px_minmax(0,1fr)_240px] gap-5 p-4', resolved && 'opacity-80')}>
      <div className="space-y-1.5">
        <div className="font-mono text-table text-ink-muted">{linesLabel(item)}</div>
        <div className="font-medium">{item.vendor_name}</div>
        <div className="flex flex-wrap gap-1">
          {weakest !== null && <Pill mono tone={item.status === 'open' ? 'warning' : 'neutral'}>confidence {weakest.toFixed(2)}</Pill>}
          {!item.blocks_cells && <Pill title="This item does not hold any cell out of the totals, but it must be acknowledged before award">to acknowledge</Pill>}
          {item.status === 'asked_vendor' && <Pill tone="info">asked vendor · draft in outbox</Pill>}
          {resolved && <Pill tone="success">resolved</Pill>}
        </div>
      </div>

      <div className="min-w-0 space-y-2">
        <h2 className="text-emphasis font-medium">{item.title}</h2>
        <p className="text-ink-muted">{item.reason}</p>
        {item.source ? (
          <>
            <Snippet source={item.source} value={item.readings[0]?.raw_value} />
            <div className="flex flex-wrap items-center gap-2 text-table text-ink-muted">
              <span>{item.source.file} · {item.source.locator}</span>
              <Verified source={item.source} />
            </div>
          </>
        ) : (
          item.evidence && <blockquote className="rounded-control bg-surface-2 px-2.5 py-2 font-mono text-table">“{item.evidence}”</blockquote>
        )}
        {item.readings.length > 0 && (
          <div className="flex gap-2">
            {item.readings.map((r) => <ReadingBox key={r.role} reading={r} />)}
            <div className="rounded-control border border-border px-2.5 py-1.5">
              <div className="text-meta text-ink-muted">Agreement</div>
              <div className="font-mono text-table font-medium">{item.agreement === null ? '–' : item.agreement === 1 ? 'agree' : 'disputed'}</div>
            </div>
          </div>
        )}
        {item.options.some((o) => o.note) && (
          <ul className="space-y-0.5 text-table text-ink-muted">
            {item.options.filter((o) => o.note).map((o) => <li key={o.option_id}><span className="font-medium text-ink">{o.label}:</span> {o.note}</li>)}
          </ul>
        )}
        {resolved && resolution && (
          <p className="rounded-control bg-success-bg px-2.5 py-1.5 text-table text-success-ink">
            {resolution.option_id === 'override' ? `Overridden to ${rupees(resolution.value)}` : resolution.label ?? resolution.option_id}
            {resolution.amount ? ` · freight entered: ${rupees(resolution.amount)}` : ''} · by {resolution.actor}
            {resolution.reason ? ` · “${resolution.reason}”` : ''}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-1.5">
        {!editable && <p className="text-table text-ink-muted">Read-only for this persona.</p>}
        {editable && resolved && <Button busy={reopen.isPending} onClick={() => reopen.mutate()}><RotateCcw className="size-3.5" /> Reopen</Button>}
        {editable && !resolved && mode === 'none' && (
          <>
            {item.options.map((option, index) => (
              <Button key={option.option_id} variant={index === 0 ? 'primary' : 'secondary'} className="h-auto min-h-8 whitespace-normal py-1.5 text-left" busy={resolve.isPending} onClick={() => resolve.mutate({ option_id: option.option_id })}>
                {option.label}
              </Button>
            ))}
            {item.kind === 'missing_freight' && <Button onClick={() => setMode('amount')}>Enter the freight amount…</Button>}
            <Button busy={ask.isPending} onClick={() => ask.mutate()}><Mail className="size-3.5" /> Ask {item.vendor_name.split(' ')[0]}</Button>
            {single && <Button variant="ghost" onClick={() => setMode('value')}>Override with my value…</Button>}
          </>
        )}
        {editable && !resolved && mode !== 'none' && (
          <div className="space-y-1.5">
            <input autoFocus className={cn(inputClass, 'font-mono')} inputMode="decimal" aria-label={mode === 'value' ? 'Value in rupees per 1,000' : 'Freight amount in rupees'} placeholder={mode === 'value' ? '₹ per 1,000 pcs' : 'Freight, ₹ for the contract'} value={value} onChange={(e) => setValue(e.target.value)} />
            {mode === 'value' && <input className={inputClass} aria-label="Reason" placeholder="Reason (required)" value={reason} onChange={(e) => setReason(e.target.value)} />}
            <div className="flex gap-1.5">
              <Button
                variant="primary"
                busy={resolve.isPending}
                disabled={!(Number(value) > 0) || (mode === 'value' && !reason.trim())}
                onClick={() => resolve.mutate(mode === 'value' ? { value: Number(value), reason } : { option_id: 'accept_open', amount: Number(value) })}
              >
                Save
              </Button>
              <Button onClick={() => setMode('none')}>Cancel</Button>
            </div>
          </div>
        )}
      </div>
    </Card>
  )
}

export function Review() {
  const { rfxId = '' } = useParams()
  const [tab, setTab] = useState<Tab>('open')
  const [draft, setDraft] = useState<Draft | null>(null)
  const { can } = usePersona()
  const queryClient = useQueryClient()
  const { data, error, isPending } = useQuery({ queryKey: ['review', rfxId], queryFn: () => api.review(rfxId) })
  const askAll = useMutation({
    mutationFn: async (items: ReviewItem[]) => {
      const byVendor = new Map<string, string[]>()
      items.forEach((item) => byVendor.set(item.vendor_id, [...(byVendor.get(item.vendor_id) ?? []), item.id]))
      const drafts = []
      for (const ids of byVendor.values()) drafts.push(await api.askVendor(rfxId, ids))
      return drafts
    },
    onSuccess: (drafts) => {
      toast.success(`${drafts.length} clarification email(s) drafted to the outbox. None was sent.`)
      void queryClient.invalidateQueries()
      setDraft(drafts[0])
    },
    onError: (e) => toast.error(e.message),
  })
  if (isPending) return <Loading />
  if (error) return <ErrorNote error={error} />
  const open = data.filter((i) => i.status !== 'resolved')
  const resolved = data.filter((i) => i.status === 'resolved')
  const shown = tab === 'open' ? open : tab === 'resolved' ? resolved : data
  const vendors = new Set(open.map((i) => i.vendor_id)).size
  const askable = open.filter((i) => i.status === 'open')
  return (
    <div>
      <PageHeader title="Review queue" sub={`${open.length} open across ${vendors} vendors · resolve, ask the vendor, or override with a reason. Every action is logged.`}>
        <Segmented label="Items" value={tab} onChange={setTab} options={[{ value: 'open', label: `Open ${open.length}` }, { value: 'resolved', label: `Resolved ${resolved.length}` }, { value: 'all', label: 'All' }]} />
        <Button busy={askAll.isPending} disabled={!can('buyer') || askable.length === 0} onClick={() => askAll.mutate(askable)}>
          <Mail className="size-3.5" /> Draft one email per vendor
        </Button>
      </PageHeader>
      <div className="space-y-3">
        {shown.map((item) => <ReviewCard key={item.id} rfxId={rfxId} item={item} onDraft={setDraft} />)}
        {shown.length === 0 && (
          <Empty title={tab === 'open' ? 'Nothing is waiting for a decision' : 'Nothing here yet'}>
            {tab === 'open' && 'Every cell counts in the totals, and the award can go for approval.'}
          </Empty>
        )}
      </div>
      {draft && (
        <Modal open onOpenChange={(o) => !o && setDraft(null)} title="Clarification drafted" sub="Saved to the outbox as a draft. Nothing is sent automatically; the email transport is stubbed.">
          <div className="space-y-2 text-table">
            <div><span className="text-ink-muted">To </span>{draft.to}</div>
            <div><span className="text-ink-muted">Subject </span><span className="font-medium">{draft.subject}</span></div>
            <pre className="max-h-[46vh] overflow-y-auto whitespace-pre-wrap rounded-control bg-surface-2 p-3 font-sans">{draft.body}</pre>
            <div className="font-mono text-meta text-ink-faint">{draft.path}</div>
            <div className="flex justify-end"><Button variant="primary" onClick={() => setDraft(null)}>Done</Button></div>
          </div>
        </Modal>
      )}
    </div>
  )
}
