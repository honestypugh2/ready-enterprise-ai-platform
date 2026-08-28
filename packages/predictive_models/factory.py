"""Selects a forecaster from configuration.

The same substitution rule as every other plane: swapping a baseline for a
managed AML endpoint changes one configuration value and nothing else. The
default is a baseline, on purpose — a platform should be able to run and be
evaluated before anyone has trained anything.
"""

from __future__ import annotations

from typing import Any

from platform_config.settings import PlatformSettings
from predictive_models.aml import AzureMLForecaster
from predictive_models.base import Forecaster
from predictive_models.baseline import MovingAverageForecaster, SeasonalNaiveForecaster

__all__ = ["build_forecaster"]


def build_forecaster(
    settings: PlatformSettings,
    credential: Any | None = None,
) -> Forecaster:
    config = settings.predictive

    if config.provider == "seasonal_naive":
        return SeasonalNaiveForecaster()

    if config.provider == "moving_average":
        return MovingAverageForecaster(window=config.window)

    if config.provider == "aml":
        if not config.aml_endpoint_url:
            raise ValueError("predictive provider 'aml' requires REAP_PREDICTIVE_AML_ENDPOINT_URL")
        return AzureMLForecaster(
            scoring_uri=config.aml_endpoint_url,
            deployment_name=config.aml_deployment_name,
            timeout_ms=config.timeout_ms,
            max_attempts=config.max_attempts,
            credential=credential,
        )

    raise ValueError(f"unknown predictive provider '{config.provider}'")
