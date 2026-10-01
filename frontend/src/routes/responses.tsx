import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ExternalLink, FileText, Inbox, Paperclip, ScanSearch } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { Button, Card, Drawer, Empty, ErrorNote, inputClass, Loading, Meta, PageHeader, Pill, QualityPill, Segmented } from '../components/ui'
import { api, fileUrl } from '../lib/api'
import { cn } from '../lib/cn'
import { pct, rupees, shortModel, when } from '../lib/format'
import { usePersona } from '../lib/persona'
import type { Grid, QualityAnswer, Reply, ReplyFile, VendorQuality } from '../lib/types'

const KIND: Record<string, string> = { quote: 'Quote', questionnaire_response: 'Questionnaire', certificate: 'Certificate', msds: 'MSDS', spec_sheet: 'Spec sheet', other: 'Other' }
const STATUS_TONE: Record<string, 'success' | 'danger' | 'warning' | 'neutral'> = { pass: 'success', answered: 'success', fail: 'danger', unanswered: 'warning' }

function RawView({ file }: { file: ReplyFile }) {
  const url = fileUrl(file.url)
  if (file.format === 'image') return <img src={url} alt={`${file.name} as received`} className="w-full rounded-control border border-border" />
  if (file.format === 'pdf') return <iframe src={url} title={file.name} className="h-[70vh] w-full rounded-control border border-border bg-white" />
  return <pre className="max-h-[70vh] overflow-auto whitespace-pre-wrap rounded-control border border-border bg-surface-1 p-3 font-mono text-table">{file.parsed_text || 'No text.'}</pre>
}

function QualityPanel({ rfxId, quality }: { rfxId: string; quality: VendorQuality }) {
  const queryClient = useQueryClient()
  const { can } = usePersona()
  const [editing, setEditing] = useState<string | null>(null)
  const [reason, setReason] = useState('')
  const override = useMutation({
    mutationFn: (v: { question: string; status: string }) => api.qualityOverride(rfxId, quality.vendor_id, v.question, { status: v.status, reason }),
    onSuccess: () => { toast.success('Verdict overridden and logged.'); setEditing(null); setReason(''); void queryClient.invalidateQueries() },
    onError: (e) => toast.error(e.message),
  })
  if (quality.error) return <ErrorNote error={`Evaluation failed: ${quality.error}`} />
  return (
    <div className="space-y-2">
      {quality.answers.map((a: QualityAnswer) => (
        <Card key={a.question_id} className="p-3">
          <div className="flex items-start gap-2">
            <span className="font-mono text-table text-ink-muted">{a.question_id}</span>
            <span className="min-w-0 flex-1 text-table">{a.question}{a.mandatory && <Pill tone="accent" className="ml-1.5">mandatory</Pill>}</span>
            <Pill tone={STATUS_TONE[a.effective_status] ?? 'neutral'}>{a.effective_status}{a.override ? ' (overridden)' : ''}</Pill>
          </div>
          {a.evidence && <blockquote className="mt-1.5 rounded-control bg-surface-2 px-2.5 py-1.5 font-mono text-table">“{a.evidence}”</blockquote>}
          <p className="mt-1 text-table text-ink-muted">{a.reasoning}</p>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-meta text-ink-faint">
            {a.file && <span>{a.file}{a.locator ? ` · ${a.locator}` : ''}</span>}
            {a.evidence_verified === true && <Pill tone="success">evidence found in file</Pill>}
            {a.evidence_verified === false && <Pill tone="danger">evidence not found in file</Pill>}
            {a.override && <span>Overridden by {a.override.actor}: “{a.override.reason}”</span>}
            {can('evaluator') && editing !== a.question_id && <button type="button" className="ml-auto text-accent-ink underline" onClick={() => setEditing(a.question_id)}>Override verdict</button>}
          </div>
          {editing === a.question_id && (
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <input className={cn(inputClass, 'w-[280px]')} aria-label="Reason" placeholder="Reason (required)" value={reason} onChange={(e) => setReason(e.target.value)} />
              {(a.mandatory ? ['pass', 'fail', 'unanswered'] : ['answered', 'unanswered']).map((s) => (
                <Button key={s} size="sm" disabled={!reason.trim()} busy={override.isPending} onClick={() => override.mutate({ question: a.question_id, status: s })}>Set {s}</Button>
              ))}
              <Button size="sm" variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
            </div>
          )}
        </Card>
      ))}
      <p className="text-meta text-ink-faint">Judged by {shortModel(quality.model)} from everything the vendor sent. Pass if every mandatory answer passes, Fail if any mandatory answer fails, otherwise Partial. The technical evaluator can override any verdict with a reason.</p>
    </div>
  )
}

