import { useQuery } from '@tanstack/react-query'
import { Activity, Check, Inbox, ListChecks, Moon, Paperclip, Settings, Sun } from 'lucide-react'
import { useState } from 'react'
import { NavLink, Outlet, useNavigate, useParams } from 'react-router-dom'
import { api, overviewApi, type Overview } from '../lib/api'
import { cn } from '../lib/cn'
import { PERSONAS, usePersona } from '../lib/persona'
import { useTheme } from '../lib/theme'
import type { Persona } from '../lib/types'
import { RunInspector } from './run-inspector'
import { Button, Pill } from './ui'

type Stage = { key: string; label: string; sub: string; done: boolean }

function stages(o: Overview | undefined): Stage[] {
  const awardLabel: Record<string, string> = {
    draft: 'draft', sent_for_approval: 'awaiting approval', approved: 'approved', changes_requested: 'changes requested',
  }
  return [
    { key: 'draft', label: 'Draft', sub: o ? `Co-pilot, ${o.lines} lines` : '', done: !!o },
    { key: 'sent', label: 'Sent', sub: o?.sent ? `${o.sent} vendors` : 'not sent', done: !!o?.sent },
    { key: 'responses', label: 'Responses', sub: o ? `${o.replies} of ${o.vendors} in` : '', done: !!o && o.replies > 0 },
    {
      key: 'compare', label: 'Compare',
      sub: !o?.replies ? 'no replies read' : o.review_open ? `${o.review_open} items to review` : `resolved · ${o.overrides} overrides`,
      done: !!o && o.replies > 0 && o.review_open === 0,
    },
    { key: 'analyse', label: 'Analyse', sub: o?.scenarios ? `${o.scenarios} scenarios saved` : 'no scenarios yet', done: !!o?.scenarios },
    { key: 'award', label: 'Award', sub: o?.award_status ? awardLabel[o.award_status] : 'not drafted', done: o?.award_status === 'approved' },
  ]
}

const statusPill = (o: Overview | undefined) => {
  if (!o) return ''
  if (o.award_status) return `Award · ${o.award_status.replace(/_/g, ' ')}`
  if (o.replies) return `Comparing · ${o.replies} of ${o.vendors} replies read`
  return o.sent ? 'Sent · awaiting replies' : 'Draft'
}

