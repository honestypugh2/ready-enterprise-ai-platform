# Presentation mapping

Every message in *Beyond the Agent: Enterprise AI Architecture Patterns and
Production Readiness* mapped to the component that implements it, the test that
enforces it, and the demo step that shows it.

If a row has no test, the claim should be softened or the test written.

## Thesis

> **Agents are not the architecture.** Successful enterprise AI programs are
> built on platforms, governance, retrieval, security, evaluation, operations,
> and measurable business outcomes.

| Message | Component | Enforced by | Demo step |
|---|---|---|---|
| The architecture is planes behind contracts, not an agent | `packages/contracts` | `tests/contract/test_plane_boundaries.py` | `reap doctor` |
| A workflow you can draw does not need to be discovered at run time | `workflows/quality_workflow.py` | 12 named steps in every audit chain | Any scenario |
| Agency is added where it earns its cost, not by default | `workflows/agent_adapter.py` | Step budget, fixed tool set | — |

## Specialized models

| Message | Component | Enforced by | Demo step |
|---|---|---|---|
| A frontier model is the wrong tool for defect detection | `packages/detector` | Three implementations, one protocol | `major-defect` step 1 |
| The model produces a signal, not a verdict | `contracts/detection.py` | Detector cannot emit a disposition | `major-defect` step 1 |
| Confidence is judged against an explicit threshold | `DetectionResult.decision_threshold` | `low-confidence` scenario → `R020` | `low-confidence` |
| Swapping to a real model is one config value | `detector/factory.py` | `test_default_is_the_baseline` | — |
| A forecast without an interval is a fabrication | `packages/predictive_models` | `ForecastPoint` validator | — |
| A model that cannot beat a naive baseline adds nothing | `Forecast.adds_information` | `test_it_loses_to_the_baseline_on_a_seasonal_series` | — |

## Retrieval and grounding

| Message | Component | Enforced by | Demo step |
|---|---|---|---|
| Entitlements are applied before scoring, not after ranking | `retrieval/local.py::_trim` | `test_trimming_happens_before_scoring_not_after_ranking` | `restricted-classification` |
| Empty entitlements means entitled to nothing | `RetrievalQuery` | `test_empty_entitlements_means_entitled_to_nothing` | — |
| Two identities, one index, different correct answers | `IdentityContext` | `test_two_identities_get_different_answers_from_one_index` | `restricted-classification` |
| Retrieved content is data, never instruction | `security/sanitisation.py` | `tests/security/test_prompt_injection.py` | — |
| Every claim carries a resolvable citation | `retrieval/citations.py` | `citation_precision` grader, threshold 0.95 | `major-defect` step 3 |
| Stale evidence is a governed condition, not a surprise | `RetrievedItem.is_stale()` | Guard `G003` | — |

## Governance

| Message | Component | Enforced by | Demo step |
|---|---|---|---|
| Business rules are deterministic and live outside the model | `packages/policy_engine` | `test_same_input_and_version_produce_the_same_decision` | Every scenario step 5 |
| Every decision names its rule, version and file hash | `PolicyDecision` | `test_every_decision_names_its_policy_version_and_hash` | Every scenario step 5 |
| A rule that cannot fire is dead governance | Rule ordering | `test_rule_ids_are_in_sorted_order` — caught `R045` | — |
| Injected instructions cannot move a verdict | Policy reads metadata, not prose | `TestInjectedInstructionsCannotMoveTheVerdict` | — |
| Approval is a named human on this exact proposal | `packages/approvals` | `test_the_requester_cannot_approve_their_own_proposal` | `major-defect` step 6 |
| Dual control means two people, not two clicks | `_resolve_state` | `test_the_same_principal_twice_does_not_satisfy_dual_control` | `critical-defect` |
| An approval is a decision about a moment | Expiry | `test_an_expired_approval_does_not_authorise_a_write` | — |
| Exactly one component may write | `connectors/writer.py` | `tests/contract/test_sole_writer.py` | `major-defect` step 7 |
| Six refusals precede any write, in order | `ScopedWriter.execute` | `inspect.getsource` ordering assertion | — |
| An unbound write cannot be expressed | `ActionRequest` | `test_an_action_request_cannot_be_built_without_its_bindings` | — |
| An audit chain, not a log | `packages/audit` | `verify_chain()` asserted for all 7 scenarios in CI | Every scenario step 8 |
| A failed transaction is audited too | `_execute` halt path | `test_a_halted_transaction_is_persisted_for_review` | Failure injection |

## Security

| Message | Component | Enforced by | Demo step |
|---|---|---|---|
| Every component authenticates as itself | `security/identity.py` | `test_every_plane_has_its_own_identity` | `reap doctor` |
| Telemetry is the most overlooked data leak | `security/redaction.py` | `tests/security/test_telemetry_redaction.py` | — |
| Redaction cannot be bypassed by a new field name | Formatter-level redaction | `test_a_jwt_is_redacted_under_an_innocuous_key` | — |
| Traceback logging leaks payloads | Type + message only | `test_a_traceback_is_reduced_to_its_type_and_message` | — |
| Containment is architectural, not lexical | Policy reads metadata | `test_an_unseen_phrasing_is_not_claimed_to_be_caught` | — |

## Operations and economics

| Message | Component | Enforced by | Demo step |
|---|---|---|---|
| One trace reconstructs the whole decision | `observability/tracing.py` | Root span per transaction | — |
| The kill switch stops the workload before it spends | `kill_switch` | `test_the_kill_switch_stops_the_workload_before_inference` | — |
| Degradation is never silent | Halt records a reason | `test_every_halt_records_a_reason` | Failure injection |
| Cost per completed task, not per call | `cost_attribution/ledger.py` | `cost_per_completed_task` | Every scenario |
| No rate card, no currency figure | `CostSummary` | `test_no_currency_figure_is_invented_without_a_rate_card` | Every scenario |
| Evaluation gates block a release | `packages/evaluation` | `make eval` non-zero exit | `make eval` |

## Honesty

| Message | Where |
|---|---|
| Nothing here has been deployed | `IMPLEMENTATION_STATUS.md` §1 |
| The mock detector carries no accuracy claim | [model card](../architecture/model-cards/mock-detector.md) |
| The evaluation scores describe the harness | PR comment on every gate run |
| There is no authentication | `SECURITY.md`, docstring, and a test asserting the label |
| READY AI is not a Microsoft standard | Package, CLI, API response, README, ADR-0019 |
| The reference implementation fails its own gate | `reap ready` |

## Demo sequence

| # | Scenario | Message | Runtime |
|---|---|---|---|
| 1 | `clean-unit` | The transaction nobody can reconstruct later is the one where nothing happened | ~2s |
| 2 | `low-confidence` | The model did not clear its own threshold, so the platform re-inspects | ~2s |
| 3 | `major-defect` | The hero path: evidence, verdict, held approval, governed write | ~3s |
| 4 | `critical-defect` | Dual control — two distinct principals before anything is written | ~3s |
| 5 | `restricted-classification` | A guard fires on classification alone | ~2s |
| 6 | `make eval` | The gate that would block this release | ~15s |
| 7 | `reap ready` | The reference implementation failing its own gate | ~1s |

Runtimes are measured on a developer laptop in local mock mode and are
indicative, not a benchmark.
