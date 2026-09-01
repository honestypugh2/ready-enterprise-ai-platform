import type {
  ActionView,
  ApprovalView,
  AuditView,
  CostView,
  DetectionView,
  EvidenceView,
  Inspection,
  PolicyView,
  RecommendationView,
  RouteView,
} from "./api";
import { presenterStages, type PresenterStageKey } from "./presenter";

export function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="row">
      <span className="k">{k}</span>
      <span className="v">{v}</span>
    </div>
  );
}

export function Detection({ d }: { d: DetectionView }) {
  return (
    <section className="panel">
      <h2>Detection — fixture signal</h2>
      <Row k="label" v={<strong>{d.label}</strong>} />
      <Row k="confidence" v={`${(d.confidence * 100).toFixed(1)}%`} />
      <Row k="decision threshold" v={`${(d.threshold * 100).toFixed(1)}%`} />
      <Row
        k="cleared threshold"
        v={
          <span className={`tag ${d.above_threshold ? "ok" : "warn"}`}>
            {d.above_threshold ? "yes" : "no"}
          </span>
        }
      />
      <Row k="model" v={`${d.model_name} ${d.model_version}`} />
      <Row k="ran at" v={d.execution_location} />
      <Row k="latency" v={`${d.latency_ms.toFixed(1)} ms`} />
      <p className="muted">
        A confidence is a signal, not a verdict. The disposition is decided
        below, by policy.
      </p>
    </section>
  );
}

export function Route({ r }: { r: RouteView }) {
  return (
    <section className="panel">
      <h2>Route — why this component answered</h2>
      <Row k="selected" v={<strong>{r.selected_route}</strong>} />
      <Row k="kind" v={r.selected_kind} />
      <Row k="cost category" v={r.cost_category} />
      <Row k="latency target" v={`${r.latency_target_ms} ms`} />
      <Row k="policy version" v={<code>{r.policy_version}</code>} />
      <div style={{ marginTop: "0.5rem" }}>
        {r.reason_codes.map((c) => (
          <span key={c} className="tag">
            {c}
          </span>
        ))}
      </div>
      {r.excluded.length > 0 && (
        <>
          <p className="muted" style={{ marginBottom: "0.25rem" }}>
            Rejected candidates — the interesting half of the log:
          </p>
          {r.excluded.map((e) => (
            <div key={e.route_id ?? e.reason_code} className="muted">
              <code>{e.route_id}</code> — {e.reason_code}
              {e.detail ? ` (${e.detail})` : ""}
            </div>
          ))}
        </>
      )}
    </section>
  );
}

export function Evidence({ e }: { e: EvidenceView }) {
  return (
    <section className="panel">
      <h2>Evidence — governed retrieval</h2>
      <Row k="strategy" v={e.strategy} />
      <Row k="index" v={`${e.index_name} · ${e.index_version}`} />
      <Row
        k="trimmed by entitlement"
        v={
          <span className={e.trimmed_count > 0 ? "tag warn" : "tag"}>
            {e.trimmed_count}
          </span>
        }
      />
      {e.partial && (
        <Row k="partial" v={<span className="tag stop">degraded</span>} />
      )}
      {e.failures.map((f) => (
        <div key={f} className="muted">
          {f}
        </div>
      ))}
      {e.items.map((item) => (
        <div key={item.citation_ref} className="evidence-item">
          <div>
            <code>[{item.citation_ref}]</code> {item.source_title}
          </div>
          <div className="muted">
            <span className={`tag ${item.authority === "authoritative" ? "ok" : ""}`}>
              {item.authority}
            </span>
            <span className="tag">{item.classification}</span>
            {item.is_stale && <span className="tag stop">stale</span>}
            score {item.score.toFixed(3)} · v{item.version}
          </div>
        </div>
      ))}
      <p className="muted">
        Passage text is not returned on the wire. Citations reference the
        evidence store, where access is controlled.
      </p>
    </section>
  );
}

