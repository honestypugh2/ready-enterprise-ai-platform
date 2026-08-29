# Documentation

Organised by what you are trying to do.

## Start here

| If you want to | Read |
|---|---|
| Understand the architecture | [architecture/overview.md](architecture/overview.md) |
| Know what is real and what is mocked | [IMPLEMENTATION_STATUS.md](../IMPLEMENTATION_STATUS.md) |
| Run the demo | [demo/runbook.md](demo/runbook.md) |
| Review it as a security engineer | [security/threat-model.md](security/threat-model.md) |
| Understand why a decision was made | [adr/README.md](adr/README.md) |

## Architecture

| Document | Covers |
|---|---|
| [overview.md](architecture/overview.md) | The nine planes, trust boundaries, where each claim is enforced |
| [reuse-and-attribution.md](architecture/reuse-and-attribution.md) | Provenance of reused patterns |
| [model-cards/mock-detector.md](architecture/model-cards/mock-detector.md) | What the mock detector is, and is not |
| [adr/](adr/README.md) | Nineteen decision records, each with its trade-off |

## Security

| Document | Covers |
|---|---|
| [threat-model.md](security/threat-model.md) | STRIDE + OWASP LLM Top 10, with unmitigated risks named |
| [authorization-model.md](security/authorization-model.md) | Entitlements, approvals, write-time re-verification |
| [../SECURITY.md](../SECURITY.md) | Reporting, scope, what is deliberately absent |

## Evaluation and operations

| Document | Covers |
|---|---|
| [evaluations/framework.md](evaluations/framework.md) | Datasets, graders, thresholds, release gates |
| [operations/execution-modes.md](operations/execution-modes.md) | local_mock, azure_dev, production |
| [operations/preview-register.md](operations/preview-register.md) | Every preview, prerelease and pinned dependency, in one place |
| [operations/production-readiness.md](operations/production-readiness.md) | READY AI, rollout stages, operational gaps |
| [../infra/README.md](../infra/README.md) | Bicep layout, decisions, preview prerequisites |

## Delivery

| Document | Covers |
|---|---|
| [demo/runbook.md](demo/runbook.md) | Running the demo, including with no network |
| [presentation-mapping/README.md](presentation-mapping/README.md) | Every message → component → test → demo step |
| [field-positioning/README.md](field-positioning/README.md) | Which conversations this supports, and where it does not apply |

## Reading order for a first review

1. [IMPLEMENTATION_STATUS.md](../IMPLEMENTATION_STATUS.md) — what is actually real
2. [architecture/overview.md](architecture/overview.md) — the shape
3. [adr/0011](adr/0011-a-single-scoped-writer.md) — the strongest claim and how it is enforced
4. `tests/contract/` — the enforcement itself
5. [security/threat-model.md](security/threat-model.md) — what is still open

Starting with the status document is deliberate. Every other document is more
useful once you know which parts of it describe running code.
