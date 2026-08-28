# 0001 — A new integration repository rather than extending an existing accelerator

**Status:** Accepted

## Context

Four existing repositories already demonstrate parts of this architecture:
`foundry-workload-studio` (multi-workload platform, WAF-aligned Bicep),
`warehouse-replenishment-ai-demo` (governed human-in-the-loop with a single
writer), `foundry-copilot-hr-policy-knowledge` (five retrieval patterns
compared with evidence), and `wordpress-chatbot` (APIM AI Gateway with per-user
cost attribution).

Extending one of them would have been cheaper.

## Decision

Build a new repository that integrates the patterns, and attribute what it
reuses.

Each existing repository is organised around the thing it proves. Bolting a
governance spine onto the HR knowledge repo would obscure what that repo is
*for* — comparing retrieval patterns — and make both stories harder to tell.
`warehouse-replenishment-ai-demo` is architecturally closest, but it is a
Copilot Studio and Databricks demonstration; the governance is a property of
that demo rather than the subject.

This repository's subject is the governance itself: the claim that agents are
not the architecture. That needs a codebase where the controls are the point
and the AI components are substitutable.

## Consequences

- Four repositories now demonstrate overlapping patterns, and a reader has to be told which to start from.
- Improvements do not propagate. A fix to the writer here does not reach the warehouse demo.
- Attribution is a maintenance obligation, recorded in [reuse-and-attribution.md](../architecture/reuse-and-attribution.md).
- In exchange, the central claims can be enforced by tests rather than described, because nothing else in the repository competes for that role.

## What would change this

If a fifth repository needed the same governance spine, the spine should become
a published package that all of them depend on, and this repository should
become its reference consumer rather than its home.
