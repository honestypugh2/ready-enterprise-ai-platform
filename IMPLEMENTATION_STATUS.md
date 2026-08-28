# Implementation Status

This document exists because a reference architecture that does not say what is
real is a marketing artifact. Every capability the README, the presentation or
the code comments claim is listed here with the same four facts: **what state it
is in, what was actually validated, what the remaining gap is, and what that gap
means if you deployed this.**

Nothing in this repository has been deployed to Azure. No benchmark, latency,
accuracy, cost or customer-outcome figure appears anywhere in it. Where a number
is shown, it is a count of something the test suite measured on this machine.

- **Last verified:** 2026-08-28
- **Verified by:** `make check` (lint, mypy strict, 273 tests), `make eval`, `make secrets`, `reap demo run`
- **Execution mode when verified:** `local_mock` — no Azure subscription, credential or network access

## Status vocabulary

| Status | Meaning |
|---|---|
| **Complete** | Implemented, tested, and does in production what it does here |
| **Partial** | Implemented for the demonstrated path; named gaps remain |
| **Mocked** | Deliberately synthetic. The *architecture around it* is real; the component is not |
| **Adapter only** | Real client code against a real service contract, never executed against the live service |
| **Planned** | Designed and referenced, not written |
| **Not implemented** | Named in the presentation; no code exists |

---

## 1. Verification actually performed

| Check | Command | Result |
|---|---|---|
| Lint + format | `make lint` | Clean, 119 files |
| Static types | `make typecheck` | mypy `--strict`, clean, 100 source files |
| Unit | `pytest tests/unit` | 93 passed |
| Contract | `pytest tests/contract` | 31 passed |
| Security | `pytest tests/security` | 69 passed |
| Integration (offline) | `pytest tests/integration` | 60 passed |
| Resilience | `pytest tests/resilience` | 20 passed |
| Evaluation gate | `make eval` | PASS, 16 cases, 7 blocking graders |
| Secret scan | `make secrets` | Clean, 128 tracked files, 6 reviewed exceptions |
| Demo | `reap demo run --scenario <all 7>` | All 7 scenarios complete, audit chains verify |
| Dependency audit | `pip-audit --skip-editable --strict` | No known vulnerabilities |
| Frontend | `npm run lint && typecheck && test && build` | Clean, 2 tests, builds; `npm audit` reports 0 vulnerabilities |
| Bicep | `make infra-lint` | 13 templates + 3 parameter files compile clean |
| Compose | `docker compose config` | Valid, 3 services |

**What was never run:** anything against Azure. No Bicep has been deployed, no
AML endpoint scored, no Foundry model called, no Azure AI Search index queried,
no Service Bus message published, no App Insights trace exported.

---

## 2. Platform planes

### Contracts — **Complete**

- **Validated:** Every model frozen and `extra="forbid"`; `tests/contract/test_plane_boundaries.py` reads the import graph and fails if any plane reaches past its boundary; `contracts` itself is proven to depend on nothing.
- **Gap:** `CONTRACT_VERSION` is declared but there is no compatibility test between versions, because there is only one version.
- **Production implication:** None today. The moment a second version exists, a consumer can break silently.
- **Next action:** Add a schema-snapshot test before the first contract change.

### Configuration and execution modes — **Complete**

- **Validated:** `local_mock` cannot select a cloud provider or disable `dry_run` — the settings validator raises, and `tests/unit` covers it. `production` mode refuses to start without App Insights, Search and reasoning endpoints.
- **Gap:** `azure_dev` and `production` modes have never been instantiated against real endpoints.
- **Production implication:** The validator's *shape* is proven; its interaction with real credential resolution is not.
- **Next action:** Exercise both modes in the first deployed environment.

### Detector (specialized model) — **Mocked / adapter only**

