// Mirrors backend/app/schemas. Kept by hand; the API is the contract.

export type CellState = 'confident' | 'needs_review' | 'not_quoted' | 'overridden'
export type Persona = 'buyer' | 'vp' | 'evaluator' | 'admin'

export type SourceRef = {
  file: string
  locator: string
  snippet: string
  snippet_verified: boolean | null
}

export type ModelReading = {
  role: 'primary' | 'secondary'
  model: string
  raw_value: number | null
  raw_unit: string | null
  unit_code: string
  raw_currency: string | null
  confidence: number
  alternatives: number[]
  not_quoted: boolean
  notes: string | null
  match_reason: string | null
  source_ref: SourceRef
}

export type Step = { op: string; factor: number; value_in: number; value_out: number; source: string }

export type Override = { action: 'override' | 'exclude'; value: number | null; actor: string; reason: string; at: string }

export type QuoteCell = {
  vendor_id: string
  line_id: string
  state: CellState
  inr_per_base: number | null
  display_inr: number | null
  extended_inr: number | null
  excluded: boolean
  is_lowest: boolean
  how: string
  raw_display: string | null
  annotation: string | null
  readings: ModelReading[]
  agreement: number | null
  normalization_trace: Step[]
  flag_reason: string | null
  review_item_ids: string[]
  resolution_note: string | null
  override: Override | null
}

export type ReviewOption = {
  option_id: string
  label: string
  inr_per_base: number | null
  note: string | null
  normalization_trace: Step[]
  lines: string[]
}

export type ReviewItem = {
  id: string
  vendor_id: string
  vendor_name: string
  cells: { vendor_id: string; line_id: string }[]
  kind: string
  title: string
  reason: string
  evidence: string | null
  source: SourceRef | null
  readings: ModelReading[]
  agreement: number | null
  options: ReviewOption[]
  blocks_cells: boolean
  status: 'open' | 'resolved' | 'asked_vendor'
  resolution: Record<string, unknown> | null
  detail: Record<string, unknown>
}

export type Freight = { kind: 'included' | 'lump_sum' | 'extra_unpriced' | 'not_stated'; amount_inr: number | null; statement: string | null }

export type GridVendor = {
  vendor_id: string
  name: string
  has_reply: boolean
  format: string | null
  format_label: string | null
  file: string | null
  lines_quoted: number
  currency: string | null
  quality: 'Pass' | 'Partial' | 'Fail' | null
  freight: Freight
  totals: { extended_inr: number; lines_counted: number; needs_review: number; not_quoted: number; excluded: number }
  agreement: number | null
  models: Record<string, string | null>
  extraction_error: string | null
}

export type GridLine = {
  line_id: string
  description: string
  qty: number
  uom: string
  last_year_inr: number | null
  cells: Record<string, QuoteCell>
}

export type Grid = {
  rfx_id: string
  title: string
  assumptions: { base_unit: string; fx: string; freight: string; tax: string }
  vendors: GridVendor[]
  lines: GridLine[]
  review_open: number
  review_blocking_cells: number
  counts: Record<CellState, number>
  run: { model_calls: number; failed_calls: number; cost_inr: number; latency_s: number; agreement: number | null }
}

export type CellDetail = {
  cell: QuoteCell
  line: { line_id: string; description: string; qty: number; uom: string; last_year_inr: number | null }
  vendor: { vendor_id: string; name: string; file: string | null; format: string | null; file_url: string | null }
  review_items: ReviewItem[]
  others: Record<string, number | null>
  history: AuditEvent[]
}

export type AuditEvent = {
  id: number
  actor_kind: 'system' | 'user'
  actor: string
  action: string
  summary: string
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
  at: string
}

export type Trace = {
  call_id: string
  parent_run_id: string | null
  rfx_id: string | null
  role: string
  provider: string
  model: string
  served_model: string | null
  prompt_version: string
  attempt: number
  status: 'ok' | 'error'
  error: string | null
  input_tokens: number | null
  output_tokens: number | null
  latency_ms: number
  cost_inr: number | null
  agreement: number | null
  provider_request_id: string | null
  created_at: string
}

export type Chart = { type: 'bar' | 'line' | 'none'; x: string | null; y: string[]; title: string | null }

export type Analysis = {
  id: string
  question: string
  status: 'answered' | 'cannot_answer' | 'query_failed' | 'model_error'
  plan: string | null
  sql: string | null
  columns: string[]
  rows: (string | number | boolean | null)[][]
  answer: string | null
  chart: Chart | null
  follow_ups: string[]
  scenario: { filters: ScenarioFilters; single_vendor: string | null } | null
  unverified_figures: string[]
  exclusions: { in_review: string[]; not_quoted: string[]; excluded: string[]; text: string }
  data_needed?: string | null
  elapsed_ms?: number
  rows_out?: number
  snapshot: string
  asked_by: string
  created_at: string
  attempts: { sql: string; ok: boolean; error?: string }[]
}

