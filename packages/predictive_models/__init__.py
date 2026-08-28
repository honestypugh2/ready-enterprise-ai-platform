"""Predictive plane — forward-looking numeric signals.

Distinct from the detector plane, which classifies what *is*, this plane
estimates what *will be*: station defect rates, consumable burn-down, time to
maintenance. Enterprise AI programmes almost always need both, and conflating
them is how a forecast ends up being treated as an observation.

Three rules hold here, and each is enforced rather than described:

* A forecast always carries an interval. ``ForecastPoint`` will not validate
  without one, and the AML adapter refuses a response that omits bounds.
* A forecast declares its skill against a baseline. ``Forecast.adds_information``
  is False for any model that has not beaten seasonal-naive, and False for any
  model that has never been measured.
* A forecast is an input to policy, never a decision. Nothing in this package
  can write, approve, or dispose.
"""

from predictive_models.aml import AzureMLForecaster
from predictive_models.base import (
    Forecast,
    Forecaster,
    ForecastPoint,
    ForecastRequest,
    ForecastUnavailableError,
    ObservedPoint,
)
from predictive_models.baseline import MovingAverageForecaster, SeasonalNaiveForecaster
from predictive_models.factory import build_forecaster
from predictive_models.metrics import mae, mape, rmse, skill_score, smape

__all__ = [
    "AzureMLForecaster",
    "Forecast",
    "ForecastPoint",
    "ForecastRequest",
    "ForecastUnavailableError",
    "Forecaster",
    "MovingAverageForecaster",
    "ObservedPoint",
    "SeasonalNaiveForecaster",
    "build_forecaster",
    "mae",
    "mape",
    "rmse",
    "skill_score",
    "smape",
]
