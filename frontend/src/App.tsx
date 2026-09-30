import { TraceTable } from './components/trace-table'
import { useTheme } from './lib/theme'

export default function App() {
  const [theme, toggleTheme] = useTheme()
  return (
    <div className="min-h-screen bg-surface-0 text-ink">
      <header className="flex h-[52px] items-center gap-4 border-b border-border bg-surface-1 px-5">
        <div className="flex items-center gap-2">
          <img src="/favicon.svg" alt="" className="size-6" />
          <span className="text-emphasis font-semibold tracking-tight">Quoteline</span>
        </div>
        <span className="rounded-full bg-info-bg px-2 py-0.5 text-meta font-medium text-info-ink">
          Checkpoint A · scaffold
        </span>
        <button
          type="button"
          onClick={toggleTheme}
          className="ml-auto rounded-control border border-border-strong bg-surface-1 px-3 py-1.5 text-table"
        >
          {theme === 'dark' ? 'Light theme' : 'Dark theme'}
        </button>
      </header>
      <main className="mx-auto max-w-[1200px] p-6">
        <h1 className="text-title font-semibold">Model calls</h1>
        <p className="mb-4 mt-1 text-ink-muted">
          Every call is traced: role, model, prompt version, tokens, latency and cost.
        </p>
        <TraceTable />
      </main>
    </div>
  )
}
