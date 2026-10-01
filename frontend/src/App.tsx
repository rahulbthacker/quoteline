import { useQuery } from '@tanstack/react-query'
import { Navigate, Route, Routes } from 'react-router-dom'
import { Toaster } from 'sonner'
import { Shell } from './components/shell'
import { Loading } from './components/ui'
import { api } from './lib/api'
import { Analyse } from './routes/analyse'
import { Award } from './routes/award'
import { Compare } from './routes/compare'
import { Draft } from './routes/draft'
import { Responses } from './routes/responses'
import { Review } from './routes/review'
import { Sent } from './routes/sent'
import { Settings } from './routes/settings'

function Home() {
  const { data, isPending, error } = useQuery({ queryKey: ['rfx-list'], queryFn: api.rfxList })
  if (isPending) return <Loading />
  if (error || !data.length)
    return (
      <div className="p-10 text-ink-muted">
        No RFx is loaded. Run <code className="font-mono">make demo</code>, which seeds the RFx, sends it and reads the five vendor replies.
      </div>
    )
  return <Navigate to={`/rfx/${data[0].id}/compare`} replace />
}

export default function App() {
  return (
    <>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/rfx/:rfxId" element={<Shell />}>
          <Route index element={<Navigate to="compare" replace />} />
          <Route path="draft" element={<Draft />} />
          <Route path="sent" element={<Sent />} />
          <Route path="responses" element={<Responses />} />
          <Route path="compare" element={<Compare />} />
          <Route path="review" element={<Review />} />
          <Route path="analyse" element={<Analyse />} />
          <Route path="award" element={<Award />} />
          <Route path="*" element={<Navigate to="../compare" replace />} />
        </Route>
        <Route path="/settings" element={<Settings />} />
      </Routes>
      <Toaster position="bottom-right" toastOptions={{ style: { background: 'var(--surface-1)', color: 'var(--ink)', border: '1px solid var(--border-strong)' } }} />
    </>
  )
}
