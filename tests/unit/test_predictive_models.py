"""The predictive plane's job is to be honest about uncertainty and skill.

These tests target the two places a forecasting stack normally goes wrong in
production: intervals that do not widen with horizon, and skill numbers that
flatter the model.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest

from platform_config.settings import PlatformSettings
from predictive_models import (
    Forecast,
    ForecastPoint,
    ForecastRequest,
    MovingAverageForecaster,
    ObservedPoint,
    SeasonalNaiveForecaster,
    build_forecaster,
    mae,
    mape,
    rmse,
    skill_score,
    smape,
)
from predictive_models.base import ForecastUnavailableError

START = datetime(2026, 1, 1, tzinfo=UTC)
# Four clean weeks of a weekly pattern. Seasonal-naive should be perfect on it.
WEEKLY = [3.0, 5.0, 4.0, 6.0, 2.0, 1.0, 1.0]


def series(values: list[float]) -> tuple[ObservedPoint, ...]:
    return tuple(
        ObservedPoint(at=START + timedelta(days=index), value=value)
        for index, value in enumerate(values)
    )


def request_for(values: list[float], *, horizon: int = 7, season: int = 7) -> ForecastRequest:
    return ForecastRequest(
        correlation_id="corr-predictive-test",
        series_id="line-a/station-3",
        metric="defect_count",
        history=series(values),
        horizon=horizon,
        season_length=season,
    )


class TestForecastContract:
    def test_a_point_cannot_sit_outside_its_own_interval(self) -> None:
        with pytest.raises(ValueError, match="inside its own interval"):
            ForecastPoint(at=START, value=10.0, lower=1.0, upper=2.0)

    def test_history_must_be_in_time_order(self) -> None:
        reversed_history = tuple(reversed(series([1.0, 2.0, 3.0])))
        with pytest.raises(ValueError, match="ascending time order"):
            ForecastRequest(
                correlation_id="c",
                series_id="s",
                metric="m",
                history=reversed_history,
                horizon=3,
            )

    def test_two_observations_are_the_minimum(self) -> None:
        with pytest.raises(ValueError, match="at least two observations"):
            ForecastRequest(
                correlation_id="c",
                series_id="s",
                metric="m",
                history=series([1.0]),
                horizon=3,
            )

    def test_a_degraded_forecast_must_say_why(self) -> None:
        with pytest.raises(ValueError, match="must say why"):
            Forecast(
                request_id="r",
                correlation_id="c",
                series_id="s",
                metric="m",
                model_name="x",
                model_version="1",
                points=(ForecastPoint(at=START, value=1.0, lower=0.0, upper=2.0),),
                latency_ms=1.0,
                execution_location="mock",  # type: ignore[arg-type]
                provenance={
                    "producer": "x",
                    "producer_version": "1",
                    "execution_location": "mock",
                },  # type: ignore[arg-type]
                degraded=True,
            )


class TestSeasonalNaive:
    async def test_it_repeats_the_previous_season(self) -> None:
        result = await SeasonalNaiveForecaster().forecast(request_for(WEEKLY * 3))
        assert [point.value for point in result.points] == WEEKLY

    async def test_a_perfect_baseline_has_zero_residual_width(self) -> None:
        """A cleanly periodic series produces no residuals, so the interval is
        a point. That is the correct answer, not a bug — and it is exactly the
        case that would divide by zero in a careless skill calculation."""
        result = await SeasonalNaiveForecaster().forecast(request_for(WEEKLY * 3))
        assert all(point.interval_width == 0.0 for point in result.points)

    async def test_intervals_widen_with_horizon(self) -> None:
        noisy = [value + (index % 3) for index, value in enumerate(WEEKLY * 3)]
        result = await SeasonalNaiveForecaster().forecast(request_for(noisy, horizon=5))
        widths = [point.interval_width for point in result.points]
        assert widths == sorted(widths)
        assert widths[-1] > widths[0]

    async def test_short_history_degrades_rather_than_inventing_a_season(self) -> None:
        result = await SeasonalNaiveForecaster().forecast(request_for([1.0, 2.0, 3.0], horizon=2))
        assert result.degraded
        assert "shorter than the season length" in (result.degraded_reason or "")
        # Last-value carry-forward, not a fabricated weekly cycle.
        assert [point.value for point in result.points] == [3.0, 3.0]

    async def test_the_baseline_claims_no_skill_against_itself(self) -> None:
        result = await SeasonalNaiveForecaster().forecast(request_for(WEEKLY * 3))
        assert result.baseline_skill == 0.0
        assert result.adds_information is False

    async def test_a_non_positive_sampling_interval_is_refused(self) -> None:
        history = (
            ObservedPoint(at=START, value=1.0),
            ObservedPoint(at=START + timedelta(days=1), value=2.0),
            ObservedPoint(at=START + timedelta(days=1), value=3.0),
        )
        request = ForecastRequest(
            correlation_id="c", series_id="s", metric="m", history=history, horizon=2
        )
        with pytest.raises(ForecastUnavailableError, match="non-positive sampling interval"):
            await SeasonalNaiveForecaster().forecast(request)


class TestMovingAverage:
    async def test_it_loses_to_the_baseline_on_a_seasonal_series(self) -> None:
        """The point of reporting skill: a flat mean is measurably worse than
        seasonal-naive here, and the forecast says so instead of just showing
        a respectable-looking error.

        The series carries a little noise on purpose. A perfectly periodic
        series gives the baseline zero error, and skill against a perfect
        baseline is reported as parity rather than as a division by zero.
        """
        noisy = [value + (index % 3) * 0.2 for index, value in enumerate(WEEKLY * 4)]
        result = await MovingAverageForecaster(window=7).forecast(request_for(noisy))
        assert result.baseline_skill is not None
        assert result.baseline_skill < 0.0
        assert result.adds_information is False

    async def test_unmeasurable_skill_is_none_not_zero(self) -> None:
        result = await MovingAverageForecaster(window=7).forecast(request_for(WEEKLY, horizon=3))
        assert result.baseline_skill is None
        assert result.adds_information is False

    async def test_the_forecast_is_flat(self) -> None:
        result = await MovingAverageForecaster(window=7).forecast(request_for(WEEKLY * 3))
        values = {point.value for point in result.points}
        assert len(values) == 1

    def test_a_zero_window_is_rejected_at_construction(self) -> None:
        with pytest.raises(ValueError, match="at least 1"):
            MovingAverageForecaster(window=0)


class TestMetrics:
    def test_mae_and_rmse(self) -> None:
        assert mae([1.0, 2.0], [1.0, 4.0]) == 1.0
        assert rmse([1.0, 2.0], [1.0, 4.0]) == pytest.approx(math.sqrt(2.0))

    def test_mape_refuses_an_all_zero_actual_series(self) -> None:
        """Sparse defect counts are mostly zero. Returning a number here would
        be worse than refusing."""
        with pytest.raises(ValueError, match="undefined when every actual"):
            mape([0.0, 0.0], [1.0, 2.0])

    def test_smape_is_defined_at_zero(self) -> None:
        assert smape([0.0, 0.0], [0.0, 0.0]) == 0.0
        assert 0.0 < smape([0.0, 4.0], [2.0, 4.0]) <= 1.0

    def test_skill_is_zero_at_parity_and_negative_when_worse(self) -> None:
        actual = [1.0, 2.0, 3.0]
        baseline = [1.5, 2.5, 3.5]
        assert skill_score(actual, baseline, baseline) == 0.0
        assert skill_score(actual, [5.0, 5.0, 5.0], baseline) < 0.0

    def test_a_perfect_baseline_reports_parity_not_infinity(self) -> None:
        actual = [1.0, 2.0]
        assert skill_score(actual, [9.0, 9.0], actual) == 0.0

    def test_mismatched_lengths_are_rejected(self) -> None:
        with pytest.raises(ValueError, match="same length"):
            mae([1.0], [1.0, 2.0])


class TestFactory:
    def test_default_is_the_baseline(self, settings: PlatformSettings) -> None:
        assert isinstance(build_forecaster(settings), SeasonalNaiveForecaster)

    def test_aml_without_an_endpoint_is_a_configuration_error(
        self, settings: PlatformSettings
    ) -> None:
        configured = settings.model_copy(
            update={"predictive": settings.predictive.model_copy(update={"provider": "aml"})}
        )
        with pytest.raises(ValueError, match="requires REAP_PREDICTIVE_AML_ENDPOINT_URL"):
            build_forecaster(configured)

    def test_local_mock_mode_cannot_select_a_cloud_forecaster(self) -> None:
        with pytest.raises(ValueError, match="cannot use predictive provider 'aml'"):
            PlatformSettings(predictive={"provider": "aml"})  # type: ignore[arg-type]
