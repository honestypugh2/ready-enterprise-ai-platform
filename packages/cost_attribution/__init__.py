"""Cost attribution plane.

Demonstrates the argument that enterprise AI consumption extends well beyond
frontier-model tokens: a single governed transaction touches a data plane, a
specialized model, search, a gateway, a runtime, integration and monitoring.

**On honesty about money.** This repository does not know a customer's rate card
and will not invent one. The ledger records *cost categories* and *consumption
units*, which are facts about the architecture. Currency appears only when a
rate card is supplied by configuration, and every derived figure is labelled
with its basis so an estimate is never mistaken for a bill.
"""

from cost_attribution.ledger import (
    CONSUMPTION_SURFACES,
    CostEntry,
    CostLedger,
    CostSummary,
    RateCard,
    ValueBasis,
)

__all__ = [
    "CONSUMPTION_SURFACES",
    "CostEntry",
    "CostLedger",
    "CostSummary",
    "RateCard",
    "ValueBasis",
]
