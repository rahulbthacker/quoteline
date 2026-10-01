import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Save } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { Button, Card, ErrorNote, Loading, Meta, PageHeader, Pill } from '../components/ui'
import { api, type ConversionTable } from '../lib/api'
import { PERSONAS, usePersona } from '../lib/persona'
import { useTheme } from '../lib/theme'

const THRESHOLD_HELP: Record<string, string> = {
  agreement_tolerance_pct: 'Two readings within this percentage count as the same number',
  min_confidence: 'Agreeing readings are flagged if both models are below this',
  hard_min_confidence: 'Agreeing readings are flagged if either model is below this',
  match_accept: 'Line-match score accepted without asking a model',
  match_margin: 'Required lead over the runner-up line',
  match_floor: 'Below this the row is flagged unmatched',
  outlier_sigma: 'Standard deviations from the line median before a price is an outlier',
  outlier_min_deviation_pct: 'And it must differ from the median by at least this percentage',
}
const numInput = 'h-7 w-[92px] rounded-control border border-border-strong bg-surface-1 px-2 text-right font-mono text-table disabled:opacity-60'

export function Settings() {
  const queryClient = useQueryClient()
  const { persona, setPersona, can } = usePersona()
  const [theme, toggleTheme] = useTheme()
  const admin = can('admin')
  const { data, error, isPending } = useQuery({ queryKey: ['conversions'], queryFn: api.conversions })
  const { data: health } = useQuery({ queryKey: ['health'], queryFn: api.health })
  const { data: prompts } = useQuery({ queryKey: ['prompts'], queryFn: api.prompts })
  const { data: list } = useQuery({ queryKey: ['rfx-list'], queryFn: api.rfxList })
  const [table, setTable] = useState<ConversionTable | null>(null)
  useEffect(() => { if (data) setTable(structuredClone(data)) }, [data])
  const save = useMutation({
    mutationFn: () => api.saveConversions(table!),
    onSuccess: () => { toast.success('Conversion table saved. Every grid is recalculated from it on its next read.'); void queryClient.invalidateQueries() },
    onError: (e) => toast.error(e.message),
  })
  if (isPending || !table) return <div className="p-6"><Loading /></div>
  if (error) return <div className="p-6"><ErrorNote error={error} /></div>
  const dirty = JSON.stringify(table) !== JSON.stringify(data)
  const back = list?.[0] ? `/rfx/${list[0].id}/compare` : '/'
  return (
    <div className="mx-auto max-w-[1180px] px-6 py-5">
      <Link to={back} className="mb-3 inline-flex items-center gap-1 text-table text-accent-ink underline underline-offset-2"><ArrowLeft className="size-3.5" /> Back to the RFx</Link>
      <PageHeader title="Settings" sub="Conversion table, thresholds, models and prompts. The arithmetic that reaches the grid comes from here, never from a model.">
        <label className="flex items-center gap-1.5 text-table"><span className="text-ink-muted">Viewing as</span>
          <select className="rounded-control border border-border-strong bg-surface-1 px-2 py-1" value={persona} onChange={(e) => setPersona(e.target.value as typeof persona)}>{PERSONAS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}</select>
        </label>
        <Button variant="ghost" onClick={toggleTheme}>{theme === 'dark' ? 'Light theme' : 'Dark theme'}</Button>
        <Button variant="primary" busy={save.isPending} disabled={!admin || !dirty} title={admin ? undefined : 'Only the admin persona can edit settings'} onClick={() => save.mutate()}><Save className="size-3.5" /> Save</Button>
      </PageHeader>
      {!admin && <p className="mb-3 rounded-card border border-border bg-surface-2 px-3 py-2 text-table text-ink-muted">Read-only. Switch to the Admin persona to edit.</p>}

      <div className="grid grid-cols-[minmax(0,3fr)_minmax(0,2fr)] gap-4">
        <Card className="overflow-hidden">
          <div className="border-b border-border px-3.5 py-2.5"><h2 className="text-emphasis font-medium">Conversion table</h2><p className="text-table text-ink-muted">Every unit a vendor may quote in, and its factor to {table.base_unit.replace(/_/g, ' ')}.</p></div>
          <table className="w-full border-collapse text-table">
            <thead><tr className="bg-surface-2 text-left text-meta font-medium uppercase text-ink-muted"><th scope="col" className="px-3.5 py-2">Unit</th><th scope="col" className="px-2">Rule</th><th scope="col" className="px-2 text-right">Factor</th><th scope="col" className="px-3.5">Recognised wording</th></tr></thead>
            <tbody>
              {Object.entries(table.units).map(([code, unit]) => {
                const rules = unit.interpretations ?? [{ id: code, label: unit.label, to_base: unit.to_base! }]
                return rules.map((rule, index) => (
                  <tr key={code + rule.id} className="border-t border-border align-top">
                    <td className="px-3.5 py-2">{index === 0 && <><div className="font-medium">{unit.label}</div>{unit.ambiguous && <Pill tone="warning" title={unit.reason}>ambiguous: always reviewed</Pill>}</>}</td>
                    <td className="px-2 py-2 text-ink-muted">{unit.ambiguous ? rule.label : ''} {rule.to_base.op === 'weight' ? '× board weight ×' : rule.to_base.op === 'pack' ? '÷ pack size ×' : '×'}</td>
                    <td className="px-2 py-1.5 text-right">
                      <input className={numInput} aria-label={`${unit.label} factor`} inputMode="decimal" disabled={!admin} value={rule.to_base.factor}
                        onChange={(e) => {
                          const next = structuredClone(table)
                          const target = next.units[code]
                          const factor = Number(e.target.value) || 0
                          if (target.interpretations) target.interpretations[index].to_base.factor = factor
                          else target.to_base!.factor = factor
                          setTable(next)
                        }} />
                    </td>
                    <td className="px-3.5 py-2 font-mono text-meta text-ink-muted">{index === 0 ? unit.aliases.join(' · ') : ''}</td>
                  </tr>
                ))
              })}
            </tbody>
          </table>
        </Card>

        <div className="space-y-4">
          <Card className="p-3.5">
            <h2 className="mb-2 text-emphasis font-medium">Thresholds</h2>
            <div className="space-y-2">
              {Object.entries(table.thresholds).map(([name, value]) => (
                <label key={name} className="flex items-center justify-between gap-3 text-table">
                  <span><span className="font-mono">{name}</span><span className="block text-meta text-ink-faint">{THRESHOLD_HELP[name]}</span></span>
                  <input className={numInput} inputMode="decimal" disabled={!admin} value={value} onChange={(e) => setTable({ ...table, thresholds: { ...table.thresholds, [name]: Number(e.target.value) || 0 } })} />
                </label>
              ))}
            </div>
          </Card>
          <Card className="p-3.5">
            <h2 className="mb-1 text-emphasis font-medium">FX policy</h2>
            <p className="text-table text-ink-muted">The FX rate, source and date belong to each RFx. Edit them from the assumptions bar on Compare, Analyse or Award; the change is audited and every converted price is recalculated.</p>
          </Card>
          <Card className="p-3.5">
            <h2 className="mb-2 text-emphasis font-medium">Models by role</h2>
            <div className="space-y-1 text-table">
              {health && Object.entries(health.roles).map(([role, chain]) => <div key={role} className="flex justify-between gap-3"><span className="text-ink-muted">{role}</span><span className="font-mono">{chain.join(' → ')}</span></div>)}
            </div>
            <p className="mt-2 text-meta text-ink-faint">Set in .env. A failed call is retried once, then the next model in the chain is tried, then the item is flagged model_error.</p>
            {health && <div className="mt-2 flex gap-1.5">{Object.entries(health.keys).map(([p, ok]) => <Pill key={p} tone={ok ? 'success' : 'danger'}>{p} key {ok ? 'set' : 'missing'}</Pill>)}</div>}
          </Card>
        </div>
      </div>

      <Card className="mt-4 p-3.5">
        <h2 className="mb-2 text-emphasis font-medium">Prompts</h2>
        <div className="space-y-1.5">
          {prompts?.map((p) => (
            <details key={p.version} className="rounded-control border border-border">
              <summary className="cursor-pointer px-3 py-2 text-table"><span className="font-mono font-medium">{p.version}</span> <span className="text-ink-muted">· {p.purpose}</span></summary>
              <pre className="max-h-[320px] overflow-auto whitespace-pre-wrap border-t border-border bg-surface-2 p-3 font-mono text-meta">{p.text}</pre>
            </details>
          ))}
        </div>
        <Meta className="mt-2">The version of the prompt used is stored on every traced call.</Meta>
      </Card>
    </div>
  )
}
