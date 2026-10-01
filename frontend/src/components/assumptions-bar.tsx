import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Info } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { api } from '../lib/api'
import { usePersona } from '../lib/persona'
import type { Grid } from '../lib/types'
import { Button, Field, inputClass, Modal } from './ui'

/** The system's assumptions are always on screen: unit, FX with source and date, freight, tax. */
export function AssumptionsBar({ rfxId, assumptions }: { rfxId: string; assumptions: Grid['assumptions'] }) {
  const [open, setOpen] = useState(false)
  const { can } = usePersona()
  const items: [string, string][] = [
    ['Base unit', assumptions.base_unit],
    ['FX', assumptions.fx],
    ['Freight', /excluded/i.test(assumptions.freight) ? 'excluded, shown per vendor' : assumptions.freight],
    ['Tax', /excluded/i.test(assumptions.tax) ? 'GST excluded' : assumptions.tax],
  ]
  return (
    <div className="mb-4 flex flex-wrap items-center gap-x-5 gap-y-1 rounded-card border border-border bg-surface-1 px-3 py-2 text-table">
      <span className="flex items-center gap-1.5 font-medium">
        <Info className="size-3.5 text-ink-muted" /> Assumptions in force
      </span>
      {items.map(([label, value]) => (
        <span key={label}>
          <span className="text-ink-muted">{label} </span>
          <span className="font-medium">{value}</span>
        </span>
      ))}
      <button
        type="button"
        className="ml-auto font-medium text-accent-ink underline underline-offset-2 disabled:text-ink-faint disabled:no-underline"
        disabled={!can('buyer', 'admin')}
        title={can('buyer', 'admin') ? undefined : 'Only the buyer or admin can edit assumptions'}
        onClick={() => setOpen(true)}
      >
        Edit assumptions
      </button>
      {open && <EditAssumptions rfxId={rfxId} onClose={() => setOpen(false)} />}
    </div>
  )
}

function EditAssumptions({ rfxId, onClose }: { rfxId: string; onClose: () => void }) {
  const queryClient = useQueryClient()
  const { data } = useQuery({ queryKey: ['rfx', rfxId], queryFn: () => api.rfx(rfxId) })
  const [form, setForm] = useState<{ rate: string; source: string; asOf: string } | null>(null)
  const fx = data?.rfx.fx_policy
  const value = form ?? (fx ? { rate: String(fx.rate), source: fx.source, asOf: fx.as_of } : null)
  const save = useMutation({
    mutationFn: () => api.updateAssumptions(rfxId, { fx_rate: Number(value!.rate), fx_source: value!.source, fx_as_of: value!.asOf }),
    onSuccess: () => {
      toast.success('Assumptions updated. Every converted price was recalculated.')
      void queryClient.invalidateQueries()
      onClose()
    },
    onError: (error) => toast.error(error.message),
  })
  return (
    <Modal open onOpenChange={(open) => !open && onClose()} title="Edit assumptions" sub="Changing the FX rate recalculates every price quoted in a foreign currency. The change is written to the audit log.">
      {value && fx && (
        <div className="space-y-3">
          <Field label={`${fx.foreign_currency} to INR rate`} hint="Used by the fx step of the normalisation trace.">
            <input className={inputClass} inputMode="decimal" value={value.rate} onChange={(e) => setForm({ ...value, rate: e.target.value })} />
          </Field>
          <Field label="Source">
            <input className={inputClass} value={value.source} onChange={(e) => setForm({ ...value, source: e.target.value })} />
          </Field>
          <Field label="As of">
            <input className={inputClass} type="date" value={value.asOf} onChange={(e) => setForm({ ...value, asOf: e.target.value })} />
          </Field>
          <div className="flex justify-end gap-2 pt-1">
            <Button onClick={onClose}>Cancel</Button>
            <Button variant="primary" busy={save.isPending} disabled={!(Number(value.rate) > 0)} onClick={() => save.mutate()}>Save</Button>
          </div>
        </div>
      )}
    </Modal>
  )
}
