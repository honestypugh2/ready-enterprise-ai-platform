# Implementation Status

This document exists because a reference architecture that does not say what is
real is a marketing artifact.

Every capability the README, the presentation or the code comments claim is
listed here on **two axes**, because one was hiding something:

- **What exists** — is the code written, and does it do the thing?
- **What has been proven** — and *by what*, specifically?

An earlier version of this document used a single **Complete** column. It read
identically for a policy engine covered by 98 tests and for a Bicep template
that had only ever been parsed. Both were "Complete". That is exactly the
elision this document exists to prevent, so the two are now separated.

- **Last verified:** 2026-08-31
- **Verified by:** local quality gates, deployment `reap-dev-final`, and a live `reap demo replenish --persist` run against `rg-reap-dev`
- **Execution mode:** `local_mock` by default; the live run used Azure AI Search, Foundry, and Application Insights while keeping the detector and approver synthetic and D365 in dry run

---

## The one-line summary

> **This repository's development infrastructure is deployed in `rg-reap-dev`.**
> The live replenishment path has observed Azure AI Search retrieval, a Foundry
> `gpt-4o-mini` completion, and an Application Insights trace. AML scoring,
> Service Bus messaging, APIM policy application, application hosting, and every
> real system-of-record write remain unproven.

The governance core is heavily tested offline. The live proof is narrow: it
proves the deployed demo path, not every provisioned service or production
posture.

| Proof level | What it means | Where it applies |
|---|---|---|
| ⬤ **Proven** | Executed against the real dependency, result observed | Search retrieval, Foundry completion, correlated Application Insights trace, and the governed dry-run replenishment chain |
| ◑ **Tested** | Executed offline against fixtures, with automated tests asserting the behaviour | The governance core: contracts, policy, approvals, the writer, audit, retrieval trimming, redaction |
| ◔ **Checked** | Parsed, compiled or schema-validated. Never executed | Bicep templates, parameter files, compose config, documentation links |
| ○ **Written** | Source exists. Never executed or validated in any way | Every Azure adapter, the APIM policy, the KQL queries, the CI workflows, the container image |
| — **Absent** | Named somewhere; no code exists | Terraform parity, DR guidance, on-call runbook, `CODE_OF_CONDUCT.md` |

Deliberately no counts: they would need hand-maintaining and would drift, which
is the failure mode this document exists to avoid. The **Proven** row is the one
to read, and it is verifiable — `git log` contains no deployment.

---

## Vocabulary

**Implementation** — what exists:

| Term | Meaning |
|---|---|
| **Implemented** | The code does the thing it claims |
| **Partial** | Implemented for the demonstrated path; named gaps remain |
| **Mocked** | Deliberately synthetic. The architecture *around* it is real; the component is not |
| **Adapter only** | Real client code against a real service contract, never pointed at the service |
| **Absent** | No code exists |

**Proof** — what has actually been demonstrated:

| Level | Means | Does **not** mean |
|---|---|---|
| ⬤ **Proven** | Ran against the real dependency; output observed | — |
| ◑ **Tested** | Ran offline; automated tests assert the behaviour | That it works against a real service |
| ◔ **Checked** | Compiled, parsed or schema-validated | That it runs, deploys, or is correct |
| ○ **Written** | The file exists | Anything at all |

The distinction that matters most: **Tested ≠ Proven.** A test against a mock
detector proves the governance path *around* a detector. It proves nothing about
detection.

---

## 1. Verification actually performed

