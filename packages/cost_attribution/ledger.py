"""Consumption ledger for one governed transaction."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import StrEnum

from contracts.common import CostCategory

# The surfaces a single governed transaction can touch. Naming them all is the
# point: tokens are one meter on a machine with many.
CONSUMPTION_SURFACES: tuple[str, ...] = (
    "governed_data",  # Fabric / OneLake capacity, pipelines
    "specialized_model",  # AML training and managed inference
    "compute",  # CPU/GPU for application and inference hosting
    "storage",  # evidence, audit, model inputs
    "event_processing",  # Service Bus / Event Grid
    "search",  # AI Search queries, indexing, embeddings
    "foundation_model",  # Foundry / Azure OpenAI inference
    "agent_runtime",  # Agent Service hosting
    "gateway",  # API Management traffic and policy
    "monitoring",  # Monitor, Log Analytics ingestion
    "evaluation",  # offline and online grading
    "application_hosting",  # Container Apps
    "enterprise_integration",  # ERP / ITSM adapters
)


class ValueBasis(StrEnum):
    """How a figure was arrived at. Always displayed next to the figure.

    The distinction between these four is the difference between a defensible
    unit-economics conversation and an invented one.
    """

    METERED = "metered"  # read from an actual billing meter
    RATE_CARD_ESTIMATE = "rate_card_estimate"  # units x customer-supplied rate
    DEMONSTRATION = "demonstration"  # measured locally in this process
    PLACEHOLDER = "placeholder"  # no value available; awaiting input


@dataclass(frozen=True, slots=True)
class CostEntry:
    surface: str
    component: str
    category: CostCategory
    units: float = 1.0
    input_tokens: int | None = None
    output_tokens: int | None = None
    basis: ValueBasis = ValueBasis.DEMONSTRATION


@dataclass(frozen=True, slots=True)
class RateCard:
    """Customer-supplied rates. Absent by default, and absent means no currency.

    Keys are ``CONSUMPTION_SURFACES`` entries; values are cost per unit in the
    customer's own currency. Nothing in this repository ships a populated rate
    card, because a figure quoted without a source damages everything else in
    the argument.
    """

    currency: str = "UNSPECIFIED"
    per_unit: dict[str, float] = field(default_factory=dict)
    per_1k_input_tokens: float | None = None
    per_1k_output_tokens: float | None = None

    @property
    def is_populated(self) -> bool:
        return bool(self.per_unit) or self.per_1k_input_tokens is not None


@dataclass(frozen=True, slots=True)
class CostSummary:
    """What can honestly be said about the cost of one completed task."""

    correlation_id: str
    entries: tuple[CostEntry, ...]
    units_by_surface: dict[str, float]
    category_by_surface: dict[str, CostCategory]
    total_input_tokens: int
    total_output_tokens: int
    frontier_calls_avoided: int
    basis: ValueBasis
    currency: str
    estimated_total: float | None
    task_completed: bool

    @property
    def cost_per_completed_task(self) -> float | None:
        """Only meaningful when the task completed and a rate card was supplied."""
        if not self.task_completed or self.estimated_total is None:
            return None
        return self.estimated_total

    def as_dict(self) -> dict[str, object]:
        return {
            "correlation_id": self.correlation_id,
            "basis": self.basis.value,
            "currency": self.currency,
            "estimated_total": self.estimated_total,
            "cost_per_completed_task": self.cost_per_completed_task,
            "units_by_surface": self.units_by_surface,
            "category_by_surface": {k: v.value for k, v in self.category_by_surface.items()},
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "frontier_calls_avoided": self.frontier_calls_avoided,
            "task_completed": self.task_completed,
            "note": (
                "Units are measured. Currency is present only when a rate card was "
                "supplied by configuration; this repository ships none."
            ),
        }


class CostLedger:
    """Accumulates consumption for one correlation id."""

    def __init__(self, *, correlation_id: str) -> None:
        self._correlation_id = correlation_id
        self._entries: list[CostEntry] = []
        self._frontier_avoided = 0

    def record(
        self,
        surface: str,
        component: str,
        category: CostCategory,
        *,
        units: float = 1.0,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        basis: ValueBasis = ValueBasis.DEMONSTRATION,
    ) -> None:
        if surface not in CONSUMPTION_SURFACES:
            raise ValueError(f"unknown consumption surface: {surface}")
        self._entries.append(
            CostEntry(
                surface=surface,
                component=component,
                category=category,
                units=units,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                basis=basis,
            )
        )

    def record_frontier_avoided(self) -> None:
        """A request that routing kept off a frontier model.

        Counted rather than priced: the saving is only real against a rate card,
        but the count is a fact about the routing policy either way.
        """
        self._frontier_avoided += 1

    def summarise(self, *, rate_card: RateCard | None = None, task_completed: bool) -> CostSummary:
        units: dict[str, float] = defaultdict(float)
        categories: dict[str, CostCategory] = {}
        input_tokens = 0
        output_tokens = 0

        for entry in self._entries:
            units[entry.surface] += entry.units
            existing = categories.get(entry.surface)
            if existing is None or _rank(entry.category) > _rank(existing):
                categories[entry.surface] = entry.category
            input_tokens += entry.input_tokens or 0
            output_tokens += entry.output_tokens or 0

        estimated: float | None = None
        basis = ValueBasis.PLACEHOLDER
        currency = "UNSPECIFIED"

        if rate_card and rate_card.is_populated:
            currency = rate_card.currency
            basis = ValueBasis.RATE_CARD_ESTIMATE
            estimated = sum(
                rate_card.per_unit.get(surface, 0.0) * amount for surface, amount in units.items()
            )
            if rate_card.per_1k_input_tokens is not None:
                estimated += (input_tokens / 1000.0) * rate_card.per_1k_input_tokens
            if rate_card.per_1k_output_tokens is not None:
                estimated += (output_tokens / 1000.0) * rate_card.per_1k_output_tokens

        return CostSummary(
            correlation_id=self._correlation_id,
            entries=tuple(self._entries),
            units_by_surface=dict(units),
            category_by_surface=categories,
            total_input_tokens=input_tokens,
            total_output_tokens=output_tokens,
            frontier_calls_avoided=self._frontier_avoided,
            basis=basis,
            currency=currency,
            estimated_total=estimated,
            task_completed=task_completed,
        )


def _rank(category: CostCategory) -> int:
    return {
        CostCategory.NONE: 0,
        CostCategory.NEGLIGIBLE: 1,
        CostCategory.LOW: 2,
        CostCategory.MEDIUM: 3,
        CostCategory.HIGH: 4,
    }[category]
