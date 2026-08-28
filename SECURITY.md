# Security Policy

## Reporting a vulnerability

Report privately through
[GitHub security advisories](https://github.com/honestypugh2/ready-enterprise-ai-platform/security/advisories/new).
Do not open a public issue for an exploitable weakness.

Include the command that reproduces it, the execution mode, and what the
weakness would allow in a deployed environment.

## Scope

This is a **reference implementation**, not a deployed system. It is not
production-ready and
[IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) states exactly which
capabilities are real, mocked, or adapter-only.

**In scope** — anything that lets a governance control be bypassed:

- A write reaching a connector without a bound, verified approval
- Evidence returned past an entitlement or classification boundary
- A policy rule that cannot fire, or a guard that widens rather than narrows
- An audit chain that verifies when it should not
- Redaction that can be bypassed by choosing a field name
- A plane reaching past its declared boundary
- Anything that would place a credential in telemetry, an audit receipt or a log

**Out of scope** — already documented as absent, not undiscovered:

- **There is no authentication.** The API selects a synthetic persona from the
  `x-demo-role` header. This is labelled in `apps/api/dependencies.py` and in
  the status document.
- Rate limiting is per-replica and in-process; the real control belongs at the
  API Management gateway.
- Transaction state is a module-level dictionary that does not survive a
  restart and is not shared across replicas.
- Approvals are stored in memory or in JSON files, not in a durable store.
- The mock detector, mock reasoner and local retriever are fixtures. Their
  outputs carry no quality claim and cannot be "wrong".

If you find something in the out-of-scope list that is *worse than documented*,
that is in scope.

## What this repository does not contain

- No credential, key, connection string or token. `make secrets` enforces this
  on every change, and CI runs it against full history.
- No code path that accepts a connection string. Every Azure dependency is
  reached with a managed identity.
- No customer data. Every fixture is synthetic and labelled as such.
- No trained model weights.

`data/knowledge/adversarial-corpus.json` contains **deliberate prompt-injection
payloads**. They exist so that containment can be tested rather than claimed.
They are entitlement-gated behind `grp-security-test` and must never be indexed
into a production corpus.

## Controls that are enforced rather than described

Each of these fails the build if it stops being true:

| Control | Enforced by |
|---|---|
| Only one component may write to a system of record | `tests/contract/test_sole_writer.py` — reads the import graph |
| Reasoning cannot decide, approve or write | `tests/contract/test_plane_boundaries.py` |
| Six refusals precede any write, in order | `tests/unit/test_scoped_writer.py` |
| Separation of duties and dual control | `tests/security/test_authorization.py` |
| Entitlements applied before scoring, not after ranking | `tests/security/test_authorization.py` |
| Redaction cannot be bypassed by an unusual field name | `tests/security/test_telemetry_redaction.py` |
| An injected instruction cannot move a verdict | `tests/security/test_prompt_injection.py` |
| Local mock mode cannot reach a cloud provider or disable dry run | `packages/platform_config/settings.py` validator |

## Supported versions

`main` only. This repository is not versioned for production use.