| Implementation | Status |
|---|---|
| `DeterministicMockDetector` | **Complete** — default, hash-seeded, reproducible |
| `OnnxDetector` | **Adapter only** — reads a local ONNX graph; never run with real weights |
| `AzureMLEndpointDetector` | **Adapter only** — written against the AML scoring contract; never called |

- **Validated:** All three satisfy one protocol; swapping is one configuration value. Mock detector is deterministic across machines. Failure injection produces a halt, not an answer.
- **Gap:** **There is no trained model in this repository and no accuracy claim of any kind.** The mock is a fixture that derives a defect distribution from a SHA-256 hash.
- **Production implication:** The governance architecture is demonstrable; the detection quality is entirely unproven and must be established by the customer against their own data.
- **Next action:** See `docs/architecture/model-cards/mock-detector.md` (**Planned**).

### Predictive models (forecasting) — **Partial**

- **Validated:** `ForecastPoint` will not validate without an interval containing its own value. `Forecast.adds_information` is False for any model that has not beaten seasonal-naive *and* for any model never measured. MAPE raises rather than returning a comfortable number on an all-zero actual series.
- **Gap:** `AzureMLForecaster` is **adapter only**. No forecast is consumed by the workflow — the plane is complete and tested in isolation but not yet wired into a decision path.
- **Production implication:** Nothing depends on it, so nothing breaks. It is currently a demonstrated capability rather than a used one.
- **Next action:** Wire station defect-rate forecasting into the policy input as an advisory signal, or state plainly that it is illustrative.

### Retrieval — **Partial**

| Implementation | Status |
|---|---|
| `LocalKnowledgeRetriever` | **Complete** for the local corpus |
| `AzureSearchRetriever` | **Adapter only** |
| `AgenticRetriever` | **Partial** — query decomposition implemented, never run against a live index |

- **Validated:** Entitlements and classification are applied **before** scoring, proven by a test that asks for `top_k=1` and requires one real result. Empty entitlements return nothing. Two identities get different answers from one corpus.
- **Gap:** The local "vector" component is a **deterministic lexical embedding (hashed character trigrams), not a semantic embedding model.** It exists to exercise the hybrid merge path offline. Relevance quality is not representative.
- **Production implication:** The *governance* of retrieval transfers directly. The *retrieval quality* does not and must be re-measured with real embeddings.
- **Next action:** Run the evaluation suite against a provisioned Azure AI Search index and compare graders.

### Reasoning — **Mocked / adapter only**

| Implementation | Status |
|---|---|
| `MockReasoner` | **Complete** — a template engine, not a model |
| `FoundryReasoner` | **Adapter only** |

- **Validated:** `Recommendation` cannot carry a verdict — there is no field for one, and a contract test asserts it. Non-refusing output must cite at least one retrieved passage. The reasoning plane cannot import `connectors`, `approvals` or `policy_engine`, enforced by the import-graph test.
- **Gap:** The mock composes explanations from templates. **It is not a language model and no output-quality claim is made.** The Foundry adapter has never called a deployment.
- **Production implication:** Substituting a real model changes wording and cost, not authority. That is the point — but it is untested against a real model's failure modes (verbosity, refusal drift, citation fabrication).
- **Next action:** Run the citation graders against a live Foundry deployment before quoting any citation-precision figure.

### Model routing — **Complete (offline)**

- **Validated:** Versioned, hash-identified routing policy; every decision records the selected route, the reason codes, and the *excluded* candidates with reasons.
- **Gap:** Route health probing is stubbed. Cost and latency attributes in `routing.yaml` are **declared, not measured.**
- **Production implication:** The routing *decision* is auditable; the inputs it routes on are placeholders until measured in a real environment.
- **Next action:** Replace declared `typical_latency_ms` with values from the evaluation harness, or mark the field advisory.

### Policy engine — **Complete**

