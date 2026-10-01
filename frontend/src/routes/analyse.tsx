import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CircleSlash, Download, Save, Sparkles } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { toast } from 'sonner'
import { AssumptionsBar } from '../components/assumptions-bar'
import { Button, Card, ErrorNote, Loading, Meta, Pill, QualityPill } from '../components/ui'
import { api, fileUrl } from '../lib/api'
import { compact, num, when } from '../lib/format'
import { usePersona } from '../lib/persona'
import type { Analysis } from '../lib/types'

const STARTERS = [
  'What if we split it, cheapest per line, but only among vendors who cleared the quality questionnaire? Compare with giving it all to the single cheapest vendor.',
  'Who is cheapest on every 5-ply line?',
  'What do we lose by excluding NorthBox?',
  'How do the best prices compare with last year, by line?',
]
const SERIES = ['var(--accent)', 'var(--info-ink)']

function cellText(value: string | number | boolean | null): string {
  if (value === null) return '–'
  if (typeof value === 'number') return num(value)
  return String(value)
}

function ResultChart({ analysis }: { analysis: Analysis }) {
  const chart = analysis.chart
  if (!chart || chart.type === 'none' || !chart.x) return null
  const data = analysis.rows.slice(0, 40).map((row) => Object.fromEntries(analysis.columns.map((c, i) => [c, row[i]])))
  const numeric = chart.y.filter((y) => data.some((d) => typeof d[y] === 'number'))
  if (!numeric.length) return null
  const axis = { stroke: 'var(--ink-faint)', fontSize: 11, tickLine: false }
  const common = (
    <>
      <CartesianGrid stroke="var(--border)" vertical={false} />
      <XAxis dataKey={chart.x} {...axis} interval={0} angle={-18} textAnchor="end" height={54} tickFormatter={(v) => (String(v).length > 22 ? `${String(v).slice(0, 21)}…` : String(v))} />
      <YAxis {...axis} width={56} tickFormatter={(v) => num(Number(v))} />
      <Tooltip contentStyle={{ background: 'var(--surface-1)', border: '1px solid var(--border-strong)', borderRadius: 6, fontSize: 12, color: 'var(--ink)' }} />
      {numeric.length > 1 && <Legend wrapperStyle={{ fontSize: 11 }} />}
    </>
  )
  return (
    <Card className="p-3">
      <Meta className="mb-2">{chart.title ?? 'Chart'}</Meta>
      <div className="h-[220px]" role="img" aria-label={chart.title ?? 'Chart of the result'}>
        <ResponsiveContainer width="100%" height="100%">
          {chart.type === 'line' ? (
            <LineChart data={data}>{common}{numeric.map((y, i) => <Line key={y} dataKey={y} stroke={SERIES[i % 2]} strokeWidth={2} dot={false} />)}</LineChart>
          ) : (
            <BarChart data={data}>{common}{numeric.map((y, i) => <Bar key={y} dataKey={y} fill={SERIES[i % 2]} radius={[3, 3, 0, 0]} />)}</BarChart>
          )}
        </ResponsiveContainer>
      </div>
    </Card>
  )
}