export type ScenarioFilters = { quality_pass_only: boolean; exclude_vendors: string[]; freight_inclusive: boolean }

export type AwardComputed = {
  filters: ScenarioFilters
  single_vendor: string | null
  rules_applied: string[]
  allocations: {
    vendor_id: string
    vendor: string
    quality: string | null
    lines: string[]
    line_count: number
    extended_inr: number
    share_pct: number
    freight: Freight
  }[]
  line_allocations: { line_id: string; vendor_id: string; vendor: string; inr_per_1000: number; extended_inr: number }[]
  total_inr: number
  goods_total_inr: number
  freight_inr: number
  freight_unpriced_vendors: string[]
  lines_allocated: number
  vendors_awarded: number
  unallocated: { line_id: string; description: string; reason: string }[]
  single_vendor_options: { vendor_id: string; vendor: string; covers_all: boolean; lines_covered: number; extended_inr: number }[]
  best_single_vendor: { vendor_id: string; vendor: string; extended_inr: number } | null
  vs_best_single_inr: number | null
  vs_best_single_pct: number | null
  last_year: { lines_compared: number; last_year_inr: number; this_year_inr: number; delta_inr: number; delta_pct: number | null }
  unconstrained_total_inr: number
  rule_cost_inr: number
  rule_cost_pct: number | null
  rule_cost_text: string | null
  exclusions: { vendor_id: string; vendor: string; rule: string; reason: string; would_have_won?: string[] }[]
  open_items: { id: string; vendor: string; title: string; status: string; lines: string[] }[]
  cells_in_review: string[]
  approval_blocked: boolean
  summary: string
}

export type Scenario = {
  id: string
  name: string
  created_by: string
  created_at: string
  filters: ScenarioFilters
  single_vendor: string | null
  question: string | null
  query_text: string | null
  saved_total_inr: number | null
  computed: AwardComputed
}

export type Preset = { key: string; name: string; filters: ScenarioFilters; single_vendor: string | null; computed: AwardComputed }

export type AwardView = {
  award: { id: string; status: string; approvals: { actor: string; decision: string; note: string | null; at: string }[]; scenario_id: string } | null
  scenario?: Scenario
  computed?: AwardComputed
  audit: AuditEvent[]
}

export type ReplyFile = {
  name: string
  format: string
  kind: string
  pages: number | null
  parent: string | null
  needs_vision: boolean
  summary: string | null
  sections: { locator: string; contains: string }[]
  parsed_text: string | null
  url: string
}

export type Condition = { kind: string; text: string; applies_to: string | null; percent: number | null; amount: number | null; source_ref: SourceRef; model: string }

export type Reply = {
  vendor_id: string
  name: string
  email: string
  received_at: string | null
  files: ReplyFile[]
  extraction: { file: string; role: string; model: string | null; status: string; error: string | null; agreement: number | null; rows: number; conditions: Condition[] }[]
  lead_role: string | null
}

export type QualityAnswer = {
  question_id: string
  mandatory: boolean
  question: string
  status: string
  effective_status: string
  answer: string | null
  evidence: string | null
  file: string | null
  locator: string | null
  reasoning: string
  evidence_verified: boolean | null
  override: { status: string; reason: string; actor: string } | null
}

export type VendorQuality = { vendor_id: string; name: string; result: 'Pass' | 'Partial' | 'Fail' | null; model: string | null; error: string | null; answers: QualityAnswer[] }

export type RfxLine = {
  line_id: string
  description: string
  spec: { ply: number | null; gsm: number | null; dims_mm: number[] | null; print: string | null; board_weight_kg_per_pc: number | null }
  qty: number
  uom: string
  last_year_price_inr: number | null
}

export type Rfx = {
  id: string
  title: string
  category: string
  base_unit: string
  currency: string
  fx_policy: { source: string; rate: number; foreign_currency: string; as_of: string }
  freight_policy: string
  tax_policy: string
  terms: { payment: string | null; delivery: string | null; validity_days: number | null; assumptions: string[] }
  questionnaire: { question_id: string; text: string; mandatory: boolean }[]
  line_items: RfxLine[]
}

export type RfxView = { rfx: Rfx; status: string; vendors: { vendor_id: string; name: string; contact: string; email: string; city: string }[] }

export type OutboxItem = { id: number; vendor_id: string | null; kind: string; to: string; subject: string; body: string; path: string; status: string; created_at: string }

export type DraftLine = { description: string; ply: number | null; gsm: number | null; dims_mm: number[]; print: string | null; qty: number | null; uom: string; last_year_price_inr: number | null }
export type RfxDraft = {
  title: string
  category: string
  line_items: DraftLine[]
  questionnaire: { text: string; mandatory: boolean }[]
  terms: { payment: string | null; delivery: string | null; validity_days: number | null }
  assumptions: string[]
  missing: string[]
}
