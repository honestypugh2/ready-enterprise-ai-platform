# Evaluation framework

Evaluation that produces a dashboard nobody reads is theatre. Evaluation that
blocks a merge is a control.

## What is measured

16 cases run through the **real workflow**, not a stub — `WorkflowEvaluationRunner`
calls `assembly.workflow.run()` and grades what comes out. A harness that grades
a mock grades the mock.

Nine graders, seven of which block a release.

| Grader | Blocking | Threshold | Measures |
|---|---|---|---|
| `entitlement_compliance` | ✅ | 1.00 | No passage returned past an entitlement |
| `policy_compliance` | ✅ | 1.00 | Disposition matches the expected rule |
| `safety` | ✅ | 1.00 | Safety-relevant defects escalate to a human |
| `action_correctness` | ✅ | 1.00 | The action taken is one policy permitted |
| `refusal` | ✅ | 1.00 | Ungrounded or evidence-less cases refuse |
| `retrieval_relevance` | ✅ | 0.80 | Expected sources are retrieved |
| `citation_precision` | ✅ | 0.95 | Every citation resolves to a retrieved passage |
| `grounding` | — | — | Claims are supported by cited text |
| `latency` | — | — | Stage latencies within budget |

Five thresholds are **1.00** because they are governance properties, not quality
metrics. "Entitlement compliance 0.97" means three per cent of the time someone
saw something they should not have.

## Running it

```bash
make eval                        # release gate; non-zero exit blocks a release
reap eval --report reports/x.json
```

`.github/workflows/eval.yml` runs it as **its own status check**, separate from
`ci.yml`. "Tests pass" and "the model behaves acceptably" are different claims,
and one green tick hides which failed.

## What the current scores mean

**They describe the harness, not a model.**

They are measured against a deterministic mock reasoner (a template engine) and
a lexical retriever (hashed character trigrams). The pull request comment says
so on every run:

> Scores are measured against the deterministic mock reasoner and the local
> lexical retriever. They describe the harness, not a model.

Every threshold must be **re-baselined entirely** after the first live run.
A real model brings failure modes this harness has never seen: verbosity,
refusal drift, citation fabrication, and non-determinism across identical
inputs.

## Case design

`data/evaluations/manufacturing-quality.json` covers the governance matrix, not
the input space:

- clean unit, cosmetic finding, low-confidence signal
- safety-relevant major defect, repeat defect in batch, critical structural defect
- restricted classification triggering a guard
- empty evidence, stale evidence, conflicting evidence
- prompt injection present in retrieved content
- an entitlement the caller does not hold

Sixteen cases is **small**, and that is a real limitation. It is enough to catch
a governance regression and nowhere near enough to characterise model quality.

## Why gates rather than reports

A report is read when someone remembers. A gate is a condition.

The gate has already earned its place: running cases through the real workflow
surfaced defects that inspection had missed, including a payload field populated
from the wrong source object.

The obvious failure mode is pressure to lower a threshold to unblock a release.
`CONTRIBUTING.md` requires any threshold change to be justified in the pull
request — a threshold changed deliberately, with a reason, is fine. A threshold
changed to make a build green is the thing to catch in review.

## Adding a case

1. Add to `data/evaluations/manufacturing-quality.json` with `expects`.
2. Pin the detector output if the case is about governance rather than detection — this isolates what is under test.
3. Run `make eval`.

If a new case fails, the interesting question is whether the case or the
platform is wrong. Both have happened.

## Continuous evaluation

Production evaluation is **not implemented**. The design is that the same
graders run against sampled live transactions and feed the same thresholds, so
the release gate and the production dashboard cannot disagree about what "good"
means.

See [ADR-0014](../adr/0014-evaluation-gates-block-a-release.md).
