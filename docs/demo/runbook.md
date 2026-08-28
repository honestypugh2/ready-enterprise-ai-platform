# Demo runbook

Everything below runs offline. No Azure subscription, no credential, no network
after `make install`. That is deliberate — a demo that depends on a conference
network is a demo that fails on stage.

## Setup, once

```bash
make install
source .venv/bin/activate
make check          # ~10s — proves the machine is ready
```

If `make check` passes, the demo will run.

## Rehearse

```bash
make demo-all       # every scenario, ~20s
```

Run this the morning of. It catches a broken fixture before an audience does.

## The seven-minute sequence

### 1 · Clean unit — ~2 min

```bash
reap demo run --scenario clean-unit
```

Nothing is wrong, and the platform still records evidence.

> *"The transaction nobody can reconstruct later is the one where nothing
> happened. This one gets the same receipt as every other."*

Point at the audit chain and `[PASS] chain verifies`.

### 2 · Low confidence — ~1 min

```bash
reap demo run --scenario low-confidence
```

The detector reported 41% against a 62% threshold.

> *"The model did not clear its own threshold. Policy re-inspects rather than
> raising a work order on a signal the model does not stand behind. Rule
> R020 — not a prompt, a rule id."*

### 3 · The hero path — ~3 min

```bash
reap demo run --scenario major-defect
```

The whole argument, in one transaction:

- **Step 1** — a specialized model, 8ms, no frontier call
- **Step 3** — evidence with citations and an entitlement trim count
- **Step 4** — the explanation, which cites and does not decide
- **Step 5** — the verdict, with a rule id, a policy version and a file hash
- **Step 6** — the approval, held, with evidence as data
- **Step 7** — the write, dry run
- **Step 8** — the chain, verified

> *"The model never writes, and the writer never reasons. Everything between
> those two facts is evidence, policy and supervision."*

### 4 · Dual control — ~1 min

```bash
reap demo run --scenario critical-defect
```

> *"Two distinct principals. One person clicking twice does not satisfy it, and
> there is a test that asserts exactly that."*

### 5 · The gate — ~1 min

```bash
make eval
reap ready
```

> *"This is the check that would block the release. And this is the same
> repository failing its own readiness gate — because it has no
> authentication and no durable approval store. A framework whose author's
> code passes trivially would be worth nothing."*

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
No, and `IMPLEMENTATION_STATUS.md` lists exactly why. No authentication, no
durable approval store, no deployed environment, no real connector.

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
model call per decision and buys nothing. ADR-0002 states when the answer flips.

**"Has any of this been deployed?"**
No. Fifteen Bicep templates compile; not one resource exists.
