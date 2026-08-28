"""Baseline forecasters.

These are not filler. Seasonal-naive is the reference every production
forecasting model is measured against, and in a surprising number of real
programmes it is never beaten. Shipping it as a first-class implementation
means the comparison is always available and never optional.

Both implementations are pure, deterministic and dependency-free, so the demo
and the tests behave identically on any machine.
"""

from __future__ import annotations

import statistics
import time
from datetime import timedelta

from contracts.common import ExecutionLocation, Provenance, utcnow
from predictive_models.base import (
    Forecast,
    ForecastPoint,
    ForecastRequest,
    ForecastUnavailableError,
)
from predictive_models.metrics import mae, skill_score

# 80% interval under a normal approximation. Stated here rather than inlined
# because the assumption is the thing a reviewer should challenge.
_Z_80 = 1.2816
_INTERVAL_CONFIDENCE = 0.80


def _step(request: ForecastRequest) -> timedelta:
    """Infer the sampling interval from the two most recent observations."""
    delta = request.history[-1].at - request.history[-2].at
    if delta <= timedelta(0):
        raise ForecastUnavailableError(
            "history has a non-positive sampling interval", retryable=False
        )
    return delta


def _residual_sigma(errors: list[float]) -> float:
    if len(errors) < 2:
        return 0.0
    return statistics.pstdev(errors)


def _assemble(
    request: ForecastRequest,
    values: list[float],
    sigma: float,
    *,
    model_name: str,
    model_version: str,
    started: float,
    baseline_skill: float | None,
    baseline_name: str,
) -> Forecast:
    step = _step(request)
    last_at = request.history[-1].at
    points = tuple(
        ForecastPoint(
            at=last_at + step * (index + 1),
            value=value,
            # The interval widens with the square root of the horizon:
            # uncertainty compounds, and a flat band would understate it.
            lower=value - _Z_80 * sigma * ((index + 1) ** 0.5),
            upper=value + _Z_80 * sigma * ((index + 1) ** 0.5),
        )
        for index, value in enumerate(values)
    )
    return Forecast(
        request_id=request.request_id,
        correlation_id=request.correlation_id,
        series_id=request.series_id,
        metric=request.metric,
        model_name=model_name,
        model_version=model_version,
        points=points,
        interval_confidence=_INTERVAL_CONFIDENCE,
        baseline_name=baseline_name,
        baseline_skill=baseline_skill,
        latency_ms=(time.perf_counter() - started) * 1000.0,
        execution_location=ExecutionLocation.LOCAL_PROCESS,
        generated_at=utcnow(),
        provenance=Provenance(
            producer=model_name,
            producer_version=model_version,
            execution_location=ExecutionLocation.LOCAL_PROCESS,
            notes=f"deterministic baseline; season_length={request.season_length}",
        ),
    )


class SeasonalNaiveForecaster:
    """Repeat the value observed one season ago.

    The baseline of record. When the history is shorter than one season it
    falls back to the last observed value and marks the forecast degraded,
    rather than quietly producing a season it does not have the data for.
    """

    model_name = "seasonal-naive"
    model_version = "1.0.0"

    async def healthy(self) -> bool:
        return True

    async def forecast(self, request: ForecastRequest) -> Forecast:
        started = time.perf_counter()
        values = [point.value for point in request.history]
        season = request.season_length
        degraded_reason: str | None = None

        if len(values) <= season:
            degraded_reason = (
                f"history of {len(values)} points is shorter than the "
                f"season length of {season}; falling back to last-value carry-forward"
            )
            season = 1

        predicted = [values[-season + (index % season)] for index in range(request.horizon)]
        errors = [
            abs(values[index] - values[index - season]) for index in range(season, len(values))
        ]
        forecast = _assemble(
            request,
            predicted,
            _residual_sigma(errors),
            model_name=self.model_name,
            model_version=self.model_version,
            started=started,
            # The baseline cannot have skill against itself. Reporting 0.0
            # rather than None states that plainly.
            baseline_skill=0.0,
            baseline_name="self",
        )
        if degraded_reason is None:
            return forecast
        return forecast.model_copy(update={"degraded": True, "degraded_reason": degraded_reason})


class MovingAverageForecaster:
    """Flat forecast at the mean of a trailing window.

    Included because it is the model people reach for first, and because it
    demonstrates the skill comparison producing a negative number on a seasonal
    series — which is the behaviour the plane exists to make visible.
    """

    model_name = "moving-average"
    model_version = "1.0.0"

    def __init__(self, *, window: int = 7) -> None:
        if window < 1:
            raise ValueError("window must be at least 1")
        self._window = window

    async def healthy(self) -> bool:
        return True

    async def forecast(self, request: ForecastRequest) -> Forecast:
        started = time.perf_counter()
        values = [point.value for point in request.history]
        window = min(self._window, len(values))
        level = statistics.fmean(values[-window:])
        predicted = [level] * request.horizon

        errors = [abs(value - level) for value in values[-window:]]
        skill = self._backtest_skill(values, request.season_length, window)
        return _assemble(
            request,
            predicted,
            _residual_sigma(errors),
            model_name=self.model_name,
            model_version=self.model_version,
            started=started,
            baseline_skill=skill,
            baseline_name="seasonal_naive",
        )

    @staticmethod
    def _backtest_skill(values: list[float], season: int, window: int) -> float | None:
        """One-step-ahead backtest against seasonal-naive on held-out history.

        Returns ``None`` when there is not enough history to make the
        comparison. An unmeasurable model reports that it is unmeasured; it
        does not report zero.
        """
        start = max(season, window)
        if len(values) <= start + 1:
            return None
        actual = values[start:]
        model = [
            statistics.fmean(values[index - window : index]) for index in range(start, len(values))
        ]
        baseline = [values[index - season] for index in range(start, len(values))]
        if mae(actual, baseline) == 0.0:
            return 0.0
        return skill_score(actual, model, baseline)


__all__ = ["MovingAverageForecaster", "SeasonalNaiveForecaster"]