function AnswerBlock({ rfxId, analysis, onAsk }: { rfxId: string; analysis: Analysis; onAsk: (q: string) => void }) {
  const queryClient = useQueryClient()
  const { can } = usePersona()
  const save = useMutation({
    mutationFn: () => {
      const hint = analysis.scenario!
      const parts = [hint.single_vendor ? `Single vendor: ${hint.single_vendor}` : 'Split']
      if (hint.filters.quality_pass_only) parts.push('quality-cleared')
      if (hint.filters.exclude_vendors.length) parts.push(`without ${hint.filters.exclude_vendors.join(', ')}`)
      if (hint.filters.freight_inclusive) parts.push('freight included')
      return api.saveScenario(rfxId, { name: parts.join(', '), filters: hint.filters, single_vendor: hint.single_vendor, analysis_id: analysis.id })
    },
    onSuccess: (scenario) => {
      toast.success(`Scenario saved: ${scenario.name} · ${compact(scenario.computed.total_inr)} (recomputed by the award engine)`)
      void queryClient.invalidateQueries()
    },
    onError: (e) => toast.error(e.message),
  })
  const answered = analysis.status === 'answered'
  return (
    <article className="space-y-3">
      <div className="flex justify-end">
        <div className="max-w-[640px] rounded-panel rounded-br-sm bg-surface-3 px-3.5 py-2.5">{analysis.question}</div>
      </div>
      {analysis.status === 'cannot_answer' && (
        <Card className="flex gap-3 border-info-ink/20 bg-info-bg p-3.5 text-info-ink">
          <CircleSlash className="mt-0.5 size-4 shrink-0" />
          <div className="space-y-1">
            <div className="font-medium">This cannot be answered from the quote data.</div>
            <p>{analysis.answer}</p>
            {analysis.data_needed && <p><span className="font-medium">What it would take: </span>{analysis.data_needed}</p>}
          </div>
        </Card>
      )}
      {(analysis.status === 'query_failed' || analysis.status === 'model_error') && (
        <Card className="border-warning-border bg-warning-bg p-3.5 text-warning-ink">{analysis.answer}</Card>
      )}
      {answered && <p className="max-w-[900px] text-emphasis leading-relaxed">{analysis.answer}</p>}
      {answered && analysis.unverified_figures.length > 0 && (
        <p className="flex items-center gap-1.5 text-table text-danger-ink">
          <AlertTriangle className="size-3.5" /> These figures in the answer are not in the query result and were not verified: {analysis.unverified_figures.join(', ')}
        </p>
      )}
      {analysis.rows.length > 0 && (
        <div className="grid grid-cols-[minmax(0,3fr)_minmax(0,2fr)] gap-3">
          <Card className="max-h-[300px] overflow-auto">
            <table className="w-full border-collapse text-table">
              <thead className="sticky top-0 bg-surface-2">
                <tr>{analysis.columns.map((c) => <th key={c} scope="col" className="whitespace-nowrap px-3 py-2 text-left text-meta font-medium uppercase text-ink-muted">{c.replace(/_/g, ' ')}</th>)}</tr>
              </thead>
              <tbody>
                {analysis.rows.map((row, i) => (
                  <tr key={i} className="border-t border-border">
                    {row.map((value, j) => <td key={j} className={typeof value === 'number' ? 'whitespace-nowrap px-3 py-1.5 text-right font-mono' : 'px-3 py-1.5'}>{cellText(value)}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
          <ResultChart analysis={analysis} />
        </div>
      )}
      {answered && (
        <p className="flex gap-2 rounded-card border border-warning-border bg-warning-bg px-3 py-2 text-table text-warning-ink">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" /> {analysis.exclusions.text}
        </p>
      )}
      {analysis.sql && (
        <details className="rounded-card border border-border bg-surface-1">
          <summary className="cursor-pointer px-3 py-2 text-table font-medium">
            Query I ran <span className="font-normal text-ink-muted">· SQL on snapshot {analysis.snapshot} · {analysis.elapsed_ms ?? 0} ms · {analysis.rows_out ?? analysis.rows.length} rows out{analysis.attempts.length > 1 ? ' · repaired once' : ''}</span>
          </summary>
          {analysis.plan && <p className="border-t border-border px-3 py-2 text-table text-ink-muted">{analysis.plan}</p>}
          <pre className="overflow-x-auto border-t border-border bg-surface-2 p-3 font-mono text-table">{analysis.sql}</pre>
        </details>
      )}
      {answered && (
        <div className="flex flex-wrap items-center gap-2">
          {analysis.scenario && (
            <Button variant="primary" busy={save.isPending} disabled={!can('buyer', 'vp')} onClick={() => save.mutate()}><Save className="size-3.5" /> Save as award scenario</Button>
          )}
          <a href={fileUrl(`/analyses/${analysis.id}/export.xlsx`)}><Button><Download className="size-3.5" /> Export XLSX</Button></a>
          <a href={fileUrl(`/analyses/${analysis.id}/export.csv`)}><Button variant="ghost">CSV</Button></a>
          <span className="ml-auto text-meta text-ink-faint">{analysis.asked_by} · {when(analysis.created_at)}</span>
        </div>
      )}
      {analysis.follow_ups.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {analysis.follow_ups.map((q) => <button key={q} type="button" onClick={() => onAsk(q)} className="rounded-full border border-border px-2.5 py-1 text-left text-table text-ink-muted hover:bg-surface-2">{q}</button>)}
        </div>
      )}
    </article>
  )
}

export function Analyse() {
  const { rfxId = '' } = useParams()
  const queryClient = useQueryClient()
  const { can } = usePersona()
  const [question, setQuestion] = useState('')
  const end = useRef<HTMLDivElement>(null)
  const { data: grid, error } = useQuery({ queryKey: ['grid', rfxId], queryFn: () => api.grid(rfxId) })
  const { data: history } = useQuery({ queryKey: ['analyses', rfxId], queryFn: () => api.analyses(rfxId) })
  const { data: scenarios } = useQuery({ queryKey: ['scenarios', rfxId], queryFn: () => api.scenarios(rfxId) })
  const ask = useMutation({
    mutationFn: (q: string) => api.analyse(rfxId, q),
    onSuccess: () => {
      setQuestion('')
      void queryClient.invalidateQueries({ queryKey: ['analyses', rfxId] })
      void queryClient.invalidateQueries({ queryKey: ['overview', rfxId] })
    },
    onError: (e) => toast.error(e.message),
  })
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [history?.length, ask.isPending])
  if (error) return <ErrorNote error={error} />
  if (!grid) return <Loading />
  const submit = (q: string) => q.trim() && !ask.isPending && ask.mutate(q.trim())
  const vendors = [...grid.vendors].sort((a, b) => a.totals.extended_inr - b.totals.extended_inr)
  const allowed = can('buyer', 'vp')
  return (
    <div className="flex h-full flex-col">
      <AssumptionsBar rfxId={rfxId} assumptions={grid.assumptions} />
      <div className="grid min-h-0 flex-1 grid-cols-[250px_minmax(0,1fr)] gap-5">
        <aside className="space-y-2 overflow-y-auto pr-1">
          <Meta>Reference · counted totals</Meta>
          {vendors.map((v) => (
            <Card key={v.vendor_id} className="p-2.5">
              <div className="flex items-center justify-between gap-2"><span className="truncate font-medium">{v.name}</span><QualityPill quality={v.quality} /></div>
              <div className="font-mono text-emphasis font-medium">{compact(v.totals.extended_inr)}</div>
              <div className="text-meta text-ink-muted">{v.totals.lines_counted} of {grid.lines.length} lines counted{v.totals.needs_review ? ` · ${v.totals.needs_review} in review` : ''}{v.totals.not_quoted ? ` · ${v.totals.not_quoted} not quoted` : ''}</div>
            </Card>
          ))}
          <p className="text-meta text-ink-faint">Totals cover different lines, so they are not like for like. Ask the analyst to compare on common lines.</p>
          <Meta className="pt-2">Saved scenarios</Meta>
          {scenarios?.saved.length ? scenarios.saved.map((s) => (
            <div key={s.id} className="rounded-card bg-surface-2 px-2.5 py-1.5 text-table"><span className="font-medium">{s.name}</span> · <span className="font-mono">{compact(s.computed.total_inr)}</span></div>
          )) : <p className="text-table text-ink-muted">None yet. Ask a split-award question and save the answer.</p>}
          <Link to={`/rfx/${rfxId}/compare`} className="block pt-1 text-table font-medium text-accent-ink underline underline-offset-2">Open full grid</Link>
        </aside>

        <section className="flex min-h-0 flex-col">
          <div className="mb-3 flex items-start gap-2">
            <Sparkles className="mt-1 size-4 text-accent" />
            <div>
              <h1 className="text-title font-semibold tracking-tight">Analyse</h1>
              <p className="text-ink-muted">Ask anything about the {grid.lines.length} lines and {grid.vendors.length} vendors. Every answer shows the query it ran, and only counted cells are in it.</p>
            </div>
            {history && history.length > 0 && <Pill className="ml-auto">{history.length} asked</Pill>}
          </div>
          <div className="min-h-0 flex-1 space-y-7 overflow-y-auto pb-3 pr-1" aria-live="polite">
            {history?.map((a) => <AnswerBlock key={a.id} rfxId={rfxId} analysis={a} onAsk={submit} />)}
            {ask.isPending && (
              <div className="space-y-3">
                <div className="flex justify-end"><div className="max-w-[640px] rounded-panel rounded-br-sm bg-surface-3 px-3.5 py-2.5">{ask.variables}</div></div>
                <Loading label="Writing a query, running it in the sandbox, then writing the answer from the rows…" />
              </div>
            )}
            {history?.length === 0 && !ask.isPending && <p className="text-ink-muted">No questions yet. Try one of the suggestions below, or ask your own.</p>}
            <div ref={end} />
          </div>
          <form className="mt-2 border-t border-border pt-3" onSubmit={(e) => { e.preventDefault(); submit(question) }}>
            <div className="flex gap-2">
              <input className="h-10 w-full rounded-control border border-border-strong bg-surface-1 px-3 focus:outline-2 focus:outline-accent" aria-label="Question" placeholder={allowed ? 'Ask about the comparison…' : 'Switch to Category buyer or VP to ask'} disabled={!allowed} value={question} onChange={(e) => setQuestion(e.target.value)} />
              <Button type="submit" variant="primary" size="lg" busy={ask.isPending} disabled={!allowed || !question.trim()}>Ask</Button>
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {STARTERS.map((q) => <button key={q} type="button" disabled={!allowed || ask.isPending} onClick={() => submit(q)} className="max-w-[420px] truncate rounded-full border border-border px-2.5 py-1 text-table text-ink-muted hover:bg-surface-2 disabled:opacity-50" title={q}>{q}</button>)}
            </div>
          </form>
        </section>
      </div>
    </div>
  )
}
