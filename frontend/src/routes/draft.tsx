import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bot, ClipboardPaste, Plus, Save, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { Button, Card, ErrorNote, inputClass, Loading, Meta, PageHeader, Pill, Segmented } from '../components/ui'
import { api } from '../lib/api'
import { cn } from '../lib/cn'
import { usePersona } from '../lib/persona'
import type { Rfx, RfxDraft } from '../lib/types'

const cellInput = 'w-full rounded-[4px] border border-transparent bg-transparent px-1.5 py-1 hover:border-border focus:border-border-strong focus:bg-surface-1 focus:outline-none disabled:hover:border-transparent'

function Editor({ rfxId }: { rfxId: string }) {
  const queryClient = useQueryClient()
  const { can } = usePersona()
  const editable = can('buyer')
  const { data, error, isPending } = useQuery({ queryKey: ['rfx', rfxId], queryFn: () => api.rfx(rfxId) })
  const [draft, setDraft] = useState<Rfx | null>(null)
  useEffect(() => { if (data) setDraft(structuredClone(data.rfx)) }, [data])
  const save = useMutation({
    mutationFn: () => api.updateRfx(rfxId, draft),
    onSuccess: () => { toast.success('RFx saved. The change is in the audit log.'); void queryClient.invalidateQueries() },
    onError: (e) => toast.error(e.message),
  })
  if (isPending || !draft) return <Loading />
  if (error) return <ErrorNote error={error} />
  const dirty = JSON.stringify(draft) !== JSON.stringify(data.rfx)
  const setLine = (index: number, patch: Partial<Rfx['line_items'][number]>) =>
    setDraft({ ...draft, line_items: draft.line_items.map((l, i) => (i === index ? { ...l, ...patch } : l)) })
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <input className={cn(inputClass, 'h-9 max-w-[460px] text-emphasis font-medium')} aria-label="RFx title" disabled={!editable} value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
        <Pill tone="info">{data.status}</Pill>
        <Pill mono>{draft.line_items.length} lines</Pill>
        <Pill mono>{draft.questionnaire.length} questions · {draft.questionnaire.filter((q) => q.mandatory).length} mandatory</Pill>
        <Button className="ml-auto" variant="primary" busy={save.isPending} disabled={!editable || !dirty} onClick={() => save.mutate()}><Save className="size-3.5" /> Save changes</Button>
      </div>
      {data.status !== 'draft' && <p className="text-table text-ink-muted">This RFx has already been sent. It stays editable, and every edit is logged.</p>}

      <Card className="overflow-x-auto">
        <table className="w-full border-collapse text-table">
          <thead>
            <tr className="bg-surface-2 text-left text-meta font-medium uppercase text-ink-muted">
              <th scope="col" className="px-3 py-2">#</th><th scope="col" className="px-2">Description</th><th scope="col" className="px-2">Ply</th><th scope="col" className="px-2">GSM</th><th scope="col" className="px-2">Print</th>
              <th scope="col" className="px-2 text-right">Board kg/pc</th><th scope="col" className="px-2 text-right">Annual qty</th><th scope="col" className="px-2">UOM</th><th scope="col" className="px-2 text-right">Last year ₹/1,000</th>
            </tr>
          </thead>
          <tbody>
            {draft.line_items.map((line, index) => (
              <tr key={line.line_id} className="border-t border-border">
                <td className="px-3 font-mono text-ink-muted">{line.line_id}</td>
                <td className="px-1"><input className={cellInput} aria-label={`${line.line_id} description`} disabled={!editable} value={line.description} onChange={(e) => setLine(index, { description: e.target.value })} /></td>
                <td className="px-2 font-mono">{line.spec.ply ?? '–'}</td><td className="px-2 font-mono">{line.spec.gsm ?? '–'}</td><td className="px-2">{line.spec.print ?? 'plain'}</td>
                <td className="px-2 text-right font-mono">{line.spec.board_weight_kg_per_pc ?? '–'}</td>
                <td className="w-[110px] px-1"><input className={cn(cellInput, 'text-right font-mono')} aria-label={`${line.line_id} quantity`} inputMode="numeric" disabled={!editable} value={line.qty} onChange={(e) => setLine(index, { qty: Number(e.target.value.replace(/\D/g, '')) || 0 })} /></td>
                <td className="px-2">{line.uom}</td>
                <td className="px-3 text-right font-mono">{line.last_year_price_inr?.toLocaleString('en-IN') ?? <span className="font-sans text-ink-faint">new</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <div className="grid grid-cols-2 gap-4">
        <Card className="space-y-1 p-3.5">
          <h2 className="mb-1 text-emphasis font-medium">Supplier questionnaire</h2>
          {draft.questionnaire.map((q, index) => (
            <div key={q.question_id} className="flex items-start gap-2">
              <span className="mt-1.5 font-mono text-table text-ink-muted">{q.question_id}</span>
              <textarea className={cn(cellInput, 'min-h-[52px] resize-y text-table')} aria-label={`${q.question_id} text`} disabled={!editable} value={q.text}
                onChange={(e) => setDraft({ ...draft, questionnaire: draft.questionnaire.map((x, i) => (i === index ? { ...x, text: e.target.value } : x)) })} />
              <label className="mt-1.5 flex shrink-0 items-center gap-1 text-meta">
                <input type="checkbox" disabled={!editable} checked={q.mandatory} onChange={(e) => setDraft({ ...draft, questionnaire: draft.questionnaire.map((x, i) => (i === index ? { ...x, mandatory: e.target.checked } : x)) })} />
                mandatory
              </label>
            </div>
          ))}
        </Card>
        <Card className="space-y-2 p-3.5">
          <h2 className="text-emphasis font-medium">Terms</h2>
          {(['payment', 'delivery'] as const).map((key) => (
            <label key={key} className="block text-table"><span className="text-ink-muted">{key[0].toUpperCase() + key.slice(1)}</span>
              <input className={inputClass} disabled={!editable} value={draft.terms[key] ?? ''} onChange={(e) => setDraft({ ...draft, terms: { ...draft.terms, [key]: e.target.value } })} />
            </label>
          ))}
          <label className="block text-table"><span className="text-ink-muted">Offer validity, days</span>
            <input className={cn(inputClass, 'w-[120px] font-mono')} inputMode="numeric" disabled={!editable} value={draft.terms.validity_days ?? ''} onChange={(e) => setDraft({ ...draft, terms: { ...draft.terms, validity_days: Number(e.target.value) || null } })} />
          </label>
          <div className="text-table text-ink-muted">Base unit ₹ per 1,000 pcs · {draft.freight_policy} {draft.tax_policy}</div>
          {draft.terms.assumptions.length > 0 && (
            <div><Meta>Assumptions the co-pilot made</Meta><ul className="list-disc pl-4 text-table text-ink-muted">{draft.terms.assumptions.map((a) => <li key={a}>{a}</li>)}</ul></div>
          )}
          <div><Meta>Vendors</Meta><div className="flex flex-wrap gap-1 pt-1">{data.vendors.map((v) => <Pill key={v.vendor_id} title={v.email}>{v.name}</Pill>)}</div></div>
        </Card>
      </div>
    </div>
  )
}

type Message = { role: 'user' | 'assistant'; content: string }

function Copilot() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { can } = usePersona()
  const [messages, setMessages] = useState<Message[]>([])
  const [draft, setDraft] = useState<RfxDraft | null>(null)
  const [input, setInput] = useState('')
  const end = useRef<HTMLDivElement>(null)
  const turn = useMutation({
    mutationFn: (next: Message[]) => api.intakeChat(next, draft),
    onSuccess: (result) => { setMessages((m) => [...m, { role: 'assistant', content: result.reply }]); setDraft(result.draft) },
    onError: (e) => toast.error(e.message),
  })
  const create = useMutation({
    mutationFn: () => api.createRfx(draft!),
    onSuccess: (r) => { toast.success(`${r.id} created as a draft.`); void queryClient.invalidateQueries(); navigate(`/rfx/${r.id}/draft`) },
    onError: (e) => toast.error(e.message),
  })
  const sample = useMutation({ mutationFn: () => fetch('/api/intake/sample').then((r) => r.json() as Promise<{ text: string }>), onSuccess: (r) => setInput(r.text) })
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages.length, turn.isPending])
  const send = () => {
    if (!input.trim() || turn.isPending) return
    const next: Message[] = [...messages, { role: 'user', content: input.trim() }]
    setMessages(next)
    setInput('')
    turn.mutate(next)
  }
  const setQty = (index: number, qty: number | null) => setDraft({ ...draft!, line_items: draft!.line_items.map((l, i) => (i === index ? { ...l, qty } : l)) })
  const missingQty = draft?.line_items.filter((l) => !l.qty).length ?? 0
  const editable = can('buyer')
  return (
    <div className="grid h-[calc(100vh-190px)] grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-4">
      <Card className="flex min-h-0 flex-col">
        <div className="flex items-center gap-2 border-b border-border px-3.5 py-2.5"><Bot className="size-4 text-accent" /><span className="font-medium">Intake co-pilot</span><span className="text-table text-ink-muted">structures what you describe; never invents a quantity</span></div>
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3.5" aria-live="polite">
          {messages.length === 0 && <p className="text-ink-muted">Describe what you need, or paste an item list with quantities. The draft appears on the right and stays editable.</p>}
          {messages.map((m, i) => (
            <div key={i} className={cn('flex', m.role === 'user' && 'justify-end')}>
              <div className={cn('max-w-[92%] whitespace-pre-wrap rounded-panel px-3 py-2', m.role === 'user' ? 'max-h-[180px] overflow-y-auto rounded-br-sm bg-surface-3' : 'rounded-bl-sm border border-border')}>{m.content}</div>
            </div>
          ))}
          {turn.isPending && <Loading label="Structuring the draft…" />}
          <div ref={end} />
        </div>
        <div className="space-y-2 border-t border-border p-3">
          <textarea className={cn(inputClass, 'h-[92px] resize-none py-2')} aria-label="Message to the co-pilot" placeholder={editable ? 'Describe the RFx, paste an item list, or ask for a change…' : 'Switch to Category buyer to draft'} disabled={!editable} value={input} onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) send() }} />
          <div className="flex items-center gap-2">
            <Button variant="primary" busy={turn.isPending} disabled={!editable || !input.trim()} onClick={send}>Send</Button>
            <Button variant="ghost" disabled={!editable} onClick={() => sample.mutate()} title="Loads a buyer's rough notes for the demo RFx: an item list with quantities and last year's rates"><ClipboardPaste className="size-3.5" /> Paste sample buyer notes</Button>
            <span className="ml-auto text-meta text-ink-faint">⌘ Enter to send</span>
          </div>
        </div>
      </Card>

      <Card className="flex min-h-0 flex-col">
        <div className="flex items-center gap-2 border-b border-border px-3.5 py-2.5">
          <span className="font-medium">{draft?.title ?? 'Draft RFx'}</span>
          {draft && <><Pill mono>{draft.line_items.length} lines</Pill><Pill mono>{draft.questionnaire.length} questions</Pill>{missingQty > 0 && <Pill tone="warning" mono>{missingQty} without quantity</Pill>}</>}
          <Button className="ml-auto" variant="primary" busy={create.isPending} disabled={!editable || !draft || !draft.line_items.length || missingQty > 0} title={missingQty ? 'Fill in every quantity first; the co-pilot does not guess them' : undefined} onClick={() => create.mutate()}><Plus className="size-3.5" /> Create RFx</Button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {!draft ? <p className="p-4 text-ink-muted">Nothing drafted yet.</p> : (
            <>
              <table className="w-full border-collapse text-table">
                <thead className="sticky top-0 bg-surface-2 text-left text-meta font-medium uppercase text-ink-muted">
                  <tr><th scope="col" className="px-3 py-2">#</th><th scope="col" className="px-2">Description</th><th scope="col" className="px-2">Ply</th><th scope="col" className="px-2">GSM</th><th scope="col" className="px-2">Dims mm</th><th scope="col" className="px-2">Print</th><th scope="col" className="px-2 text-right">Qty</th><th scope="col" className="px-2">UOM</th><th scope="col" className="px-2 text-right">LY ₹/1,000</th><th /></tr>
                </thead>
                <tbody>
                  {draft.line_items.map((line, index) => (
                    <tr key={index} className="border-t border-border">
                      <td className="px-3 font-mono text-ink-muted">{index + 1}</td><td className="px-2 py-1">{line.description}</td>
                      <td className="px-2 font-mono">{line.ply ?? '–'}</td><td className="px-2 font-mono">{line.gsm ?? '–'}</td><td className="px-2 font-mono">{line.dims_mm.join('×') || '–'}</td><td className="px-2">{line.print ?? 'plain'}</td>
                      <td className="w-[100px] px-1"><input className={cn(cellInput, 'text-right font-mono', !line.qty && 'border-warning-border bg-warning-bg')} aria-label={`Line ${index + 1} quantity`} inputMode="numeric" placeholder="missing" value={line.qty ?? ''} onChange={(e) => setQty(index, Number(e.target.value.replace(/\D/g, '')) || null)} /></td>
                      <td className="px-2">{line.uom}</td><td className="px-2 text-right font-mono">{line.last_year_price_inr?.toLocaleString('en-IN') ?? '–'}</td>
                      <td className="px-1"><button type="button" aria-label={`Remove line ${index + 1}`} className="text-ink-faint hover:text-danger-ink" onClick={() => setDraft({ ...draft, line_items: draft.line_items.filter((_, i) => i !== index) })}><Trash2 className="size-3.5" /></button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="grid grid-cols-2 gap-4 p-3.5">
                <div><Meta>Questionnaire</Meta><ul className="mt-1 space-y-1 text-table">{draft.questionnaire.map((q, i) => <li key={i}>{q.text} {q.mandatory && <Pill tone="accent">mandatory</Pill>}</li>)}</ul></div>
                <div className="space-y-2 text-table">
                  <div><Meta>Terms</Meta><div>Payment: {draft.terms.payment ?? '–'}</div><div>Delivery: {draft.terms.delivery ?? '–'}</div><div>Validity: {draft.terms.validity_days ?? '–'} days</div></div>
                  {draft.assumptions.length > 0 && <div><Meta>Assumed, please confirm</Meta><ul className="list-disc pl-4 text-ink-muted">{draft.assumptions.map((a) => <li key={a}>{a}</li>)}</ul></div>}
                  {draft.missing.length > 0 && <div><Meta>Still missing</Meta><ul className="list-disc pl-4 text-warning-ink">{draft.missing.map((a) => <li key={a}>{a}</li>)}</ul></div>}
                </div>
              </div>
            </>
          )}
        </div>
      </Card>
    </div>
  )
}

export function Draft() {
  const { rfxId = '' } = useParams()
  const [tab, setTab] = useState<'rfx' | 'copilot'>('rfx')
  return (
    <div>
      <PageHeader title="Draft" sub={tab === 'rfx' ? `${rfxId}: the RFx as it will go to vendors. Edit anything.` : 'Start a new RFx by describing it. Everything the co-pilot produces lands in an editable draft.'}>
        <Segmented label="Draft mode" value={tab} onChange={setTab} options={[{ value: 'rfx', label: 'This RFx' }, { value: 'copilot', label: 'New RFx with co-pilot' }]} />
      </PageHeader>
      {tab === 'rfx' ? <Editor rfxId={rfxId} /> : <Copilot />}
    </div>
  )
}