| Check | Command | Result | Proof |
|---|---|---|---|
| Lint + format | `make lint` | Clean, 120 files | ◑ |
| Static types | `make typecheck` | mypy `--strict`, 101 source files | ◑ |
| Unit | `pytest tests/unit` | 98 passed | ◑ |
| Contract | `pytest tests/contract` | 31 passed | ◑ |
| Security | `pytest tests/security` | 80 passed | ◑ |
| Integration (offline) | `pytest tests/integration` | 60 passed | ◑ |
| Resilience | `pytest tests/resilience` | 20 passed | ◑ |
| **Total** | `pytest tests` | **289 passed** | ◑ |
| Evaluation gate | `make eval` | PASS, 16 cases, 7 blocking graders | ◑ |
| Secret scan | `make secrets` | Clean, 240 tracked files, 6 reviewed exceptions | ◑ |
| Demo | `reap demo run` × 7 | All complete, audit chains verify | ◑ |
| Dependency audit | `pip-audit --strict` | No known vulnerabilities | ◑ |
| Frontend | `npm lint/typecheck/test/build` | Clean, 0 npm audit findings | ◑ |
| Bicep | `make infra-lint` | 15 templates + 3 params compile | ◔ |
| Compose | `docker compose config` | Valid, 3 services | ◔ |
| Doc links | link checker | 94/94 resolve | ◔ |

**Never run:** any AML scoring call; any Service Bus message; any real D365
write; any GitHub Actions workflow; any container image build or application
host deployment.

---

## 2. Platform planes

### Contracts — Implemented · ◑ Tested

- **Proven by:** `tests/contract/test_plane_boundaries.py` parses the import graph and fails if a plane reaches past its boundary. `contracts` is proven to depend on nothing.
- **Gap:** `CONTRACT_VERSION` exists with no cross-version compatibility test, because there is only one version.
- **If deployed:** fine today; a second version could break a consumer silently.
- **Next:** schema-snapshot test before the first contract change.

### Configuration and execution modes — Implemented · ◑ Tested

- **Proven by:** the settings validator raises when `local_mock` names a cloud provider or disables `dry_run`; `production` refuses to start without App Insights, Search and reasoning endpoints.
- **Gap:** `azure_dev` and `production` have never been instantiated against real endpoints.
- **If deployed:** the validator's *shape* is proven; its interaction with real credential resolution is not.
- **Next:** exercise both modes in the first deployed environment.

### Detector — Mocked + Adapter only · ◑ Tested / ○ Written

| Implementation | State | Proof |
|---|---|---|
| `DeterministicMockDetector` | Implemented (fixture) | ◑ Tested |
| `OnnxDetector` | Adapter only | ○ Written — never run with real weights |
| `AzureMLEndpointDetector` | Adapter only | ○ Written — never called |

- **Proven by:** all three satisfy one protocol; the mock is deterministic across machines; failure injection produces a halt, not an answer.
- **Gap:** **no trained model exists here and no accuracy claim is made.** The mock derives a distribution from a SHA-256 hash. See [the model card](docs/architecture/model-cards/mock-detector.md).
- **If deployed:** the governance architecture transfers; detection quality is entirely unestablished.
- **Next:** train on real inspection data; establish the false-negative rate on safety-relevant classes.

### Predictive models — Implemented · ◑ Tested (unused)

- **Proven by:** `ForecastPoint` will not validate without an interval containing its own value; `adds_information` is False for a model that never beat seasonal-naive *and* for one never measured; MAPE raises rather than flattering an all-zero series.
- **Gap:** `AzureMLForecaster` is ○ Written. **No forecast is consumed by the workflow** — the plane is tested in isolation and wired to nothing.
- **If deployed:** nothing depends on it, so nothing breaks. A demonstrated capability, not a used one.
- **Next:** wire it into the policy input as an advisory signal, or state plainly that it is illustrative.

### Retrieval — Partial · ◑ Tested / ⬤ Proven for Azure Search

| Implementation | State | Proof |
|---|---|---|
| `LocalKnowledgeRetriever` | Implemented | ◑ Tested |
| `AzureSearchRetriever` | Adapter only | ⬤ Proven — entitlement-filtered query observed against `replenishment-knowledge` |
| `AgenticRetriever` | Partial | ○ Written — decomposition implemented, never run live |
| Azure Search demo indexer | Implemented | ⬤ Proven — 8 labelled synthetic passages uploaded |

