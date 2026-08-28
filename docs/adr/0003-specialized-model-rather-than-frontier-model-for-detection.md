# 0003 — A specialized model for detection, not a frontier model

**Status:** Accepted

## Context

A multimodal frontier model can describe a defect in a photograph. It is also
the most expensive, slowest and least reproducible way to answer a question
that a small CNN answers in single-digit milliseconds — and it cannot be
calibrated against a decision threshold, which is what the policy engine needs.

## Decision

Detection is a specialized model behind `packages/detector`: a mock by default,
an ONNX graph for local execution, an Azure ML managed online endpoint for
production. The frontier model never sees the frame.

The detector emits a label, a confidence and the threshold it was judged
against. It cannot decide what the business does next, and nothing in that
package is capable of doing so.

## Consequences

- Cost and latency are bounded and predictable per inspection.
- The decision threshold is an explicit, versioned, tunable number rather than a property of a prompt.
- Model quality is established with a real evaluation set on the customer's own data — which is work this repository does not do and does not claim to.
- **A separate MLOps lifecycle exists:** training, registration, deployment, drift monitoring. That is a real cost this decision imposes.
- This repository ships **no trained model** and makes **no accuracy claim**. The mock is a fixture that derives a distribution from a SHA-256 hash. See [the model card](../architecture/model-cards/mock-detector.md).

## What would change this

A workload where the visual task is genuinely open-ended — "describe anything
unusual" rather than "is this one of seven defect classes" — where no
enumerable label set exists to train against.
