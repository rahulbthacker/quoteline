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

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`/api${path}`)
  if (!response.ok) throw new Error(`${path} returned ${response.status}`)
  return response.json() as Promise<T>
}

export const api = {
  traces: () => get<Trace[]>('/traces'),
}
