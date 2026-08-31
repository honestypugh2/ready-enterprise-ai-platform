# AGENTS.md

Instructions for AI coding agents working in this repository. Humans should read
[CONTRIBUTING.md](CONTRIBUTING.md), which covers the same ground with more
context.

## What this repository is

A reference implementation of the governance architecture around AI components.
Its credibility rests entirely on one property:

**Every claim it makes is enforced by something that fails the build when the
claim stops being true.**

The README says the reasoning plane cannot write. That is not a comment — it is
`tests/contract/test_plane_boundaries.py` parsing the import graph and failing
if `reasoning` ever imports `connectors`.

If you add a claim, add the test that would catch its violation. If you cannot
write that test, weaken the claim.

## Setup

```bash
source .venv/bin/activate    # always, before any uv command
make check                   # lint, mypy --strict, unit + contract + security
```

`uv` owns Python dependencies. Never call `pip` directly and never install into
a system interpreter.

## Before you finish

```bash
make check          # must pass
make eval           # must pass, or justify the threshold change
make secrets        # must pass
make infra-lint     # if you touched infra/
cd apps/web && npm run lint && npm run typecheck && npm run test   # if you touched the UI
```

## Hard constraints

These are not preferences. Violating one makes the repository dishonest.

1. **No fabricated numbers.** No benchmark, latency, accuracy, cost or customer
   outcome that was not measured on this machine. If you need an example figure,
   say what produced it.
2. **No prices, anywhere.** The cost ledger refuses to emit a currency figure
   without a supplied rate card. Keep it that way.
3. **Name the mock.** A fixture must say it is a fixture — in the docstring, in
   the API response, and on screen.
4. **READY AI is an original field framework**, not a Microsoft standard,
   product or official guidance. Label it every time.
5. **Local mock mode stays the enforced default.** The settings validator must
   keep refusing a cloud provider and `dry_run=false` in local mode.
6. **Do not reference `foundry-copilot-search-validate`.**
7. **Update `IMPLEMENTATION_STATUS.md`** whenever a capability changes on either
   axis — what exists (Implemented / Partial / Mocked / Adapter only / Absent)
   or what has been proven (⬤ Proven / ◑ Tested / ◔ Checked / ○ Written).
   **Only claim ⬤ Proven for something you ran against the real dependency and
   observed.** A passing test is ◑ Tested. A template that compiles is ◔
   Checked. A status document that drifts is worse than none, because people
   trust it.

## Architecture rules

- Planes depend on `contracts` and nothing else. Shared vocabulary belongs in
  `contracts`, not inside whichever plane defined it first.
- `packages/workflows/assembly.py` is the single composition root. Wiring
  scattered across entry points is how one of them ends up without the kill
  switch.
- Contracts are frozen with `extra="forbid"`.
- Only `connectors.writer.ScopedWriter` may call a connector.
- Reasoning has no method through which it could write, approve or decide.

## Adding a plane

1. `packages/<plane>/__init__.py` declaring `__all__`
2. Add to `PLANES` and `ALLOWED_DEPENDENCIES` in
   `tests/contract/test_plane_boundaries.py`
3. Add to `[tool.hatch.build.targets.wheel]` in `pyproject.toml`
4. Wire it in `packages/workflows/assembly.py`

## Adding a policy rule

`packages/policy_engine/policies/manufacturing.yaml` is first-match-wins and
rule ids must be in ascending order — a test enforces it, because a rule was
once added below a broader rule and could never fire. Bump the policy version.

## Style

- Python 3.12, `ruff format`, line length 100, `mypy --strict`.
- Comments state what the code cannot. One line explaining *why* beats a
  paragraph restating *what*. Do not write comments addressed to a reviewer.
- Test names are sentences stating the property:
  `test_the_requester_cannot_approve_their_own_proposal`.
- Do not create markdown files documenting your changes.

## What will be rejected

- Adding an exemption to a contract test instead of fixing the violation
- A performance or accuracy claim with no measurement
- A convenience path that lets a component write without an approval
- Removing a labelled limitation instead of resolving it
- Weakening the local-mock enforcement to make something easier to run

## Where to look

| Question | File |
|---|---|
| What is actually real? | [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) |
| What is the shape? | [docs/architecture/overview.md](docs/architecture/overview.md) |
| What is still open? | [docs/security/threat-model.md](docs/security/threat-model.md) |
