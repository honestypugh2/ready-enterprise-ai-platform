"""Contracts and protocol for the predictive (forecasting) plane.

A forecast is a *signal about the future*, and it is the most dangerous kind of
model output to put in front of a business process, because a point estimate
reads as a fact. Every forecast this plane emits therefore carries an interval,
a baseline it was measured against, and an explicit horizon — so a consumer
that wants to act on it has to look at the uncertainty to get at the number.

As everywhere else on this platform, a forecast is an input to policy. It is
never a decision.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, Self, runtime_checkable

from pydantic import Field, model_validator

from contracts.common import (
    ExecutionLocation,
    LatencyBudget,
    PlatformModel,
    Provenance,
    new_id,
    utcnow,
)
from contracts.errors import UpstreamUnavailableError


class ForecastUnavailableError(UpstreamUnavailableError):
    """The forecaster could not produce a usable series.

    Distinct from "the forecast is bad": a degraded forecast is returned with
    ``degraded=True`` so the caller can decide. This is raised only when there
    is nothing to return.
    """

    plane = "predictive"

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = True,
        correlation_id: str | None = None,
    ) -> None:
        super().__init__(message, correlation_id=correlation_id)
        # Per-instance override of the class-level contract: a malformed
        # response is permanent, a transport blip is not.
        self.retryable = retryable


class ObservedPoint(PlatformModel):
    """One historical observation feeding a forecast."""

    at: datetime
    value: float


class ForecastRequest(PlatformModel):
    """Ask for a forward view of one series.

    ``series_id`` is the unit of accountability. Forecast quality is tracked
    per series, because an aggregate MAPE hides the one line that is wrong.
    """

    request_id: str = Field(default_factory=lambda: new_id("fc"))
    correlation_id: str
    series_id: str = Field(min_length=1, max_length=128)
    metric: str = Field(min_length=1, max_length=64)
    history: tuple[ObservedPoint, ...]
    horizon: int = Field(ge=1, le=365)
    season_length: int = Field(default=7, ge=1, le=365)
    budget: LatencyBudget = LatencyBudget(target_ms=250, timeout_ms=5_000)

    @model_validator(mode="after")
    def _validate_history(self) -> Self:
        if len(self.history) < 2:
            raise ValueError("a forecast needs at least two observations")
        times = [point.at for point in self.history]
        if times != sorted(times):
            raise ValueError("history must be in ascending time order")
        return self


class ForecastPoint(PlatformModel):
    """A predicted value and the interval it actually lives in."""

    at: datetime
    value: float
    lower: float
    upper: float

    @model_validator(mode="after")
    def _validate_interval(self) -> Self:
        if not self.lower <= self.value <= self.upper:
            raise ValueError("forecast value must fall inside its own interval")
        return self

    @property
    def interval_width(self) -> float:
        return self.upper - self.lower


class Forecast(PlatformModel):
    """The auditable record of one forecast run.

    ``baseline_skill`` is the field that keeps this plane honest. It is the
    improvement over the seasonal-naive baseline on held-out history. A model
    with skill at or below zero is not adding information, and the release gate
    in ``packages/evaluation`` is where that stops being an opinion.
    """

    forecast_id: str = Field(default_factory=lambda: new_id("fcr"))
    request_id: str
    correlation_id: str
    series_id: str
    metric: str

    model_name: str = Field(min_length=1, max_length=128)
    model_version: str = Field(min_length=1, max_length=64)

    points: tuple[ForecastPoint, ...]
    interval_confidence: float = Field(default=0.80, gt=0.0, lt=1.0)
    baseline_name: str = "seasonal_naive"
    baseline_skill: float | None = None

    latency_ms: float = Field(ge=0.0)
    execution_location: ExecutionLocation
    generated_at: datetime = Field(default_factory=utcnow)
    provenance: Provenance
    degraded: bool = False
    degraded_reason: str | None = None

    @model_validator(mode="after")
    def _validate_points(self) -> Self:
        if not self.points:
            raise ValueError("a forecast must contain at least one point")
        if self.degraded and not self.degraded_reason:
            raise ValueError("a degraded forecast must say why")
        return self

    @property
    def adds_information(self) -> bool:
        """False when the model failed to beat the naive baseline.

        Unknown skill counts as False. A forecast that has never been measured
        against a baseline has not earned the benefit of the doubt.
        """
        return self.baseline_skill is not None and self.baseline_skill > 0.0


@runtime_checkable
class Forecaster(Protocol):
    """One protocol, several implementations, chosen by configuration."""

    model_name: str
    model_version: str

    async def healthy(self) -> bool: ...

    async def forecast(self, request: ForecastRequest) -> Forecast: ...


__all__ = [
    "Forecast",
    "ForecastPoint",
    "ForecastRequest",
    "ForecastUnavailableError",
    "Forecaster",
    "ObservedPoint",
]
