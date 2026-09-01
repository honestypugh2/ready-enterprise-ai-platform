import type { Inspection } from "./api";

export type PresenterStageKey =
  | "detection"
  | "evidence"
  | "route"
  | "recommendation"
  | "policy"
  | "approval"
  | "action"
  | "audit";

export interface PresenterStage {
  key: PresenterStageKey;
  title: string;
}

export function presenterStages(inspection: Inspection): PresenterStage[] {
  const stages: PresenterStage[] = [];
  if (inspection.detection) stages.push({ key: "detection", title: "Signal received" });
  if (inspection.evidence) {
    stages.push({ key: "evidence", title: "Entitled evidence retrieved" });
  }
  if (inspection.route) stages.push({ key: "route", title: "Reasoning route selected" });
  if (inspection.recommendation) {
    stages.push({ key: "recommendation", title: "Grounded explanation produced" });
  }
  if (inspection.policy) {
    stages.push({ key: "policy", title: "Deterministic verdict applied" });
  }
  if (inspection.approval) {
    stages.push({ key: "approval", title: "Exact proposal awaiting approval" });
  }
  if (inspection.action) {
    stages.push({ key: "action", title: "Scoped writer returned a receipt" });
  }
  if (inspection.audit) stages.push({ key: "audit", title: "Decision chain verified" });
  return stages;
}