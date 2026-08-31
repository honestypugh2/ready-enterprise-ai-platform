# Demo runbook

## Protected live Azure sequence - slides S16-S18

The 16:00-20:00 window runs from the presenter workstation and uses real Azure
AI Search, Microsoft Foundry, and Application Insights resources in
`rg-reap-dev`.
It does not require Docker, Container Apps, the API, worker, web application,
AML or APIM. The detector and approver remain labelled synthetic fixtures, and
the scoped writer remains a dry run. No ERP write is claimed.

The validated development infrastructure is deployed from the full repository
template:

```bash
AZURE_LOCATION=eastus scripts/deploy.sh --what-if --env dev
AZURE_LOCATION=eastus scripts/deploy.sh --apply --env dev
```

Install the optional clients, set `REAP_MODE=azure_dev`, and configure Search
plus the repo-owned reasoning and Application Insights resources. The Foundry
adapter requires the account's Azure OpenAI endpoint, not its general
Cognitive Services endpoint. Then populate the index and run preflight:

```bash
source .venv/bin/activate
make install-all
make azure-demo-index
make azure-demo-preflight
```

Preflight observes an Azure credential and the configured Search index. It
checks Foundry and telemetry configuration, but only the scenario itself can
prove a model completion and exported trace:

```bash
reap demo replenish --persist
```

Narrate seven beats: retrieve, cite, reject the unsafe SKU deterministically,
explain the safe candidate with Foundry, capture a separate human approval,
hold the scoped writer in dry run, and show the correlated trace plus
audit/evaluation evidence.

If preflight or the live scenario fails, say **"Azure fallback"** before using
the captured local run. Never present fallback output as a live Azure result.

## Offline rehearsal and fallback

Everything below runs offline. No Azure subscription, no credential, no network
after `make install`. That is deliberate — a demo that depends on a conference
network needs a rehearsed fallback.

## Setup, once

```bash
make install-all
source .venv/bin/activate
make check          # ~10s — proves the machine is ready
```

If `make check` passes, the demo will run.

## Rehearse

```bash
reap demo replenish --persist
```

This is the only conference demo. It runs the unsafe rejection followed by the
approved dry-run order using labelled synthetic inventory, supplier, approver,
and D365 data.

## The replenishment sequence

### 1 · Unsafe candidate

```bash
reap demo run --scenario unsafe-replenishment
```

Leave the deterministic rejection on screen. The model does not get a vote on
an authoritative constraint.

### 2 · Governed candidate

```bash
reap demo run --scenario governed-replenishment --persist
```

Show evidence, explanation, the inventory-manager approval, the dry-run D365
receipt, and the verified audit chain. Every displayed business value is a
synthetic fixture.

Ending on the failing scorecard is the strongest available move. It converts
the whole session from a product pitch into a working assessment.

## With the API and UI

```bash
make dev            # terminal 1 — http://127.0.0.1:8000/docs
make web            # terminal 2 — http://127.0.0.1:5173
```

The UI renders the same transaction and labels every figure as a fixture or a
measurement. Use it when the audience is not comfortable reading a terminal.

## No network at all

Everything above already works offline **after** `make install`. If the venv is
already built, unplug and it still runs.

Pre-recorded fallbacks belong in `docs/demo/recordings/`.

## If something breaks

| Symptom | Cause | Fix |
|---|---|---|
| `reap: command not found` | venv not active | `source .venv/bin/activate` |
| Scenario produces the wrong label | Fixture pins not loaded | `reap demo list` first, which loads and pins all seven |
| API 404 on `/v1/inspections/{id}` | Transaction state is per-replica and in-memory | Restart, re-run the scenario |
| `make web` fails on install | Node too old | `node --version`, needs 24+ |
| Port already in use | Previous run | `pkill -f uvicorn` |

## Questions you will be asked

**"Is this production-ready?"**
No, and `IMPLEMENTATION_STATUS.md` lists exactly why. Development infrastructure
is deployed, but there is no application authentication, durable approval
store, hosted application, or real connector.

**"How accurate is the model?"**
There is no model. The detector is a hash-seeded fixture and carries no accuracy
claim. See the model card.

**"What does it cost?"**
No price appears anywhere in this repository. The ledger records units and
refuses to produce a currency figure without a rate card, because it does not
know yours.

**"Is READY AI a Microsoft standard?"**
No. It is an original field framework created for this session.

**"Why not just use an agent?"**
For this workload the sequence is known, so discovering it per request costs a
model call per decision and buys nothing. Add agentic orchestration only when
runtime variation justifies its coordination and failure surface.

**"Has any of this been deployed?"**
Yes. The development stack is provisioned in `rg-reap-dev`. The live demo has
observed Search retrieval, a Foundry completion, and an Application Insights
trace. AML scoring, Service Bus messaging, APIM policy execution, hosted
applications, and real D365 writes remain unproven.
