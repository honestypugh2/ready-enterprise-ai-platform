# 0008 — Entitlements are applied before scoring, not after ranking

**Status:** Accepted

## Context

The convenient place to filter retrieved documents is after ranking: search,
then drop what the caller may not see. It is also wrong in two ways. A
restricted document consumes a top-k slot, so an entitled caller silently gets
fewer results. And the *existence* of a document leaks through score
distributions and result counts.

## Decision

`RetrievalQuery.entitlement_groups` is a **required** field — a retriever that
can be called without entitlements will eventually be called without them.
Empty entitlements means entitled to nothing, never entitled to everything.

Trimming happens before scoring. `RetrievalResult.trimmed_count` reports how
many documents were removed, so the caller can tell "nothing matched" from
"nothing you may see matched".

A test asks for `top_k=1` and requires one real result, which fails if
filtering ever moves after ranking.

## Consequences

- Two identities get different, correct answers from one index — demonstrated in `tests/security/test_authorization.py`.
- Classification is a second, independent axis: being in the group is not sufficient.
- Retrieved content is treated as untrusted input, sanitised and wrapped with a non-forgeable delimiter.
- **Trimming before scoring costs performance** at scale: the filter cannot be pushed into the search service's own top-k. Azure AI Search security filters are the production answer, and the local retriever's approach does not transfer unchanged.
- The local "vector" component is **hashed character trigrams, not a semantic embedding model**. It exercises the hybrid merge path deterministically and makes no relevance claim.

## What would change this

Nothing about the ordering. The implementation should move to index-side
security filters in production, but the property — a document the caller may
not see is never ranked — must survive that change.