function Detail({ rfxId, reply, grid, quality }: { rfxId: string; reply: Reply; grid: Grid | undefined; quality: VendorQuality | undefined }) {
  const quote = reply.files.find((f) => f.kind === 'quote') ?? reply.files[0]
  const [file, setFile] = useState(quote.name)
  const [tab, setTab] = useState<'extraction' | 'conditions' | 'quality'>('extraction')
  const current = reply.files.find((f) => f.name === file) ?? quote
  const lead = reply.extraction.find((e) => e.role === reply.lead_role) ?? reply.extraction[0]
  return (
    <div className="grid grid-cols-2 gap-4">
      <section className="min-w-0 space-y-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <Meta>As received</Meta>
          {reply.files.map((f) => (
            <button key={f.name} type="button" onClick={() => setFile(f.name)} className={cn('rounded-full border px-2 py-0.5 text-meta', f.name === file ? 'border-accent bg-accent-bg text-accent-ink' : 'border-border text-ink-muted')}>{f.name}</button>
          ))}
          <a href={fileUrl(current.url)} target="_blank" rel="noreferrer" className="ml-auto inline-flex items-center gap-1 text-table text-accent-ink underline">Open original <ExternalLink className="size-3" /></a>
        </div>
        <p className="text-table text-ink-muted"><span className="font-medium text-ink">Router: </span>{current.summary} {current.needs_vision && <Pill tone="info">read from image</Pill>}</p>
        <RawView file={current} />
      </section>
      <section className="min-w-0 space-y-2">
        <Segmented label="Extraction view" value={tab} onChange={setTab} options={[{ value: 'extraction', label: 'What was read' }, { value: 'conditions', label: `Conditions ${lead?.conditions.length ?? 0}` }, { value: 'quality', label: 'Questionnaire' }]} />
        {tab === 'extraction' && grid && (
          <Card className="max-h-[74vh] overflow-auto">
            <table className="w-full border-collapse text-table">
              <thead className="sticky top-0 bg-surface-2 text-meta font-medium uppercase text-ink-muted">
                <tr><th scope="col" className="px-2.5 py-2 text-left">Line</th><th scope="col" className="px-2.5 text-left">As quoted</th><th scope="col" className="px-2.5 text-left">Where</th><th scope="col" className="px-2.5 text-right">₹ per 1,000</th><th scope="col" className="px-2.5 text-left">State</th></tr>
              </thead>
              <tbody>
                {grid.lines.map((line) => {
                  const cell = line.cells[reply.vendor_id]
                  const source = cell.readings[0]?.source_ref
                  return (
                    <tr key={line.line_id} className="border-t border-border align-top">
                      <td className="px-2.5 py-1.5 font-mono text-ink-muted" title={line.description}>{line.line_id}</td>
                      <td className="px-2.5 py-1.5 font-mono">{cell.raw_display ?? '–'}</td>
                      <td className="max-w-[180px] truncate px-2.5 py-1.5 text-ink-muted" title={source?.snippet}>{source?.locator ?? '–'}</td>
                      <td className="px-2.5 py-1.5 text-right font-mono">{cell.inr_per_base !== null ? rupees(cell.inr_per_base) : cell.display_inr !== null ? `${rupees(cell.display_inr)}?` : '–'}</td>
                      <td className="px-2.5 py-1.5"><Pill tone={cell.state === 'confident' ? 'success' : cell.state === 'needs_review' ? 'warning' : cell.state === 'overridden' ? 'accent' : 'neutral'}>{cell.excluded ? 'excluded' : cell.state.replace('_', ' ')}</Pill></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </Card>
        )}
        {tab === 'conditions' && (
          <div className="space-y-2">
            {lead?.conditions.map((c, i) => (
              <Card key={i} className="p-3">
                <div className="mb-1 flex items-center gap-2"><Pill tone="info">{c.kind.replace(/_/g, ' ')}</Pill><span className="text-meta text-ink-faint">{c.source_ref.locator}</span>{c.percent !== null && <Pill mono>{c.percent}%</Pill>}{c.amount !== null && <Pill mono>{rupees(c.amount)}</Pill>}</div>
                <div className="font-mono text-table">“{c.text}”</div>
                {c.applies_to && <div className="text-meta text-ink-muted">applies to: {c.applies_to}</div>}
              </Card>
            ))}
            {!lead?.conditions.length && <Empty title="No conditions were reported for this quote" />}
            <p className="text-meta text-ink-faint">Conditions are reported verbatim and never applied to a price by a model. A discount or missing freight becomes a review item.</p>
          </div>
        )}
        {tab === 'quality' && (quality ? <QualityPanel rfxId={rfxId} quality={quality} /> : <Empty title="No evaluation yet" />)}
      </section>
    </div>
  )
}

export function Responses() {
  const { rfxId = '' } = useParams()
  const [params] = useSearchParams()
  const queryClient = useQueryClient()
  const { can } = usePersona()
  const [open, setOpen] = useState<string | null>(null)
  const { data: replies, error, isPending } = useQuery({ queryKey: ['replies', rfxId], queryFn: () => api.replies(rfxId) })
  const { data: grid } = useQuery({ queryKey: ['grid', rfxId], queryFn: () => api.grid(rfxId) })
  const { data: quality } = useQuery({ queryKey: ['quality', rfxId], queryFn: () => api.quality(rfxId) })
  const { data: inbox } = useQuery({ queryKey: ['inbox', rfxId], queryFn: () => api.inbox(rfxId) })
  const { data: job } = useQuery({
    queryKey: ['ingest', rfxId],
    queryFn: () => api.ingestStatus(rfxId),
    refetchInterval: (query) => (query.state.data?.status === 'running' ? 2500 : false),
  })
  const deliver = useMutation({
    mutationFn: () => api.deliverSeed(rfxId),
    onSuccess: (r) => { toast.success(`${Object.keys(r.delivered).length} vendor replies arrived in the inbox.`); void queryClient.invalidateQueries({ queryKey: ['inbox', rfxId] }) },
    onError: (e) => toast.error(e.message),
  })
  const ingest = useMutation({
    mutationFn: () => api.startIngest(rfxId),
    onSuccess: () => { toast.message('Reading the inbox with both models. This takes two to three minutes.'); void queryClient.invalidateQueries({ queryKey: ['ingest', rfxId] }) },
    onError: (e) => toast.error(e.message),
  })
  const finishedAt = job?.status === 'done' ? job.finished_at : undefined
  useEffect(() => {
    if (finishedAt) void queryClient.invalidateQueries()
  }, [finishedAt, queryClient])
  if (isPending) return <Loading />
  if (error) return <ErrorNote error={error} />
  const waiting = Object.values(inbox ?? {}).reduce((n, files) => n + files.length, 0)
  const running = job?.status === 'running'
  const selected = replies.find((r) => r.vendor_id === open)
  const attachments = replies.flatMap((r) => r.files.filter((f) => f.kind !== 'quote').map((f) => ({ vendor: r.name, file: f })))
  const showAttachments = params.get('tab') === 'attachments'

  return (
    <div>
      <PageHeader title={showAttachments ? 'Attachments' : 'Responses'} sub={showAttachments ? 'Supporting documents the vendors sent, as routed by the intake model.' : `${replies.filter((r) => r.files.length).length} of ${replies.length} vendors have replied. Any format is accepted; nothing is rejected for ignoring the template.`}>
        <Pill mono title="Files sitting in mail/inbox">{waiting} files in inbox</Pill>
        <Button busy={deliver.isPending} disabled={!can('buyer') || running} onClick={() => deliver.mutate()} title="Email transport is stubbed: this drops the five fabricated replies into mail/inbox, as if they had arrived">
          <Inbox className="size-3.5" /> Receive replies (stub)
        </Button>
        <Button variant="primary" busy={ingest.isPending || running} disabled={!can('buyer') || waiting === 0} onClick={() => ingest.mutate()}>
          <ScanSearch className="size-3.5" /> {running ? 'Reading…' : 'Read inbox with both models'}
        </Button>
      </PageHeader>
      {running && <div role="status" className="mb-3 rounded-card border border-border bg-info-bg px-3 py-2 text-info-ink">Live extraction in progress: routing each file, then Claude and Gemini read every quote in parallel while the questionnaire is evaluated. The grid refreshes when it finishes.</div>}
      {job?.status === 'failed' && <div className="mb-3"><ErrorNote error={`The last read failed: ${job.error}`} /></div>}

      {showAttachments ? (
        <div className="grid grid-cols-3 gap-3">
          {attachments.map(({ vendor, file }) => (
            <Card key={vendor + file.name} className="space-y-1.5 p-3.5">
              <div className="flex items-center gap-2"><Paperclip className="size-3.5 text-ink-muted" /><span className="truncate font-medium" title={file.name}>{file.name}</span></div>
              <div className="flex gap-1.5"><Pill tone="info">{KIND[file.kind] ?? file.kind}</Pill><Pill>{vendor}</Pill>{file.parent && <Pill title={`Carried inside ${file.parent}`}>in email</Pill>}</div>
              <p className="text-table text-ink-muted">{file.summary}</p>
              <a href={fileUrl(file.url)} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-table text-accent-ink underline">Open <ExternalLink className="size-3" /></a>
            </Card>
          ))}
          {attachments.length === 0 && <Empty title="No attachments have been read yet" />}
        </div>
      ) : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(330px,1fr))] gap-3">
          {replies.map((reply) => {
            const vendor = grid?.vendors.find((v) => v.vendor_id === reply.vendor_id)
            const quote = reply.files.find((f) => f.kind === 'quote')
            if (!reply.files.length)
              return <Card key={reply.vendor_id} className="p-4"><div className="font-medium">{reply.name}</div><p className="text-ink-muted">No reply read yet.</p></Card>
            return (
              <Card key={reply.vendor_id} className="flex flex-col gap-2 p-4">
                <div className="flex items-start justify-between gap-2">
                  <div><div className="text-emphasis font-medium">{reply.name}</div><div className="text-meta text-ink-faint">{reply.email} · received {when(reply.received_at)}</div></div>
                  <QualityPill quality={vendor?.quality ?? null} />
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {vendor?.format_label && <Pill>{vendor.format_label}</Pill>}
                  <Pill mono tone={vendor?.lines_quoted === 30 ? 'neutral' : 'warning'}>Lines {vendor?.lines_quoted}/30</Pill>
                  {vendor && vendor.totals.needs_review > 0 && <Pill mono tone="warning">{vendor.totals.needs_review} in review</Pill>}
                  {quote?.needs_vision && <Pill tone="info">vision</Pill>}
                </div>
                <p className="text-table text-ink-muted">{quote?.summary}</p>
                <div className="space-y-1 rounded-control bg-surface-2 p-2 text-table">
                  {reply.extraction.map((e) => (
                    <div key={e.role} className="flex items-center justify-between gap-2">
                      <span>{shortModel(e.model)}{e.role === reply.lead_role ? ' · lead' : ''}</span>
                      {e.status === 'ok' ? <span className="font-mono text-ink-muted">{e.rows} rows · {e.conditions.length} conditions</span> : <Pill tone="danger" title={e.error ?? ''}>failed</Pill>}
                    </div>
                  ))}
                  <div className="flex items-center justify-between border-t border-border pt-1"><span>Agreement between the two</span><span className="font-mono font-medium">{pct(vendor?.agreement, 1)}</span></div>
                </div>
                <div className="flex flex-wrap gap-1">
                  {reply.files.map((f) => <Pill key={f.name} title={f.summary ?? ''}><FileText className="size-3" />{KIND[f.kind] ?? f.kind}</Pill>)}
                </div>
                <Button className="mt-auto" onClick={() => setOpen(reply.vendor_id)}>Raw beside extraction</Button>
              </Card>
            )
          })}
        </div>
      )}
      {selected && (
        <Drawer open onOpenChange={(o) => !o && setOpen(null)} width={1280} title={selected.name} sub="The reply exactly as received, beside what the models read from it.">
          <Detail rfxId={rfxId} reply={selected} grid={grid} quality={quality?.find((q) => q.vendor_id === selected.vendor_id)} />
        </Drawer>
      )}
    </div>
  )
}