- **Proven by:** entitlements and classification applied **before** scoring, asserted by a test that asks for `top_k=1` and requires one real result; empty entitlements return nothing; two identities get different answers from one corpus.
- **Gap:** the local "vector" component is **hashed character trigrams, not a semantic embedding model.** Relevance quality is not representative of anything.
- **If deployed:** the *governance* of retrieval transfers directly. The *retrieval quality* does not.
- **Next:** run the full evaluation suite against the provisioned index and compare graders before making a retrieval-quality claim.

### Reasoning — Mocked + Adapter only · ◑ Tested / ⬤ Proven on the repo deployment

| Implementation | State | Proof |
|---|---|---|
| `MockReasoner` | Implemented (template engine) | ◑ Tested |
| `FoundryReasoner` | Adapter only | ⬤ Proven — structured `gpt-4o-mini` completions observed for both replenishment scenarios |

- **Proven by:** `Recommendation` has no field for a verdict, asserted by a contract test; non-refusing output must cite a retrieved passage; the plane cannot import `connectors`, `approvals` or `policy_engine`.
- **Gap:** the mock is a template engine. The one live completion proves adapter compatibility, not output quality, repeatability, or an evaluation threshold.
- **If deployed:** substituting a real model changes wording and cost, not authority — but it is untested against a real model's failure modes: verbosity, refusal drift, citation fabrication, non-determinism.
- **Next:** run the citation graders against a live deployment before quoting any citation-precision figure.

### Model routing — Implemented · ◑ Tested (offline)

- **Proven by:** versioned, hash-identified policy; every decision records the selected route, the reason codes, and the *excluded* candidates with reasons.
- **Gap:** route health probing is stubbed. Cost and latency attributes are **declared, not measured.**
- **If deployed:** the routing *decision* is auditable; the inputs it routes on are placeholders.
- **Next:** replace declared `typical_latency_ms` with measured values, or mark the field advisory.

### Policy engine — Implemented · ◑ Tested

- **Proven by:** 8 rules, 3 guards, first-match-wins with ascending-id order enforced by a test. Every decision names its policy version and file hash. Guards can only narrow. Denied outcomes cannot permit actions.
- **Two dead-governance defects have been caught here, both of which had passed review:**
  - `R045` sat below the broader `R040` and could never fire → renumbered `R035`, rule-order test added.
  - `low_confidence_floor` was declared, schema-validated and **read by nothing**. R020 used the *detector's own* threshold, so a model deployed at `0.20` would have driven a work order on a 41% signal. Policy now has an independent floor. Version 2.6.0.
- **Gap:** policy is a file on disk. No signing, no change-control workflow, no policy-change audit event.
- **If deployed:** **whoever can write the policy file can change what the platform is allowed to do.** The most significant unmitigated risk in the design.
- **Next:** source policy from a signed artifact; record version changes as audit events.

### Approvals — Implemented · ◑ Tested

- **Proven by:** separation of duties, role match, expiry, revocation, and dual control requiring **two distinct principals** — a test asserts that one person deciding twice does not satisfy it.
- **Gap:** `InMemoryApprovalStore` is the default and `JsonFileApprovalStore` the alternative. Neither is durable or replicated.
- **If deployed:** **an approval does not survive a replica restart.** The single most important storage gap.
- **Next:** back approvals with Cosmos DB or Azure SQL before any pilot.

### Connectors and the scoped writer — Implemented · ◑ Tested (against mocks)

- **Proven by:** six refusals precede any write; `tests/contract/test_sole_writer.py` reads the import graph and fails if any module outside the writer acquires a connector; `inspect.getsource` proves `verify_for_write` precedes `_attempt_write`.
- **Gap:** all three connectors are **in-memory**. No real ERP, ServiceNow or D365 call has ever been made.
- **If deployed:** the authorization chain transfers. The integration — auth, throttling, schema drift, partial-failure semantics — is unbuilt, so its failure modes are unknown.
- **Next:** implement one real connector behind the same protocol and re-run `tests/resilience` against it.

