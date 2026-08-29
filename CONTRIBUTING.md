# Contributing

## Setup

```bash
make install          # uv venv + dependencies
source .venv/bin/activate
make check            # lint, strict types, unit + contract + security suites
make demo             # one governed transaction, end to end
```

No Azure subscription, credential or network access is required. If a clean
clone cannot do this, that is a bug worth reporting.

## The one rule

**Every claim this repository makes must be enforced by something that fails
the build when it stops being true.**

The README says the reasoning plane cannot write. That is not a comment — it is
`tests/contract/test_plane_boundaries.py` reading the import graph and failing
if `reasoning` ever imports `connectors`. If you add a claim, add the test that
would catch its violation. If you cannot write that test, weaken the claim.

## Before opening a pull request

```bash
make check            # must pass
make eval             # must pass, or justify the threshold change
make secrets          # must pass
make infra-lint       # if you touched infra/
```

Update [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) if your change moves
a capability on either axis — what exists (Implemented / Partial / Mocked /
Adapter only / Absent) or what has been proven (⬤ Proven / ◑ Tested / ◔ Checked
/ ○ Written).

The two are separated because one column was hiding the difference between a
plane covered by ninety-odd tests and a Bicep template that had only ever been
parsed. **Only claim ⬤ Proven for something you ran against the real dependency
and observed the result of.** A passing test against a mock is ◑ Tested, and
that is a claim about the governance path, not about the mocked component.

A status document that drifts is worse than none, because people trust it.

## Honesty constraints

These are not style preferences. They are why the repository is credible.

- **No fabricated numbers.** No benchmark, latency, accuracy, cost or customer
  outcome that was not measured. Where a figure appears, say what produced it.
- **Name the mock.** A fixture must say it is a fixture, in the docstring, in
  the API response and on the screen. The demo UI labels every figure as either
  a fixture or a measurement.
- **Units, not prices.** The cost ledger records tokens and calls. It refuses to
  produce a currency figure without a supplied rate card, because the repository
  does not know anyone's negotiated rates.
- **Preview features are labelled** with what breaks if the preview changes.
- **READY AI is an original field framework**, not a Microsoft standard. It must
  be described that way every time it appears.

## Code conventions

- Python 3.12, `ruff format`, line length 100, `mypy --strict`.
- Contracts are frozen with `extra="forbid"`. A contract that silently accepts
  an unknown field is a contract that lets a caller ship a bug it cannot see.
- Planes depend on `contracts` and nothing else. Shared vocabulary belongs in
  `contracts`, not inside whichever plane happened to define it first.
- Comments state what the code cannot. Prefer one line explaining *why* over a
  paragraph restating *what*.
- Tests are named as sentences that state the property, not the method under
  test: `test_the_requester_cannot_approve_their_own_proposal`.

## Adding a policy rule

`packages/policy_engine/policies/manufacturing.yaml` is evaluated
**first-match-wins**, and rule ids must be in ascending order — a test enforces
it. That test exists because a rule was once added below a broader rule and was
therefore unreachable: dead governance that looked live in review.

Bump the policy version. Every decision records the version and the file hash,
so a changed policy that keeps its version makes past decisions unexplainable.

## Adding a plane

1. Create `packages/<plane>/` with an `__init__.py` that declares `__all__`.
2. Add it to `PLANES` and `ALLOWED_DEPENDENCIES` in
   `tests/contract/test_plane_boundaries.py`, declaring what it may import.
3. Add it to `[tool.hatch.build.targets.wheel]` in `pyproject.toml`.
4. Wire it in `packages/workflows/assembly.py` — the single composition root.

If the boundary test fails, the fix is a boundary change you can defend in
review, not an exemption.

## What will be declined

- A change that adds an exemption to a contract test rather than fixing the
  violation.
- A performance or accuracy claim with no measurement behind it.
- A convenience path that lets a component write without an approval, "just for
  the demo".
- Removing a labelled limitation instead of resolving it.

## License

Contributions are accepted under the [MIT License](LICENSE).
