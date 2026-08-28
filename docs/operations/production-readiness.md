# Production readiness

Two instruments: the **READY AI scorecard**, which assesses a workload, and the
**release gate**, which blocks a merge. The first is a judgement; the second is
a condition.

## READY AI

> **READY AI is an original field framework** created for the *Beyond the Agent*
> session. It is **not** a Microsoft standard, product or official guidance.
> See [ADR-0019](../adr/0019-ready-ai-is-an-original-field-framework.md).

Five weighted dimensions, scored at one of five maturity levels, with a gate and
a remediation backlog.

```bash
reap ready                       # score the reference workload
reap ready --file my-assessment.json
```

**Evidence is required above the lowest level** — a claim without an artifact
scores at the level below. That validator is what stops the scorecard measuring
optimism instead of maturity.

Critical dimensions have a floor independent of the total, so a workload cannot
average its way past a control it does not have.

### The reference implementation fails its own gate

This is the honest result and it is left visible. The repository has no
authentication, no durable approval store, and no deployed environment. A
framework whose author's own code passes trivially would be worth nothing.

## Release gate

```bash
make gate                        # check + eval
```

Non-zero exit blocks a release. Seven blocking graders, five of them at a
threshold of 1.00 because they are governance properties rather than quality
metrics. See [evaluations/framework.md](../evaluations/framework.md).

## Before a pilot

Ordered by what hurts first. These are the same five in
[IMPLEMENTATION_STATUS.md](../../IMPLEMENTATION_STATUS.md), which is
authoritative if the two ever disagree.

1. **Durable approval storage.** Everything in the governance chain depends on the approval record existing. In-memory or file-backed does not survive a restart.
2. **Authentication.** The API identifies callers by an HTTP header. Replace `get_identity` with Entra token validation at the gateway.
3. **A real system-of-record connector.** The refusal chain is proven against in-memory mocks; the integration is unbuilt.
4. **Deploy something.** Fifteen templates compile. Not one resource exists, so every infrastructure claim is a claim about source code.
5. **Re-baseline every evaluation threshold** against real components.

## Operational readiness

| Capability | Status |
|---|---|
| Structured logging with redaction | Complete, stdout only |
| Distributed tracing | Complete in structure, **never exported** |
| Health probes | `/livez` does not touch dependencies; `/readyz` does — a liveness probe that calls a dependency restarts a healthy replica because something else is down |
| Kill switch | Complete. Stops the workload before inference, so it spends nothing |
| Alerting | One Sev-0 rule in Bicep: a write without a recorded approval. **Never deployed** |
| Operational queries | Six KQL files. **None has ever run against a real workspace** |
| Dead-letter handling | Topic and subscription in Bicep; **no consumer handling** |
| Disaster recovery | **Not implemented.** No documented RPO or RTO, no restore procedure, no tested failover |
| Capacity planning | **Not implemented** |
| On-call runbook | **Not implemented** |

## Rollout

| Stage | What it proves | Exit criteria |
|---|---|---|
| Local | The governance path holds | `make gate` passes |
| Dev | The adapters actually work | Every adapter executes against a real service |
| Test | The gate means something | Gate passes against real components with re-baselined thresholds |
| Pilot | The workload is viable | Approval latency within business tolerance; cost per completed task measured |
| Production | It holds under load | Multi-region, tested DR, on-call rota |

The most common mistake is skipping **Test**. A gate that passes against mocks
and a gate that passes against a real model are different claims, and only the
second one is evidence.

## Cost

`make eval` and `reap demo` cost nothing — no cloud dependency.

In Azure, the significant items are APIM (Developer tier is not free and
Premium is substantially more), Foundry model deployments (per token), Azure AI
Search (per replica and partition), and AML managed online endpoints (per
instance-hour, billed whether or not they score anything).

**No price appears in this repository.** Prices vary by region, tier, commitment
and negotiated rate; quoting one would be inventing a number. The cost ledger
records units and refuses to produce a currency figure without a supplied rate
card. See [ADR-0016](../adr/0016-cost-per-completed-task.md).