- **Validated:** 8 rules, 3 guards, first-match-wins, ascending-id order enforced by a test (this caught a dead rule: `R045` was unreachable below `R040` and was renumbered to `R035`). Every decision names its policy version and file hash. Guards can only narrow. Denied outcomes cannot permit actions.
- **Gap:** Policy is loaded from a file on disk. There is no signing, no approval workflow for policy changes, and no policy-change audit trail.
- **Production implication:** **Whoever can write the policy file can change what the platform is allowed to do.** In production this file needs the same change control as code, plus signing.
- **Next action:** Source policy from a signed artifact; record policy version changes as audit events.

### Approvals — **Complete**

- **Validated:** Separation of duties (requester ≠ approver), role match, expiry, revocation, and dual control requiring **two distinct principals** — a test asserts that one person deciding twice does not satisfy it. The approval surface carries evidence, a fingerprint and an expiry, not just a sentence.
- **Gap:** `InMemoryApprovalStore` is the default; `JsonFileApprovalStore` is the persistent option. Neither is a durable, replicated store.
- **Production implication:** An approval does not survive a replica restart. This is the single most important storage gap.
- **Next action:** Back approvals with Cosmos DB or Azure SQL before any pilot.

### Connectors and the scoped writer — **Complete (against mocks)**

- **Validated:** Six refusals precede any write — policy allowed, action in permitted set, approval verified against the proposal fingerprint, connector supports the kind, idempotency check, dry-run gate. `tests/contract/test_sole_writer.py` reads the import graph and fails the build if any module outside `connectors.writer` acquires a path to a connector, and uses `inspect.getsource` to prove `verify_for_write` appears before `_attempt_write`.
- **Gap:** All three connectors (`mock_erp`, `mock_servicenow`, `mock_dynamics365`) are **in-memory**. No real ERP, ServiceNow or Dynamics 365 call has ever been made.
- **Production implication:** The authorization chain transfers. The integration itself — auth, throttling, schema drift, partial failure semantics — is entirely unbuilt.
- **Next action:** Implement one real connector behind the same protocol and re-run `tests/resilience` against it.

### Audit — **Complete**

- **Validated:** Hash-chained steps with a genesis hash; `verify_chain()` is checked after every scenario; a receipt is sealed for failed and halted transactions as well as successful ones; attributes are redacted **on the way in**, so the receipt never holds a prompt or payload value. The proposal and the write share one chain via `AuditTrailBuilder.resume`.
- **Gap:** `JsonFileAuditStore` is write-once by convention, not by storage policy. `infra/modules/storage.bicep` provisions the audit container with an immutability policy, but that template has never been deployed, so the enforced version does not yet exist anywhere.
- **Production implication:** In the local demo an audit record can be deleted by anyone who can delete a file, and an audit record that can be quietly deleted is not evidence.
- **Next action:** Deploy the storage module and point `REAP_STATE_DIR` at the immutable container.

### Observability — **Partial**

- **Validated:** One root span per transaction with every step as a child. Span attributes and log fields are redacted by key and by value pattern in the formatter, so no call site can bypass it. A `LoggerAdapter` bug that silently dropped caller-supplied fields was found and fixed.
- **Gap:** The Azure Monitor exporter is **adapter only** — configured but never exported a span. Metrics are in-process counters, not emitted. The six KQL queries in `infra/monitor/queries/` are written against the schema the platform emits and **have never been run against a real workspace**.
- **Production implication:** Traces are correct in structure and unproven in transit. A query that has never run is a hypothesis.
- **Next action:** Export to a real App Insights workspace and execute each query before quoting any of them.

### Events — **Partial**

- **Validated:** 12 event types, CloudEvents projection, in-process bus with deduplication, ordered publication asserted end to end.
- **Gap:** `servicebus.py` is **adapter only**. `apps/worker` consumes the in-process bus and is not yet wired to a Service Bus subscription; there is no dead-letter handling in the worker and no replay.
- **Production implication:** Events are emitted into memory. The Service Bus topic, its duplicate detection and its dead-letter path exist in Bicep and have never carried a message.
- **Next action:** Bind the worker to the `worker` subscription and handle the dead-letter queue.

