# 0015 — Bicep first, Terraform not at parity

**Status:** Accepted

## Context

Enterprise customers are split between Bicep and Terraform. Maintaining both at
parity doubles the work and, in practice, produces one that is tested and one
that has drifted.

## Decision

Bicep, subscription-scoped, as the only maintained infrastructure. No Terraform
until someone needs it enough to own it.

Subscription scope because the resource group is part of what is deployed. A
template that assumes the group exists cannot describe the whole environment,
and the group carries the tags that drive cost attribution and residency
reporting.

## Consequences

- Fifteen templates compile clean and `make infra-lint` runs on every change.
- Same-day support for new resource properties, and type checking against real resource schemas.
- Private networking is **derived** rather than requested — `environment == 'prod' || deployPrivateNetworking` — so the broken combination of "public access disabled, no private endpoints" is not reachable through a parameter file.
- **This excludes Terraform-standardised customers.** They get a reference to translate, not a template to run. That is a real limitation and `infra/README.md` states it.
- **Nothing here has been deployed.** Compiling is a much weaker claim than working, and `IMPLEMENTATION_STATUS.md` marks every module accordingly.

## What would change this

A customer engagement that needs Terraform. The right response is a translated
module set with its own validation in CI — not an untested transliteration.
