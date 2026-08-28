import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  decide,
  health,
  provenanceLabel,
  runScenario,
  type Inspection,
} from "./api";
import { Transaction } from "./components";

/** Mirrors `data/fixtures/demo-scenarios.json`. */
const SCENARIOS = [
  ["clean-unit", "Clean unit"],
  ["cosmetic", "Cosmetic finding"],
  ["low-confidence", "Low-confidence signal"],
  ["major-defect", "Safety-relevant major defect"],
  ["repeat-major", "Repeated major defect in batch"],
  ["critical-defect", "Critical structural defect"],
  ["restricted-classification", "Restricted classification"],
] as const;

export default function App() {
  const [mode, setMode] = useState<string | null>(null);
  const [inspection, setInspection] = useState<Inspection | null>(null);
  const [active, setActive] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    health()
      .then((h) => setMode(h.mode))
      .catch(() => setMode(null));
  }, []);

  const run = useCallback(async (id: string) => {
    setBusy(true);
    setError(null);
    setActive(id);
    try {
      setInspection(await runScenario(id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, []);

  const onDecide = useCallback(
    async (principal: string, decision: string) => {
      if (!inspection?.approval) return;
      setBusy(true);
      setError(null);
      try {
        setInspection(
          await decide(inspection.approval.approval_id, {
            approver_principal_id: principal,
            approver_role: inspection.approval.required_role,
            decision,
            rationale:
              "Evidence, policy result and downstream effect reviewed in the demo UI.",
          }),
        );
      } catch (err) {
        setError(err instanceof ApiError ? err.message : String(err));
      } finally {
        setBusy(false);
      }
    },
    [inspection],
  );

  return (
    <div className="app">
      <header>
        <h1>Ready Enterprise AI Platform</h1>
        <p>
          One governed transaction, end to end. The model produces a signal;
          policy decides; a named human approves; one component writes; the
          chain proves what happened.
        </p>
      </header>

      <div className="mode-banner">
        <strong>Mode:</strong>{" "}
        {mode === null
          ? "API unreachable — start it with `make dev`"
          : provenanceLabel(mode)}
      </div>

      <div className="scenarios">
        {SCENARIOS.map(([id, label]) => (
          <button
            key={id}
            disabled={busy}
            className={active === id ? "primary" : ""}
            onClick={() => void run(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {error && (
        <div className="error">
          <strong>{error}</strong>
        </div>
      )}

      {inspection ? (
        <>
          <div className="mode-banner">
            <strong>{inspection.status}</strong>
            {inspection.halted_reason ? ` — ${inspection.halted_reason}` : ""}
            <span className="muted"> · {inspection.correlation_id}</span>
          </div>
          <Transaction
            inspection={inspection}
            onDecide={(p, d) => void onDecide(p, d)}
            busy={busy}
          />
        </>
      ) : (
        <p className="muted">Pick a scenario to run a governed transaction.</p>
      )}
    </div>
  );
}