export function Recommendation({ r }: { r: RecommendationView }) {
  return (
    <section className="panel">
      <h2>Explanation — grounded, and not a decision</h2>
      {r.refused ? (
        <p>
          <span className="tag stop">refused</span> {r.refusal_reason}
        </p>
      ) : (
        <>
          <p style={{ marginTop: 0 }}>
            <strong>{r.headline}</strong>
          </p>
          <p className="muted">{r.rationale}</p>
        </>
      )}
      <Row k="model" v={r.model_name} />
      <Row k="prompt" v={`${r.prompt_id} ${r.prompt_version}`} />
      <Row
        k="citation precision"
        v={
          r.citation_precision === null
            ? "—"
            : r.citation_precision.toFixed(2)
        }
      />
      <div style={{ marginTop: "0.5rem" }}>
        {r.citations.map((c, index) => (
          <span key={`${c}-${index}`} className="tag">
            [{c}]
          </span>
        ))}
      </div>
      {r.missing_information.length > 0 && (
        <p className="muted">
          Missing information: {r.missing_information.join("; ")}
        </p>
      )}
    </section>
  );
}

export function Policy({ p }: { p: PolicyView }) {
  return (
    <section className="panel">
      <h2>Policy — the verdict, decided outside the model</h2>
      <Row k="disposition" v={<strong>{p.disposition}</strong>} />
      <Row k="severity" v={p.severity} />
      <Row
        k="approval required"
        v={
          <span className={`tag ${p.approval_required ? "warn" : "ok"}`}>
            {p.approval_required ? p.approver_role : "no"}
          </span>
        }
      />
      {p.dual_control_required && (
        <Row k="dual control" v={<span className="tag stop">two approvers</span>} />
      )}
      <Row k="policy version" v={<code>{p.policy_version}</code>} />
      <Row k="policy sha" v={<code>{p.policy_sha.slice(0, 22)}…</code>} />
      <div style={{ marginTop: "0.5rem" }}>
        {p.matched_rules.map((r) => (
          <span key={r} className="tag ok">
            {r}
          </span>
        ))}
        {p.reason_codes.map((r) => (
          <span key={r} className="tag">
            {r}
          </span>
        ))}
      </div>
      <p className="muted">
        Deterministic, versioned and hash-identified. The same input and the
        same policy version always produce the same verdict.
      </p>
    </section>
  );
}

export function Approval({
  a,
  onDecide,
  busy,
}: {
  a: ApprovalView;
  onDecide: (principal: string, decision: string) => void;
  busy: boolean;
}) {
  const decided = a.decisions.length;
  return (
    <section className="panel">
      <h2>Approval — a named human, on this exact proposal</h2>
      <Row
        k="state"
        v={
          <span
            className={`tag ${a.state === "approved" ? "ok" : a.state === "pending" ? "warn" : "stop"}`}
          >
            {a.state}
          </span>
        }
      />
      <Row k="required role" v={a.required_role} />
      <Row k="expires" v={new Date(a.expires_at).toLocaleString()} />
      <Row k="fingerprint" v={<code>{a.proposal_fingerprint.slice(0, 22)}…</code>} />
      <Row k="decisions recorded" v={decided} />
      <p className="muted" style={{ marginBottom: 0 }}>
        {a.proposed_action_summary}
      </p>
      {a.state === "pending" && (
        <div className="approval-actions">
          <button
            className="primary"
            disabled={busy}
            onClick={() => onDecide(`synthetic-approver-${decided + 1}`, "approved")}
          >
            Approve as approver {decided + 1}
          </button>
          <button
            disabled={busy}
            onClick={() => onDecide(`synthetic-approver-${decided + 1}`, "rejected")}
          >
            Reject
          </button>
        </div>
      )}
      {a.dual_control_required && decided < 2 && (
        <p className="muted">
          Dual control: two distinct principals are required. One person
          deciding twice does not satisfy it.
        </p>
      )}
    </section>
  );
}

export function Action({ a }: { a: ActionView }) {
  const dryRun = a.status === "dry_run";
  return (
    <section className="panel">
      <h2>Action — the only component that may write</h2>
      <Row
        k="status"
        v={
          <span className={`tag ${dryRun ? "warn" : a.status === "succeeded" ? "ok" : "stop"}`}>
            {a.status}
          </span>
        }
      />
      <Row k="target system" v={a.target_system} />
      <Row k="reference" v={<code>{a.external_reference ?? "—"}</code>} />
      <Row k="attempts" v={a.attempts} />
      {a.error_code && <Row k="error" v={a.error_code} />}
      {dryRun && (
        <p className="muted">
          Dry run: a receipt exists, no record was created. Connector execution
          remains disabled for this demonstration.
        </p>
      )}
    </section>
  );
}

