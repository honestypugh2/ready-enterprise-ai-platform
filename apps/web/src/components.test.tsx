import { describe, expect, it } from "vitest";
import type { Inspection } from "./api";
import { presenterStages } from "./presenter";

function emptyInspection(): Inspection {
  return {
    correlation_id: "corr_test",
    status: "halted",
    halted_reason: null,
    mode: "local_mock",
    detection: null,
    route: null,
    evidence: null,
    recommendation: null,
    policy: null,
    approval: null,
    action: null,
    audit: null,
    cost: null,
    step_latencies_ms: {},
  };
}

describe("presenterStages", () => {
  it("does not invent approval or action stages when policy stopped the transaction", () => {
    const inspection = emptyInspection();
    inspection.policy = {} as NonNullable<Inspection["policy"]>;
    inspection.audit = {} as NonNullable<Inspection["audit"]>;

    expect(presenterStages(inspection).map((stage) => stage.key)).toEqual([
      "policy",
      "audit",
    ]);
  });

  it("places exact approval before the scoped writer and final audit", () => {
    const inspection = emptyInspection();
    inspection.approval = {} as NonNullable<Inspection["approval"]>;
    inspection.action = {} as NonNullable<Inspection["action"]>;
    inspection.audit = {} as NonNullable<Inspection["audit"]>;

    expect(presenterStages(inspection).map((stage) => stage.key)).toEqual([
      "approval",
      "action",
      "audit",
    ]);
  });
});