export function Shell() {
  const { rfxId = '' } = useParams()
  const navigate = useNavigate()
  const { persona, setPersona } = usePersona()
  const [theme, toggleTheme] = useTheme()
  const [inspector, setInspector] = useState(false)
  const { data: overview } = useQuery({ queryKey: ['overview', rfxId], queryFn: () => overviewApi(rfxId), enabled: !!rfxId, refetchInterval: 15000 })
  const { data: list } = useQuery({ queryKey: ['rfx-list'], queryFn: api.rfxList })

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-surface-0 text-ink">
      <header className="flex h-[52px] shrink-0 items-center gap-4 border-b border-border bg-surface-1 px-5">
        <div className="flex w-[196px] items-center gap-2">
          <img src="/favicon.svg" alt="" className="size-6" />
          <span className="text-emphasis font-semibold tracking-tight">Quoteline</span>
        </div>
        <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-2">
          <span className="text-ink-faint">RFx</span>
          <span className="text-ink-faint">/</span>
          <select
            aria-label="RFx"
            value={rfxId}
            onChange={(event) => navigate(`/rfx/${event.target.value}/compare`)}
            className="max-w-[360px] truncate bg-transparent font-medium focus:outline-none"
          >
            {(list ?? []).map((r) => (
              <option key={r.id} value={r.id}>{r.id} · {r.title}</option>
            ))}
          </select>
          {overview && <Pill tone="info">{statusPill(overview)}</Pill>}
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <label className="flex items-center gap-1.5 rounded-control border border-border-strong px-2.5 py-1 text-table" title="Persona switcher: a demo device that stands in for sign-in and roles">
            <span className="text-ink-muted">Viewing as:</span>
            <select
              value={persona}
              onChange={(event) => setPersona(event.target.value as Persona)}
              className="bg-transparent font-medium focus:outline-none"
            >
              {PERSONAS.map((p) => (
                <option key={p.id} value={p.id}>{p.label}</option>
              ))}
            </select>
          </label>
          <Button variant="ghost" onClick={() => setInspector(true)}>
            <Activity className="size-3.5" /> Run inspector
          </Button>
          <Button variant="ghost" size="sm" aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'} onClick={toggleTheme}>
            {theme === 'dark' ? <Sun className="size-4" /> : <Moon className="size-4" />}
          </Button>
          <div className="flex size-7 items-center justify-center rounded-full bg-surface-3 text-meta font-medium" aria-label="Signed in as Rahul Thacker">RT</div>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <aside className="flex w-[212px] shrink-0 flex-col border-r border-border bg-surface-1 p-3">
          <div className="px-2 pb-2 text-meta font-medium uppercase tracking-wide text-ink-faint">Stages</div>
          <nav aria-label="Stages" className="space-y-0.5">
            {stages(overview).map((stage, index) => (
              <NavLink
                key={stage.key}
                to={`/rfx/${rfxId}/${stage.key}`}
                className={({ isActive }) => cn('flex items-start gap-2.5 rounded-card px-2 py-2', isActive ? 'bg-accent-bg' : 'hover:bg-surface-2')}
              >
                {({ isActive }) => (
                  <>
                    <span
                      className={cn(
                        'mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full text-meta font-medium',
                        isActive ? 'bg-accent text-on-accent' : stage.done ? 'bg-success-bg text-success-ink' : 'border border-border-strong text-ink-muted',
                      )}
                    >
                      {stage.done && !isActive ? <Check className="size-3" /> : index + 1}
                    </span>
                    <span className="min-w-0">
                      <span className="block font-medium leading-tight">{stage.label}</span>
                      <span className="block text-meta text-ink-faint">{stage.sub}</span>
                    </span>
                  </>
                )}
              </NavLink>
            ))}
          </nav>
          <div className="my-3 border-t border-border" />
          <nav aria-label="Shortcuts" className="space-y-0.5">
            <RailLink to={`/rfx/${rfxId}/review`} icon={<ListChecks className="size-3.5" />} label="Review queue" count={overview?.review_open} />
            <RailLink to={`/rfx/${rfxId}/responses`} icon={<Inbox className="size-3.5" />} label="Vendor inbox" />
            <RailLink to={`/rfx/${rfxId}/responses?tab=attachments`} icon={<Paperclip className="size-3.5" />} label="Attachments" />
            <RailLink to="/settings" icon={<Settings className="size-3.5" />} label="Settings" />
          </nav>
          {overview && (
            <button
              type="button"
              onClick={() => setInspector(true)}
              className="mt-auto rounded-card bg-surface-2 p-2.5 text-left text-meta hover:bg-surface-3"
            >
              <div className="font-medium text-ink">This run</div>
              <div className="font-mono text-ink-muted">
                {overview.run.model_calls} model calls · ₹{overview.run.cost_inr.toFixed(0)}
                {overview.run.failed_calls ? ` · ${overview.run.failed_calls} retried` : ''}
              </div>
              <div className="font-mono text-ink-muted">
                Extraction agreement {overview.run.agreement === null ? '–' : `${(overview.run.agreement * 100).toFixed(1)}%`}
              </div>
            </button>
          )}
        </aside>
        <main className="min-w-0 flex-1 overflow-y-auto px-6 py-5">
          <Outlet />
        </main>
      </div>
      <RunInspector open={inspector} onOpenChange={setInspector} />
    </div>
  )
}

function RailLink({ to, icon, label, count }: { to: string; icon: React.ReactNode; label: string; count?: number }) {
  return (
    <NavLink
      to={to}
      end
      className={({ isActive }) => cn('flex items-center gap-2 rounded-card px-2 py-1.5 font-medium', isActive ? 'bg-accent-bg' : 'hover:bg-surface-2')}
    >
      <span className="text-ink-muted">{icon}</span>
      {label}
      {count ? <Pill tone="warning" mono className="ml-auto">{count}</Pill> : null}
    </NavLink>
  )
}
