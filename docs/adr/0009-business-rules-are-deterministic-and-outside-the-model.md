# 0009 — Business rules are deterministic and outside the model

**Status:** Accepted

## Context

A model can be prompted to decide a disposition. It will produce a plausible
one. It will not produce the same one twice for the same input, cannot name the
rule it applied, and can be argued into a different answer by text in a
retrieved document.

## Decision

`packages/policy_engine` executes a versioned YAML document. Given a detection,
evidence metadata, a classification and a batch defect count, it returns a
`PolicyDecision` naming the disposition, the severity, whether approval is
required, which role, the permitted actions, the matched rule ids, the reason
codes, the policy version and the **SHA-256 of the policy file**.

Evaluation is first-match-wins, so file order is part of the contract and rule
ids must be in ascending order — enforced by a test.

Guards may only narrow an outcome, never widen it.

## Consequences

- The same input and the same policy version always produce the same verdict.
- "Why was this quarantined?" is answered with a rule id, not a paragraph.
- **Policy reads detection signals and evidence *metadata*, never passage prose.** This is what makes prompt injection unable to move a verdict, and it is asserted directly in `tests/security/test_prompt_injection.py`.
- The rule-order test caught real dead governance: `R045-repeat-major-in-batch` sat below the broader `R040` and could never fire. It was renumbered to `R035`. It had passed review.
- **A YAML rules engine is inflexible by design.** Expressing a genuinely fuzzy judgement requires either a new closed-vocabulary condition or admitting the judgement belongs to a human.
- **Whoever can write the policy file can change what the platform may do.** There is no signing and no change-control workflow. This is the most significant unmitigated risk in the design.

## What would change this

The unmitigated risk needs closing regardless: policy should come from a signed
artifact, and a policy version change should itself be an audited event.
