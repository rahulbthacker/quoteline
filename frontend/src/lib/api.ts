import type {
  Analysis, AuditEvent, AwardView, CellDetail, Grid, OutboxItem, Persona, Preset, Reply, ReviewItem,
  RfxDraft, RfxView, Scenario, ScenarioFilters, Trace, VendorQuality,
} from './types'

let persona: Persona = (localStorage.getItem('quoteline-persona') as Persona) || 'buyer'
export const setApiPersona = (next: Persona) => {
  persona = next
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method,
    headers: { 'X-Persona': persona, ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try {
      const payload = await response.json()
      detail = typeof payload.detail === 'string' ? payload.detail : JSON.stringify(payload.detail)
    } catch {
      /* keep the status text */
    }
    throw new ApiError(response.status, detail)
  }
  return response.json() as Promise<T>
}

const get = <T,>(path: string) => request<T>('GET', path)
const post = <T,>(path: string, body: unknown = {}) => request<T>('POST', path, body)

export const fileUrl = (path: string) => `/api${path}`

export const api = {
  health: () => get<{ status: string; roles: Record<string, string[]>; keys: Record<string, boolean> }>('/health'),
  rfxList: () => get<{ id: string; title: string; status: string; lines: number }[]>('/rfx'),
  rfx: (id: string) => get<RfxView>(`/rfx/${id}`),
  updateRfx: (id: string, rfx: unknown) => request<{ ok: boolean }>('PUT', `/rfx/${id}`, rfx),
  updateAssumptions: (id: string, body: unknown) => request<{ ok: boolean }>('PUT', `/rfx/${id}/assumptions`, body),
  intakeChat: (messages: { role: string; content: string }[], draft: RfxDraft | null) =>
    post<{ reply: string; draft: RfxDraft; model: string }>('/intake/chat', { messages, draft }),
  createRfx: (draft: RfxDraft) => post<{ id: string }>('/rfx', { draft }),
  send: (id: string) => post<{ sent: { vendor_id: string; to: string; path: string }[] }>(`/rfx/${id}/send`),
  outbox: (id: string) => get<OutboxItem[]>(`/rfx/${id}/outbox`),
  inbox: (id: string) => get<Record<string, string[]>>(`/rfx/${id}/inbox`),
  deliverSeed: (id: string) => post<{ delivered: Record<string, string[]> }>(`/rfx/${id}/inbox/deliver-seed`),
  startIngest: (id: string) => post<IngestStatus>(`/rfx/${id}/ingest`),
  ingestStatus: (id: string) => get<IngestStatus>(`/rfx/${id}/ingest`),
  replies: (id: string) => get<Reply[]>(`/rfx/${id}/replies`),
  grid: (id: string) => get<Grid>(`/rfx/${id}/grid`),
  cell: (id: string, vendor: string, line: string) => get<CellDetail>(`/rfx/${id}/cells/${vendor}/${line}`),
  override: (id: string, vendor: string, line: string, body: { value?: number; exclude?: boolean; reason: string }) =>
    post<{ ok: boolean }>(`/rfx/${id}/cells/${vendor}/${line}/override`, body),
  revert: (id: string, vendor: string, line: string) =>
    request<{ ok: boolean }>('DELETE', `/rfx/${id}/cells/${vendor}/${line}/override`),
  review: (id: string) => get<ReviewItem[]>(`/rfx/${id}/review`),
  resolve: (id: string, item: string, body: { option_id?: string; value?: number; amount?: number; reason?: string }) =>
    post<ReviewItem>(`/rfx/${id}/review/${item}/resolve`, body),
  reopen: (id: string, item: string) => post<ReviewItem>(`/rfx/${id}/review/${item}/reopen`),
  askVendor: (id: string, itemIds: string[]) =>
    post<{ vendor_id: string; to: string; subject: string; body: string; path: string; model: string }>(
      `/rfx/${id}/review/ask-vendor`, { item_ids: itemIds },
    ),
  quality: (id: string) => get<VendorQuality[]>(`/rfx/${id}/quality`),
  qualityOverride: (id: string, vendor: string, question: string, body: { status: string; reason: string }) =>
    post<{ ok: boolean }>(`/rfx/${id}/quality/${vendor}/${question}/override`, body),
  audit: (id: string) => get<AuditEvent[]>(`/rfx/${id}/audit`),
  analyse: (id: string, question: string) => post<Analysis>(`/rfx/${id}/analyse`, { question }),
  analyses: (id: string) => get<Analysis[]>(`/rfx/${id}/analyses`),
  scenarios: (id: string) => get<{ saved: Scenario[]; presets: Preset[] }>(`/rfx/${id}/scenarios`),
  saveScenario: (id: string, body: { name: string; filters: ScenarioFilters; single_vendor?: string | null; analysis_id?: string }) =>
    post<Scenario>(`/rfx/${id}/scenarios`, body),
  award: (id: string) => get<AwardView>(`/rfx/${id}/award`),
  setAward: (id: string, scenarioId: string) => post<AwardView>(`/rfx/${id}/award`, { scenario_id: scenarioId }),
  awardAction: (awardId: string, action: 'send-for-approval' | 'approve' | 'request-changes', note?: string) =>
    post<AwardView>(`/award/${awardId}/${action}`, { note }),
  traces: (rfxId?: string) => get<Trace[]>(rfxId ? `/traces?rfx_id=${rfxId}` : '/traces'),
  allTraces: () => get<Trace[]>('/traces'),
  prompts: () => get<{ version: string; purpose: string; text: string }[]>('/prompts'),
  conversions: () => get<ConversionTable>('/settings/conversions'),
  saveConversions: (table: ConversionTable) => request<ConversionTable>('PUT', '/settings/conversions', table),
  evalReport: () => get<EvalReport>('/eval/report'),
}

export type IngestStatus = { status: 'idle' | 'running' | 'done' | 'failed'; started_at?: string; finished_at?: string; error?: string; summary?: { calls: number; failed_calls: number; cost_inr: number } }

export type ConversionTable = {
  base_unit: string
  units: Record<string, { label: string; aliases: string[]; ambiguous?: boolean; reason?: string; to_base?: { op: string; factor: number }; interpretations?: { id: string; label: string; to_base: { op: string; factor: number } }[] }>
  currencies: Record<string, { symbols: string[] }>
  thresholds: Record<string, number>
}

export type EvalReport = {
  generated_at: string
  ingest_run: string
  method: string
  headline: {
    primary_accuracy: Record<string, number>
    secondary_accuracy: Record<string, number>
    rows_scored_per_model: number
    agreement_rate: number | null
    flag_precision: number | null
    flags_raised: number
    missed_problems: number
    free_text_score: number | null
    quality_verdict_accuracy: number | null
    ingest_calls: number
    ingest_cost_inr: number
    mean_extraction_latency_s: number
  }
  vendors: {
    vendor_id: string
    vendor: string
    format: string
    agreement: number | null
    models: Record<string, { model: string | null; rows: number; accuracy: Record<string, number | null>; errors: string[]; free_text_score: number | null; latency_s?: number; cost_inr?: number }>
    flags_expected_met: string[]
    flags_missed: string[]
    flags_unexpected: string[]
  }[]
}

export type Overview = {
  rfx_id: string
  title: string
  status: string
  lines: number
  vendors: number
  sent: number
  replies: number
  review_open: number
  review_total: number
  cells_in_review: number
  overrides: number
  scenarios: number
  award_status: string | null
  run: Grid['run']
}

export const overviewApi = (id: string) => get<Overview>(`/rfx/${id}/overview`)