### Audit — Implemented · ◑ Tested

- **Proven by:** hash-chained steps from a genesis hash; `verify_chain()` asserted for all seven scenarios; receipts sealed for failed and halted transactions too; attributes redacted on the way in.
- **A defect was found here during review:** the credential heuristic matched hex digests, so `input_hash`, `policy_sha` and `proposal_fingerprint` were being replaced with `[redacted]`. **The chain still verified** — the receipt looked valid and could no longer say which frame was inspected. Content hashes are now held out of the credential scan, with regression tests.
- **Gap:** `JsonFileAuditStore` is write-once by convention. The immutability policy exists in `infra/modules/storage.bicep` and has never been deployed.
- **If deployed locally:** an audit record can be deleted by anyone who can delete a file.
- **Next:** deploy the storage module and point state at the immutable container.

### Observability — Partial · ◑ Tested / ⬤ Proven for trace export

- **Proven by:** one root span per transaction with every step a child; redaction in the formatter, so no call site can bypass it. A `LoggerAdapter` bug that silently dropped caller-supplied fields was found and fixed.
- **Proven live by:** the synthetic governed replenishment transaction exported to `reap-dev-appi` and was queried by correlation and trace ID in `reap-dev-law`; transaction, reasoning, validation, and action spans were observed.
- **Gap:** metrics are in-process counters. The six repository KQL files have not all been exercised.
- **Next:** execute every checked-in query before quoting operational coverage.

### Events — Partial · ◑ Tested / ○ Written

- **Proven by:** 12 event types, CloudEvents projection, in-process bus with deduplication, ordered publication asserted end to end.
- **Gap:** `servicebus.py` is ○ Written. The worker consumes the in-process bus only; no dead-letter handling, no replay.
- **If deployed:** the Service Bus topic and its dead-letter path exist in Bicep and have never carried a message.
- **Next:** bind the worker to the subscription and handle the dead-letter queue.

### Cost attribution — Partial by design · ◑ Tested

- **Proven by:** units and token counts recorded per correlation id; `frontier_calls_avoided` counted; the summary **refuses** a currency figure without a supplied rate card.
- **Gap:** **no price appears anywhere in this repository, deliberately.** Token counts come from the mock reasoner and are fictional.
- **If deployed:** the *method* is sound. Every number it currently produces is a demonstration.
- **Next:** supply a real rate card and real token counts before quoting cost per task.

### Evaluation — Implemented · ◑ Tested (against mocks)

- **Proven by:** 16 cases through the **real workflow**, not a stub; 7 blocking graders; non-zero exit gates a release.
- **Gap:** the graders measure a template engine and a lexical retriever. **The passing scores describe the harness, not a model.**
- **If deployed:** the gate mechanism is production-shaped. The scores are not transferable.
- **Next:** re-baseline every threshold after the first live run.

### READY AI scorecard — Implemented · ◑ Tested

- **Proven by:** scores, gates, produces a remediation backlog; evidence required above the lowest level, enforced by a validator.
- **Labelling:** **READY AI is an original field framework** created for the *Beyond the Agent* session. It is **not** a Microsoft standard, product or official guidance.
- **Note:** the reference implementation **fails its own release gate.** That is the honest result and is left visible.

---

## 3. Applications

| Component | Implementation | Proof | Notes |
|---|---|---|---|
| `apps/api` | Implemented | ◑ Tested | **The `x-demo-role` header is persona selection, not authentication** |
| `apps/worker` | Implemented | ◑ Tested | Graceful SIGTERM drain. Holds no connector. In-process bus only |
| `apps/web` | Implemented | ◑ Tested | React 19 + Vite 8, TS strict. Labels every figure as fixture or measurement |
| `packages/cli` (`reap`) | Implemented | ◑ Tested | `demo`, `eval`, `ready`, `audit`, `doctor`, Azure index/preflight |

