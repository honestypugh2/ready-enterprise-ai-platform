# 0018 — Packages install as top-level modules

**Status:** Accepted

## Context

`packages/` and `apps/` each contain several distributable units. The import
style follows from how they are installed, and the choice is between
`from contracts.detection import ...` and `from reap.contracts.detection import
...`.

A namespace package would avoid any chance of a name collision on PyPI. It also
puts a prefix on every import in the repository, which is noise in a codebase
whose imports are the architecture.

## Decision

Each directory under `packages/` and `apps/` installs as a **top-level module**,
listed explicitly in `[tool.hatch.build.targets.wheel]`.

This repository is not published to PyPI. Collisions are therefore confined to
a virtual environment the developer controls, and the names were reviewed
against installed distributions: `contracts`, `detector`, `approvals`,
`connectors`, `audit`, `evaluation`, `retrieval`, `reasoning`, `security`,
`events`, `observability`, `workflows`, `cli`, `api`, `worker`.

`platform_config` is named that way because `platform` is a standard-library
module. `security` and `cli` are the closest calls; both are local packages
that shadow nothing imported by a dependency here.

## Consequences

- Imports read as the architecture: `from policy_engine import PolicyEngine`.
- The plane-boundary test can analyse the import graph with a flat module namespace, which keeps that test simple enough to be trusted.
- **`security` and `cli` are generic names.** If this were ever published, both would need renaming — which is a breaking change to every import.
- Adding a package means three edits: the directory, `pyproject.toml`, and `ALLOWED_DEPENDENCIES` in the boundary test. `CONTRIBUTING.md` lists them.

## What would change this

Publishing to PyPI. At that point the whole tree moves under one namespace and
every import changes, which is exactly the migration this decision defers.
