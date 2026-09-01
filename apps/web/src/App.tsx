import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  decide,
  executionBadge,
  health,
  provenanceLabel,
  runScenario,
  type Inspection,
} from "./api";
import { Transaction } from "./components";
import { presenterStages } from "./presenter";

const SCENARIOS = {
  "unsafe-replenishment": {
    label: "01 / Unsafe candidate",
    sku: "SKU-BEARING-041",
    summary: "Discontinued SKU. Policy must stop the transaction.",
  },
  "governed-replenishment": {
    label: "02 / Governed candidate",
    sku: "SKU-BEARING-042",
    summary: "Eligible SKU. Exact approval is required before dry run.",
  },
} as const;

type ScenarioId = keyof typeof SCENARIOS;
type Theme = "light" | "dark";

const THEME_STORAGE_KEY = "reap-theme";

function initialTheme(): Theme {
  const savedTheme = window.localStorage.getItem(THEME_STORAGE_KEY);
  if (savedTheme === "light" || savedTheme === "dark") return savedTheme;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export default function App() {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [mode, setMode] = useState<string | null | undefined>(undefined);
  const [inspection, setInspection] = useState<Inspection | null>(null);
  const [active, setActive] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [revealedStages, setRevealedStages] = useState(0);

  useEffect(() => {
    health()
      .then((h) => setMode(h.mode))
      .catch(() => setMode(null));
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);

  const run = useCallback(async (id: ScenarioId) => {
    setBusy(true);
    setError(null);
    setActive(id);
    setInspection(null);
    setRevealedStages(0);
    try {
      setInspection(await runScenario(id));
      setRevealedStages(1);
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
        const completed = await decide(inspection.approval.approval_id, {
            approver_principal_id: principal,
            approver_role: inspection.approval.required_role,
            decision,
            rationale:
              "Evidence, policy result and downstream effect reviewed in the demo UI.",
          });
        setInspection(completed);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : String(err));
      } finally {
        setBusy(false);
      }
    },
    [inspection],
  );

  const stages = inspection ? presenterStages(inspection) : [];
  const currentStage = stages[Math.min(revealedStages, stages.length) - 1];
  const approvalWaiting =
    currentStage?.key === "approval" && inspection?.approval?.state === "pending";
  const activeScenario = active ? SCENARIOS[active as ScenarioId] : null;
  const badge = executionBadge(mode);

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">Ready Enterprise AI Platform</p>
          <h1>Governed Replenishment Console</h1>
        </div>
        <div className="header-tools">
          <div className="provenance" aria-label="Demonstration provenance">
            <span className={mode === "azure_dev" ? "provenance-live" : ""}>{badge}</span>
            <span>FIXTURE · inventory / detector / identities</span>
            <span className="provenance-dry">ACTION · DRY RUN</span>
          </div>
          <button
            type="button"
            className="theme-toggle"
            aria-label={`Switch to ${theme === "light" ? "dark" : "light"} mode`}
            title={`Switch to ${theme === "light" ? "dark" : "light"} mode`}
            onClick={() => setTheme((current) => (current === "light" ? "dark" : "light"))}
          >
            <span aria-hidden="true">{theme === "light" ? "☾" : "☀"}</span>
          </button>
        </div>
      </header>

      <div className="environment-line">
        <span className={`status-dot ${mode ? "connected" : ""}`} />
        {mode === undefined
          ? "Checking API and configured dependencies..."
          : mode === null
            ? "API unreachable - start the API and web app in separate terminals"
            : provenanceLabel(mode)}
      </div>

      <nav className="scenario-switcher" aria-label="Replenishment scenarios">
        {(Object.entries(SCENARIOS) as [ScenarioId, (typeof SCENARIOS)[ScenarioId]][]).map(
          ([id, scenario]) => (
          <button
            key={id}
            disabled={busy}
            className={active === id ? "scenario-active" : ""}
            onClick={() => void run(id)}
          >
            <strong>{scenario.label}</strong>
            <span>{scenario.summary}</span>
          </button>
          ),
        )}
      </nav>

      {error && (
        <div className="error">
          <strong>{error}</strong>
        </div>
      )}

      {inspection && activeScenario ? (
        <main className="presenter-grid">
          <aside className="decision-rail">
            <p className="eyebrow">Warehouse decision</p>
            <h2>{activeScenario.sku}</h2>
            <p>{activeScenario.summary}</p>
            <dl>
              <div><dt>Warehouse</dt><dd>SEA-01</dd></div>
              <div><dt>Supplier</dt><dd>SUP-1007</dd></div>
              <div><dt>Quantity</dt><dd>120 fixture units</dd></div>
              <div><dt>State</dt><dd>{inspection.status}</dd></div>
            </dl>
            {inspection.policy && revealedStages >= 5 && (
              <div className={`decision-callout ${inspection.policy.allowed ? "permit" : "block"}`}>
                <span>{inspection.policy.allowed ? "APPROVAL REQUIRED" : "BLOCKED"}</span>
                <strong>{inspection.policy.matched_rules.join(", ")}</strong>
                <small>{inspection.policy.reason_codes.join(" · ")}</small>
              </div>
            )}
            <div className="correlation">
              <span>Correlation ID</span>
              <code>{inspection.correlation_id}</code>
            </div>
          </aside>

          <section className="execution-console">
            <div className="console-heading">
              <div>
                <p className="eyebrow">Governed execution</p>
                <h2>{currentStage?.title ?? "Transaction ready"}</h2>
              </div>
              <span>{Math.min(revealedStages, stages.length)} / {stages.length}</span>
            </div>
            <Transaction
              inspection={inspection}
              onDecide={(principal, decision) => void onDecide(principal, decision)}
              busy={busy}
              visibleCount={revealedStages}
            />
            <div className="presenter-controls">
              <p>
                {approvalWaiting
                  ? "A separate decision is required before this transaction can continue."
                  : revealedStages < stages.length
                    ? "Reveal the next verified stage from this transaction."
                    : "Transaction evidence is fully revealed."}
              </p>
              {!approvalWaiting && revealedStages < stages.length && (
                <button
                  className="next-button"
                  onClick={() => setRevealedStages((count) => count + 1)}
                >
                  Next stage <span aria-hidden="true">→</span>
                </button>
              )}
            </div>
          </section>
        </main>
      ) : (
        <div className="empty-state">
          <p className="eyebrow">Presenter mode</p>
          <h2>Choose the unsafe candidate first.</h2>
          <p>The workflow executes once; you control when each verified stage is revealed.</p>
        </div>
      )}
    </div>
  );
}