### Known API gaps

- **No authentication.** No token validation exists anywhere in this repository.
- **Transaction storage is an in-process LRU map**, bounded at 1,000 entries after a review found it unbounded. It does not survive a restart and is per-replica, so the approval flow fails on a second replica.
- **Rate limiting is per-replica and in-process**, with stale-window eviction added after the same review. The real control is the APIM gateway.

---

## 4. Infrastructure and operations

The development infrastructure is deployed in the repo-owned `rg-reap-dev` resource group. Provisioning is not proof that an adapter has executed; those distinctions remain explicit below.

| Component | Implementation | Proof | Notes |
|---|---|---|---|
| `infra/` Bicep | Implemented | ⬤ Proven for dev provisioning | Deployment `reap-dev-final` succeeded in East US |
| `infra/demo/` Search-only Bicep | Implemented | ◔ Checked | Superseded by the isolated full dev deployment |
| `infra/environments/{dev,test,prod}` | Implemented | ◔ Checked | All three validate. Owner and cost centre are `CHANGE-ME` by design |
| Private endpoints, DNS, VNet | Implemented | ◔ Checked | Derived from the environment, so prod cannot omit them |
| `infra/apim/ai-gateway.policy.xml` | Implemented | ○ Written | APIM service exists, but policy application is disabled until the Entra app registration and logger auth are supplied |
| `infra/monitor/queries/*.kql` | Implemented | ○ Written | Six queries. **Not one has been run** |
| `Dockerfile` | Implemented | ○ Written | **Build fails locally** — buildkit cannot reach PyPI. An environment fault, but the image has never been built |
| `docker-compose.yml` | Implemented | ◔ Checked | Config-valid, never run. Depends on the image above |
| `azure.yaml` (azd) | Implemented | ◔ Checked | Never run. `scripts/deploy.sh` is the reviewed path |
| `.github/workflows/` | Implemented | ○ Written | **Never executed on GitHub.** Every command was verified locally; the workflows have not run |
| `.github/dependabot.yml` | Implemented | ○ Written | uv, npm, actions, docker |
| `.devcontainer/` | Implemented | ○ Written | Never opened |
| `scripts/scan-secrets.sh` | Implemented | ◑ Tested | Runs in git mode; found a true positive on first execution |
| `scripts/validate-bicep.sh` | Implemented | ◑ Tested | Validates 15 templates + 3 parameter files |
| `scripts/deploy.sh` | Implemented | ◔ Checked | Deployment used the equivalent reviewed Azure CLI path; script itself was not used for apply |
| `reap azure index/preflight` | Implemented | ⬤ Proven | Index upload and all live preflight checks passed |
| Terraform parity | Absent | — | |

---

## 5. Documentation

All tracked public documentation links are checked by the repository validation
suite. Presenter mapping, field positioning, and decision notes are maintained
locally and are intentionally excluded from the published repository.

| Document | State |
|---|---|
| `README.md`, `AGENTS.md`, `SECURITY.md`, `CONTRIBUTING.md` | Implemented |
| `docs/architecture/overview.md` | Implemented — planes, trust boundaries, where each claim is enforced |
| `docs/architecture/reuse-and-attribution.md` | Implemented |
| `docs/architecture/model-cards/mock-detector.md` | Implemented — opens by stating it is not a model |
| `docs/security/threat-model.md` | Implemented — STRIDE + OWASP LLM Top 10, unmitigated risks named |
| `docs/security/authorization-model.md` | Implemented |
| `docs/evaluations/framework.md` | Implemented |
| `docs/operations/execution-modes.md` | Implemented |
| `docs/operations/preview-register.md` | Implemented — every preview API version, pinned constraint and non-version prerequisite in one place |
| `docs/operations/production-readiness.md` | Implemented |
| `docs/demo/runbook.md` | Implemented — including the questions you will be asked |
| `CODE_OF_CONDUCT.md` | Absent |
| Disaster recovery guidance | Absent — no RPO, no RTO, no tested restore |
| Operations runbook / on-call | Absent |

