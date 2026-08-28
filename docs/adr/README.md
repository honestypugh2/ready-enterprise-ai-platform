# Architecture Decision Records

Each record states a decision that was genuinely contested, what it cost, and
what would make it wrong. An ADR that only lists advantages is a press release.

Format: **Context → Decision → Consequences → What would change this.**

| # | Decision | Status |
|---|---|---|
| [0001](0001-new-repository-rather-than-extending-an-existing-one.md) | A new integration repository rather than extending an existing accelerator | Accepted |
| [0002](0002-explicit-workflow-rather-than-agent-first.md) | An explicit workflow, with agency added only where it earns its cost | Accepted |
| [0003](0003-specialized-model-rather-than-frontier-model-for-detection.md) | A specialized model for detection, not a frontier model | Accepted |
| [0004](0004-local-mock-mode-is-the-enforced-default.md) | Local mock mode is the enforced default | Accepted |
| [0005](0005-azure-ml-adapter-speaks-the-scoring-contract.md) | The AML adapter speaks the HTTPS scoring contract, not the SDK | Accepted |
| [0006](0006-foundry-adapter-for-reasoning.md) | Foundry for reasoning, behind a narrow protocol | Accepted |
| [0007](0007-routing-is-a-versioned-policy-not-a-heuristic.md) | Routing is a versioned policy, not a heuristic | Accepted |
| [0008](0008-hybrid-retrieval-with-entitlements-applied-before-scoring.md) | Entitlements are applied before scoring, not after ranking | Accepted |
| [0009](0009-business-rules-are-deterministic-and-outside-the-model.md) | Business rules are deterministic and outside the model | Accepted |
| [0010](0010-human-approval-is-a-separate-request.md) | Human approval happens in a separate request from the write | Accepted |
| [0011](0011-a-single-scoped-writer.md) | Exactly one component may mutate a system of record | Accepted |
| [0012](0012-apim-as-the-ai-gateway.md) | API Management is the AI Gateway | Accepted |
| [0013](0013-opentelemetry-with-redaction-in-the-formatter.md) | OpenTelemetry, with redaction in the formatter | Accepted |
| [0014](0014-evaluation-gates-block-a-release.md) | Evaluation gates block a release | Accepted |
| [0015](0015-bicep-first-infrastructure.md) | Bicep first, Terraform not at parity | Accepted |
| [0016](0016-cost-per-completed-task.md) | Cost per completed task, and no invented prices | Accepted |
| [0017](0017-preview-features-are-isolated-behind-adapters.md) | Preview features are isolated behind adapters | Accepted |
| [0018](0018-monorepo-package-layout.md) | Packages install as top-level modules | Accepted |
| [0019](0019-ready-ai-is-an-original-field-framework.md) | READY AI is an original field framework, not a Microsoft standard | Accepted |
