import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Send } from 'lucide-react'
import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { Button, Card, Empty, ErrorNote, Loading, Modal, PageHeader, Pill } from '../components/ui'
import { api } from '../lib/api'
import { when } from '../lib/format'
import { usePersona } from '../lib/persona'
import type { OutboxItem } from '../lib/types'

const KIND: Record<string, string> = { rfx: 'RFx', clarification: 'Clarification', approval_request: 'Approval request' }

export function Sent() {
  const { rfxId = '' } = useParams()
  const queryClient = useQueryClient()
  const { can } = usePersona()
  const [open, setOpen] = useState<OutboxItem | null>(null)
  const { data, error, isPending } = useQuery({ queryKey: ['outbox', rfxId], queryFn: () => api.outbox(rfxId) })
  const send = useMutation({
    mutationFn: () => api.send(rfxId),
    onSuccess: (r) => { toast.success(`RFx written to the outbox for ${r.sent.length} vendors.`); void queryClient.invalidateQueries() },
    onError: (e) => toast.error(e.message),
  })
  if (isPending) return <Loading />
  if (error) return <ErrorNote error={error} />
  const rfxSent = data.some((m) => m.kind === 'rfx')
  return (
    <div>
      <PageHeader title="Sent" sub="Outbox log. Email transport is the one stub in the system: sending writes a real .eml file to mail/outbox/ and nothing leaves this machine.">
        <Button variant="primary" busy={send.isPending} disabled={!can('buyer')} onClick={() => send.mutate()}>
          <Send className="size-3.5" /> {rfxSent ? 'Send the RFx again' : 'Send the RFx to vendors'}
        </Button>
      </PageHeader>
      {data.length === 0 ? (
        <Empty title="Nothing has been sent">Send the RFx to write one email per vendor to the outbox.</Empty>
      ) : (
        <Card className="overflow-hidden">
          <table className="w-full border-collapse">
            <thead>
              <tr className="bg-surface-2 text-left text-meta font-medium uppercase text-ink-muted">
                <th scope="col" className="px-3 py-2">When</th><th scope="col" className="px-3">Kind</th><th scope="col" className="px-3">To</th><th scope="col" className="px-3">Subject</th><th scope="col" className="px-3">Status</th><th scope="col" className="px-3">File</th>
              </tr>
            </thead>
            <tbody>
              {data.map((m) => (
                <tr key={m.id} className="h-10 cursor-pointer border-t border-border hover:bg-surface-2" onClick={() => setOpen(m)}>
                  <td className="whitespace-nowrap px-3 font-mono text-table text-ink-muted">{when(m.created_at)}</td>
                  <td className="px-3"><Pill tone={m.kind === 'rfx' ? 'info' : 'accent'}>{KIND[m.kind] ?? m.kind}</Pill></td>
                  <td className="px-3">{m.to}</td>
                  <td className="px-3"><button type="button" className="text-left font-medium underline-offset-2 hover:underline">{m.subject}</button></td>
                  <td className="px-3"><Pill tone={m.status === 'sent' ? 'success' : 'warning'}>{m.status === 'sent' ? 'written to outbox' : 'draft, not sent'}</Pill></td>
                  <td className="px-3 font-mono text-meta text-ink-faint">{m.path}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
      {open && (
        <Modal open onOpenChange={(o) => !o && setOpen(null)} title={open.subject} sub={`To ${open.to} · ${open.path}`}>
          <pre className="max-h-[60vh] overflow-y-auto whitespace-pre-wrap rounded-control bg-surface-2 p-3 font-sans text-table">{open.body}</pre>
        </Modal>
      )}
    </div>
  )
}
