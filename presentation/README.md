# Beyond the Agent — the deck

A 25-minute technical session. Fifteen slides, five live moments, six appendix
slides that are never presented.

Everything runs offline after `npm install`. A deck that depends on a conference
network is a deck that fails on stage, for the same reason the demo in
[../docs/demo/runbook.md](../docs/demo/runbook.md) does not touch Azure.

## Run it

```bash
cd presentation
npm install
npm run dev          # http://localhost:5180
```

| Key | What it does |
|---|---|
| `S` | Speaker view — notes, timing marks, next slide, clock |
| `ESC` | Slide grid, for jumping to an appendix slide during Q&A |
| `F` | Full screen |
| `B` | Blackout, when you want the room looking at you |

## Export a PDF leave-behind

```
http://localhost:5180/?print-pdf
```

Then print to PDF from the browser: A4/Letter **landscape**, margins **none**,
background graphics **on**. Fragments flatten to one slide per section, which is
what a leave-behind wants.

## Present from a file, with no dev server

```bash
npm run build        # → presentation/dist/
```

`dist/index.html` opens directly from disk. Copy the folder to a USB stick and
it still works.

## Running order

The talk is a claim, then the thing running. Five live moments, in order:

| Time | Slide | Live |
|---|---|---|
| 0:00 | Title | |
| 0:30 | Cold open | `reap demo run --scenario critical-defect` |
| 3:00 | An agent is a runtime | |
| 4:30 | The chain — the map | |
| 6:30 | The constraint chooses the component | |
| 8:30 | Two identities, one index | `reap demo run --scenario restricted-classification` |
| 10:30 | Grounding is a data product | |
| 11:30 | The verdict | policy step, from the live run |
| 14:00 | Six refusals, in order | |
| 15:30 | A chain, not a log | audit step, from the live run |
| 17:00 | The gate | `make eval` |
| 19:00 | READY AI | |
| 20:30 | **This repository, failing its own gate** | `reap ready` |
| 22:30 | Close | |

Slide 3 is the captured `critical-defect` run. It exists so that a terminal
failure costs you a sentence rather than the talk — press right and narrate the
artifact instead. Never debug on stage.

## Rules this deck keeps

The same ones the repository keeps, because a deck that overclaims is a
repository that gets audited.

- **Every number came from this machine.** 8 rules, 3 guards, 16 evaluation
  cases, 7 blocking graders, 42.5 overall — all produced by `make check`,
  `make eval` and `reap ready`. No benchmark, latency, accuracy or cost figure
  appears anywhere.
- **Terminal frames are captured output**, labelled with the date and the
  execution mode. They are not mock-ups of output.
- **The mock says it is a mock**, on screen, in the appendix, and out loud.
- **READY AI is labelled an original field framework**, not a Microsoft
  standard, every time it appears.
- **No prices.** The cost ledger refuses to emit a currency figure without a
  supplied rate card, so the deck does not either.

If a slide gains a claim, it needs a component and a test behind it — see
[../docs/presentation-mapping/README.md](../docs/presentation-mapping/README.md),
which maps every message in this talk to the code that implements it and the
test that enforces it.

## Refreshing the captured output

The terminal frames in `index.html` are pasted from real runs. When the demo
output changes, re-capture rather than editing by hand:

```bash
source ../.venv/bin/activate
reap demo run --scenario critical-defect
reap ready
```