### Cost attribution — **Partial by design**

- **Validated:** Units and token counts are recorded per correlation id; `frontier_calls_avoided` is counted; a summary refuses to produce a currency figure without a supplied rate card.
- **Gap:** **No price appears anywhere in this repository, deliberately.** Token counts come from the mock reasoner and are therefore fictional.
- **Production implication:** The *method* — cost per completed task, attributed per transaction — is sound. Every number it currently produces is a demonstration.
- **Next action:** Feed a customer rate card and real token counts before quoting cost per task.

### Evaluation — **Complete (against mocks)**

- **Validated:** 16 cases run through the **real workflow**, not a stub. 7 blocking graders. `make eval` exits non-zero on failure, so it can gate a release.
- **Gap:** The graders measure a deterministic mock reasoner and a lexical retriever. **The passing scores describe the harness, not a model.**
- **Production implication:** The gate mechanism is production-shaped. The scores are not transferable.
- **Next action:** Re-baseline every threshold after the first live run.

### READY AI scorecard — **Complete**

- **Validated:** Scores, gates, and produces a remediation backlog. Evidence is required above the lowest maturity level, enforced by a validator.
- **Gap:** None in the framework. **READY AI is an original field framework created for the "Beyond the Agent" session. It is not a Microsoft standard, product or official guidance.**
- **Production implication:** Present it as one practitioner's assessment instrument.
- **Note:** The reference implementation **fails its own release gate**, which is the honest result and is left visible on purpose.

---

## 3. Applications

| Component | Status | Notes |
|---|---|---|
| `apps/api` | **Complete (local)** | FastAPI, correlation, security headers, body limit, in-process rate limit. **The `x-demo-role` header is persona selection, not authentication** — production replaces it with a validated Entra token at the gateway. |
| `apps/worker` | **Complete (local)** | Event consumer with graceful drain on SIGTERM. Holds no connector, so a subscriber cannot write to a system of record. Consumes the in-process bus; the Service Bus consumer is **adapter only**. |
| `apps/web` | **Complete (local)** | React 19 + Vite 8 + TypeScript strict. Renders the whole transaction and labels its own provenance — every screen says whether the figures are fixtures or measurements. |
| `packages/cli` (`reap`) | **Complete** | `demo`, `eval`, `ready`, `audit`, `doctor`. |

### Known API gaps

- **Transaction storage is a module-level dict** (`apps/api/routers/inspections.py`). It does not survive a restart and is per-replica; the approval flow will fail on a second replica. Production replaces it with the evidence store.
- **No authentication.** There is no token validation anywhere in this repository.
- **Rate limiting is per-replica and in-process.** In Azure the quota belongs at the APIM gateway.

---

## 4. Infrastructure and operations

| Component | Status |
|---|---|
| `infra/` Bicep | **Complete, never deployed** — 13 templates compile clean. Nothing has been applied to a subscription. |
| `infra/environments/{dev,test,prod}` | **Complete, never deployed** — all three validate. Owner, cost centre and publisher are `CHANGE-ME` placeholders by design. |
| `infra/apim/ai-gateway.policy.xml` | **Complete, never applied** — token limits, per-user cost attribution, egress hygiene. The Entra path needs an app registration that this subscription may not permit. |
| `infra/monitor/queries/*.kql` | **Complete, never executed** — six queries written against the schema the platform emits. Not one has been run against a real workspace. |
| Private endpoints and DNS zones | **Not implemented** — prod disables public access but provisions no private endpoints, so **deploying prod as written produces resources nothing can reach**. |
| Terraform parity | **Not implemented** |
| `Dockerfile` | **Written, build unverified** — the image build fails on this machine because buildkit cannot reach PyPI (runtime containers resolve it fine). A local container-networking fault, not a template defect, but it means the image has never been built. |
| `docker-compose.yml` | **Config-validated, never run** — depends on the image above. Read-only root filesystem, dropped capabilities, loopback-only ports. |
| `.devcontainer/` | **Not implemented** |
| `.github/workflows/` CI | **Not implemented** — `make check` and `make eval` are not yet enforced on a pull request |
| `azure.yaml` (azd) | **Not implemented** |
| `scripts/scan-secrets.sh` | **Complete** — runs in git mode, found one true positive on first execution |
| `scripts/validate-bicep.sh` | **Complete and exercised** — validates 13 templates and 3 parameter files |
| `scripts/deploy.sh` | **Complete, never exercised against Azure** — refuses to deploy `prod` from a workstation by design |