---

## 6. The five gaps that matter most

Ordered by what would hurt first in a pilot.

1. **Approvals are not durably stored.** A restart loses pending approvals, and everything else in the governance chain depends on that record existing.
2. **No authentication.** The API identifies callers by an HTTP header. Documented, not undiscovered — and the first thing to replace.
3. **No real system-of-record connector.** The refusal chain is proven against in-memory mocks; the integration is unbuilt, so its failure modes are unknown.
4. **Nothing has been deployed.** The ⬤ Proven column is empty. Every infrastructure claim in this document is a claim about source code.
5. **The evaluation scores describe the harness.** Measured against a template engine and a lexical retriever; they must be re-baselined entirely against real components.

### What review has already found

Listed because a document claiming rigour should show its own defect history.
Each of these passed inspection before a later pass caught it.

| Defect | Why it mattered | Now |
|---|---|---|
| `R045` unreachable below `R040` | Dead governance that looked live | Renumbered `R035`; rule-order test |
| `low_confidence_floor` read by nothing | The *model* decided when its own output was trustworthy | Independent policy floor; policy 2.6.0 |
| Redaction destroyed audit provenance | The chain still verified but could not say which frame was inspected | Hashes held out of the credential scan |
| `LoggerAdapter` dropped caller fields | Structured logging silently losing its structure | `_MergingAdapter` |
| Payload built from the wrong source field | Work-order contents subtly wrong | Authoritative request fields |
| Two unbounded maps in the request path | Memory leak, trivially triggered | Both bounded |

---

## 7. Reuse and attribution

Patterns reused from four MIT-licensed repositories. Where a pattern was adapted
rather than invented, the file that adapted it says so. Full detail in
[docs/architecture/reuse-and-attribution.md](docs/architecture/reuse-and-attribution.md).

| Source | What was reused |
|---|---|
| [foundry-workload-studio](https://github.com/honestypugh2/foundry-workload-studio) | Subscription-scoped Bicep layout; WAF-aligned `modules/` + `environments/` split |
| [wordpress-chatbot](https://github.com/honestypugh2/wordpress-chatbot) | APIM AI Gateway: identity precedence (Entra `oid` › `x-user-id` › subscription), per-user token limiting, token-metric dimensions, chargeback KQL shape |
| [warehouse-replenishment-ai-demo](https://github.com/honestypugh2/warehouse-replenishment-ai-demo) | The governance spine: a deterministic validator ahead of reasoning, one component permitted to mutate the system of record, human approval before any write, citations on every recommendation, mock-first offline default |
| [foundry-copilot-hr-policy-knowledge](https://github.com/honestypugh2/foundry-copilot-hr-policy-knowledge) | uv project shape, retrieval pattern taxonomy, two-phase provision/deploy discipline, the "not production-ready" disclosure convention |

Nothing was copied verbatim. `foundry-copilot-search-validate` is deliberately
not referenced.

---

## 8. What this repository is, and is not

**It is** a reference implementation of the governance architecture around AI
components: contracts, entitlement-aware retrieval, deterministic policy, human
approval, a single scoped writer, hash-chained audit, evaluation gates and cost
attribution — with the central claims enforced by tests rather than prose.

**It is not** a trained model, a benchmark, a product, a Microsoft standard, or
a system that has been deployed. It carries no accuracy, latency, cost or
outcome claim, and it should not be cited as evidence for one.

Local mock mode is the enforced default so that every ◑ **Tested** claim above
can be re-verified by anyone, on any machine, with no Azure subscription:

```bash
make install && make check && make eval && make demo
```

The ⬤ **Proven** claims cannot be re-verified by anyone, because there are none
yet.