export function Audit({ a }: { a: AuditView }) {
  return (
    <section className="panel full">
      <h2>Audit — a chain, not a log</h2>
      <Row
        k="chain verified"
        v={
          <span className={`tag ${a.chain_verified ? "ok" : "stop"}`}>
            {a.chain_verified ? "verified" : "BROKEN"}
          </span>
        }
      />
      <Row k="outcome" v={a.outcome} />
      <Row k="chain head" v={<code>{a.chain_head.slice(0, 26)}…</code>} />
      {a.steps.map((s) => (
        <div key={s.sequence} className="audit-step">
          <code>{String(s.sequence).padStart(2, "0")}</code> {s.step_name}
          <span className="muted">
            {" "}
            · {s.component} → {s.outcome}
          </span>
        </div>
      ))}
    </section>
  );
}

export function Latency({ steps }: { steps: Record<string, number> }) {
  const entries = Object.entries(steps);
  const max = Math.max(...entries.map(([, ms]) => ms), 1);
  return (
    <section className="panel">
      <h2>Latency by stage</h2>
      {entries.map(([name, ms]) => (
        <div key={name}>
          <div className="row">
            <span className="k">{name}</span>
            <span className="v">{ms.toFixed(1)} ms</span>
          </div>
          <div className="bar" style={{ width: `${(ms / max) * 100}%` }} />
        </div>
      ))}
    </section>
  );
}

export function Cost({ c }: { c: CostView }) {
  return (
    <section className="panel">
      <h2>Cost — units are facts, prices are yours</h2>
      {Object.entries(c.units_by_surface).map(([surface, units]) => (
        <Row key={surface} k={surface} v={`${units} · ${c.category_by_surface[surface]}`} />
      ))}
      <Row k="tokens in / out" v={`${c.total_input_tokens} / ${c.total_output_tokens}`} />
      <Row k="frontier calls avoided" v={c.frontier_calls_avoided} />
      <Row k="basis" v={c.basis} />
      <p className="muted">
        {c.estimated_total === null
          ? "No rate card supplied, so no currency figure is claimed."
          : `Estimated ${c.estimated_total} ${c.currency}`}
      </p>
    </section>
  );
}

export function Transaction({
  inspection,
  onDecide,
  busy,
  visibleCount = Number.POSITIVE_INFINITY,
}: {
  inspection: Inspection;
  onDecide: (principal: string, decision: string) => void;
  busy: boolean;
  visibleCount?: number;
}) {
  const stages = presenterStages(inspection);
  return (
    <div className="stage-stack">
      {stages.slice(0, visibleCount).map((stage, index, visibleStages) => (
        <div
          className={`stage-reveal ${index === visibleStages.length - 1 ? "stage-current" : "stage-complete"}`}
          key={stage.key}
        >
          <span className="stage-number">{String(index + 1).padStart(2, "0")}</span>
          {index === visibleStages.length - 1 ? (
            stageContent(stage.key, inspection, onDecide, busy)
          ) : (
            <div className="stage-summary">
              <strong>{stage.title}</strong>
              <span>verified</span>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function stageContent(
  key: PresenterStageKey,
  inspection: Inspection,
  onDecide: (principal: string, decision: string) => void,
  busy: boolean,
): React.ReactNode {
  if (key === "detection" && inspection.detection) return <Detection d={inspection.detection} />;
  if (key === "evidence" && inspection.evidence) return <Evidence e={inspection.evidence} />;
  if (key === "route" && inspection.route) return <Route r={inspection.route} />;
  if (key === "recommendation" && inspection.recommendation) {
    return <Recommendation r={inspection.recommendation} />;
  }
  if (key === "policy" && inspection.policy) return <Policy p={inspection.policy} />;
  if (key === "approval" && inspection.approval) {
    return <Approval a={inspection.approval} onDecide={onDecide} busy={busy} />;
  }
  if (key === "action" && inspection.action) return <Action a={inspection.action} />;
  if (key === "audit" && inspection.audit) return <Audit a={inspection.audit} />;
  return null;
}
