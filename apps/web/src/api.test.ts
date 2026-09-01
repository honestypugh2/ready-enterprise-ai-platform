import { describe, expect, it } from "vitest";
import { executionBadge, provenanceLabel } from "./api";

describe("provenanceLabel", () => {
  it("says plainly when figures are fixtures", () => {
    expect(provenanceLabel("local_mock")).toContain("fixtures, not measurements");
  });

  it("names the environment when connected to Azure", () => {
    expect(provenanceLabel("azure_dev")).toContain("azure_dev");
    expect(provenanceLabel("azure_dev")).toContain("measured");
  });
});

describe("executionBadge", () => {
  it("distinguishes loading, live Azure, fallback, and unavailable states", () => {
    expect(executionBadge(undefined)).toContain("CHECKING");
    expect(executionBadge("azure_dev")).toContain("LIVE");
    expect(executionBadge("local_mock")).toContain("FALLBACK");
    expect(executionBadge(null)).toContain("UNAVAILABLE");
  });
});
