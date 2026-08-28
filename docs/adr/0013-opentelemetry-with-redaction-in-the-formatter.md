# 0013 — OpenTelemetry, with redaction in the formatter

**Status:** Accepted

## Context

Telemetry is the most commonly overlooked data leak in an AI workload, because
traces contain prompts, retrieved passages and tool arguments *by
construction*. The usual mitigation — redact before display — protects the
dashboard and not the store.

## Decision

OpenTelemetry for tracing, with one root span per transaction and every step as
a child, so a single trace reconstructs the whole decision.

Redaction happens **in the formatter**, before storage: by key
(`SENSITIVE_KEYS`) and by value pattern (JWT, Azure key, email, bearer,
connection string). A caller cannot bypass it by logging an unusual field, and
a new call site cannot forget.

The key is preserved when the value is removed, so telemetry stays queryable.

## Consequences

- Vendor-neutral. Application Insights is one exporter, not a dependency.
- Span names use the workflow's own step vocabulary, so a trace reads the way the architecture diagram is drawn.
- Attributes carry identifiers, versions, counts and decisions — never payload content. Full content lives in the evidence store where access is controlled and retention enforced.
- Exception logging records the type and message, not the traceback, because tracebacks echo local variables and local variables hold payloads.
- Writing the redaction test found a real defect: `logging.LoggerAdapter.process()` replaces the caller's `extra` by default, silently discarding half the structure. `_MergingAdapter` fixes it.
- **A value-pattern heuristic has false positives.** Any long unbroken base64-shaped string is redacted outright, including some hashes. That is the deliberate trade: truncating a credential still leaks most of it.
- **The Azure Monitor exporter has never exported a span,** and the six KQL queries have never run against a real workspace. A query that has never run is a hypothesis.

## What would change this

Nothing about where redaction happens. The key list must be extended after a
data classification review, not after an incident.