---

## 5. Documentation

| Document | Status |
|---|---|
| `README.md` | **Complete** |
| `IMPLEMENTATION_STATUS.md` | This file |
| `docs/architecture/*` | **Planned** |
| `docs/adr/*` | **Planned** — `pyproject.toml` already references ADR-0018 and `detector/mock.py` references a model card. **Both links are currently dangling.** |
| `docs/security/threat-model.md` | **Planned** |
| `docs/operations/*` | **Planned** |
| `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` | **Not implemented** |

---

## 6. The five gaps that matter most

Ordered by what would hurt first in a pilot.

1. **Approvals are not durably stored.** A restart loses pending approvals. Everything else in the governance chain depends on this record existing.
2. **No authentication.** The API identifies callers by an HTTP header. This is labelled in code and in this document, and it is the first thing to replace.
3. **No real system-of-record connector.** The refusal chain is proven; the integration is not built.
4. **No CI.** The release gate exists as a command, not as an enforced check.
5. **Prod networking is incomplete.** The prod parameters disable public access on every resource but provision no private endpoints or DNS zones, so `--env prod` as written produces resources nothing can reach. Dev and test are coherent; prod is not yet deployable.

---

## 7. Reuse and attribution

This repository reuses patterns from four MIT-licensed repositories. Where a
pattern was adapted rather than invented, the file that adapted it says so.

| Source | What was reused |
|---|---|
| [foundry-workload-studio](https://github.com/honestypugh2/foundry-workload-studio) | Subscription-scoped Bicep layout; WAF-aligned `modules/` + `environments/` split |
| [wordpress-chatbot](https://github.com/honestypugh2/wordpress-chatbot) | APIM AI Gateway policy: identity precedence (Entra `oid` › `x-user-id` › subscription), per-user token limiting, `azure-openai-emit-token-metric` dimensions, and the chargeback KQL shape |
| [warehouse-replenishment-ai-demo](https://github.com/honestypugh2/warehouse-replenishment-ai-demo) | The governance spine: a deterministic validator ahead of reasoning, one component permitted to mutate the system of record, human approval before any write, citations on every recommendation, mock-first offline default |
| [foundry-copilot-hr-policy-knowledge](https://github.com/honestypugh2/foundry-copilot-hr-policy-knowledge) | uv project shape, retrieval pattern taxonomy, two-phase provision/deploy discipline, the "not production-ready" disclosure convention |

Nothing was copied verbatim. `foundry-copilot-search-validate` is deliberately
not referenced.

---

## 8. What this repository is, and is not

**It is** a reference implementation of the governance architecture around AI
components: contracts, entitlement-aware retrieval, deterministic policy,
human approval, a single scoped writer, hash-chained audit, evaluation gates and
cost attribution — with the central claims enforced by tests rather than prose.

**It is not** a trained model, a benchmark, a product, a Microsoft standard, or
a system that has been deployed. It carries no accuracy, latency, cost or
outcome claim, and it should not be cited as evidence for one.

Local mock mode is the enforced default so that every claim above can be
re-verified by anyone, on any machine, with no Azure subscription:

```bash
make install && make check && make eval && make demo
```
