/**
 * Wire types and the API client.
 *
 * These mirror `apps/api/schemas.py`, which is deliberately separate from the
 * platform's internal contracts. If the API changes shape, this file is where
 * it should fail to compile.
 */

const BASE = import.meta.env["VITE_API_BASE_URL"] ?? "";

export interface DetectionView {
  prediction_id: string;
  label: string;
  confidence: number;
  threshold: number;
  above_threshold: boolean;
  model_name: string;
  model_version: string;
  execution_location: string;
  latency_ms: number;
  input_hash: string;
}

export interface RouteExclusionView {
  route_id: string | null;
  reason_code: string | null;
  detail: string | null;
}

export interface RouteView {
  selected_route: string;
  selected_kind: string;
  reason_codes: string[];
  excluded: RouteExclusionView[];
  policy_version: string;
  cost_category: string;
  latency_target_ms: number;
  is_fallback: boolean;
}

export interface EvidenceItemView {
  citation_ref: string;
  source_id: string;
  source_title: string;
  source_uri: string;
  authority: string;
  classification: string;
  version: string;
  updated_at: string;
  score: number;
  is_stale: boolean;
}

export interface EvidenceView {
  strategy: string;
  index_name: string;
  index_version: string;
  items: EvidenceItemView[];
  trimmed_count: number;
  partial: boolean;
  failures: string[];
  latency_ms: number;
}

export interface RecommendationView {
  headline: string;
  rationale: string;
  citations: string[];
  missing_information: string[];
  refused: boolean;
  refusal_reason: string | null;
  model_name: string;
  route_id: string;
  prompt_id: string;
  prompt_version: string;
  citation_precision: number | null;
  latency_ms: number;
}

export interface PolicyView {
  decision_id: string;
  allowed: boolean;
  severity: string;
  disposition: string;
  approval_required: boolean;
  approver_role: string | null;
  dual_control_required: boolean;
  permitted_actions: string[];
  reason_codes: string[];
  matched_rules: string[];
  policy_version: string;
  policy_sha: string;
}

export interface ApprovalView {
  approval_id: string;
  state: string;
  required_role: string;
  dual_control_required: boolean;
  requested_at: string;
  expires_at: string;
  proposal_fingerprint: string;
  proposed_action_summary: string;
  evidence: Record<string, unknown>;
  decisions: Record<string, string>[];
}

export interface ActionView {
  receipt_id: string;
  status: string;
  target_system: string;
  external_reference: string | null;
  attempts: number;
  error_code: string | null;
  latency_ms: number;
}

export interface AuditStepView {
  sequence: number;
  step_name: string;
  component: string;
  outcome: string;
  occurred_at: string;
}

export interface AuditView {
  audit_id: string;
  correlation_id: string;
  outcome: string;
  chain_head: string;
  chain_verified: boolean;
  steps: AuditStepView[];
}

export interface CostView {
  basis: string;
  currency: string;
  units_by_surface: Record<string, number>;
  category_by_surface: Record<string, string>;
  total_input_tokens: number;
  total_output_tokens: number;
  frontier_calls_avoided: number;
  estimated_total: number | null;
  cost_per_completed_task: number | null;
}

export interface Inspection {
  correlation_id: string;
  status: string;
  halted_reason: string | null;
  mode: string;
  detection: DetectionView | null;
  route: RouteView | null;
  evidence: EvidenceView | null;
  recommendation: RecommendationView | null;
  policy: PolicyView | null;
  approval: ApprovalView | null;
  action: ActionView | null;
  audit: AuditView | null;
  cost: CostView | null;
  step_latencies_ms: Record<string, number>;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });

  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail =
      body && typeof body === "object" && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : response.statusText;
    throw new ApiError(detail, response.status);
  }
  return (await response.json()) as T;
}

export function runScenario(scenarioId: string): Promise<Inspection> {
  return request<Inspection>("/v1/inspections/scenario", {
    method: "POST",
    body: JSON.stringify({ scenario_id: scenarioId }),
  });
}

export function decide(
  approvalId: string,
  body: {
    approver_principal_id: string;
    approver_role: string;
    decision: string;
    rationale: string;
  },
): Promise<Inspection> {
  return request<Inspection>(`/v1/approvals/${approvalId}/decision`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function health(): Promise<{ mode: string; status: string }> {
  return request<{ mode: string; status: string }>("/healthz");
}

export function executionBadge(mode: string | null | undefined): string {
  if (mode === undefined) return "CHECKING · configured execution mode";
  if (mode === null) return "UNAVAILABLE · API not connected";
  if (mode === "azure_dev") return "LIVE · Search / Foundry / telemetry";
  return "FALLBACK · local retrieval / reasoning / telemetry";
}

/**
 * Every surface that shows a number must also say where it came from.
 * `local_mock` means the figures are fixtures, not measurements.
 */
export function provenanceLabel(mode: string): string {
  return mode === "local_mock"
    ? "Local mock — fixtures, not measurements"
    : `Azure-connected (${mode}) — measured on this environment`;
}
