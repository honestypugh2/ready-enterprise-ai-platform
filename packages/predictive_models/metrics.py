"""Forecast accuracy metrics, including the one that matters.

Absolute error metrics are easy to report and easy to misread: a MAPE of 8%
means nothing until you know what the naive baseline scored. ``skill_score``
is the honest summary, and it is deliberately the last function here so that
nothing can report accuracy without it being available.
"""

from __future__ import annotations

from collections.abc import Sequence

__all__ = ["mae", "mape", "rmse", "skill_score", "smape"]


def _check(actual: Sequence[float], predicted: Sequence[float]) -> None:
    if len(actual) != len(predicted):
        raise ValueError("actual and predicted must be the same length")
    if not actual:
        raise ValueError("cannot score an empty series")


def mae(actual: Sequence[float], predicted: Sequence[float]) -> float:
    """Mean absolute error, in the units of the series."""
    _check(actual, predicted)
    return sum(abs(a - p) for a, p in zip(actual, predicted, strict=True)) / len(actual)


def rmse(actual: Sequence[float], predicted: Sequence[float]) -> float:
    """Root mean squared error. Penalises large misses harder than MAE."""
    _check(actual, predicted)
    mean_sq = sum((a - p) ** 2 for a, p in zip(actual, predicted, strict=True)) / len(actual)
    return float(mean_sq**0.5)


def mape(actual: Sequence[float], predicted: Sequence[float]) -> float:
    """Mean absolute percentage error, as a fraction.

    Undefined at zero, which is not a rounding problem — a defect-count series
    is zero most of the time. Zero actuals are skipped and, if every actual is
    zero, this raises rather than returning a comfortable number.
    """
    _check(actual, predicted)
    pairs = [(a, p) for a, p in zip(actual, predicted, strict=True) if a != 0.0]
    if not pairs:
        raise ValueError("MAPE is undefined when every actual value is zero; use MAE or sMAPE")
    return sum(abs(a - p) / abs(a) for a, p in pairs) / len(pairs)


def smape(actual: Sequence[float], predicted: Sequence[float]) -> float:
    """Symmetric MAPE, as a fraction in [0, 1].

    Defined at zero, which is why it is preferred here over MAPE for sparse
    count series. Terms where both actual and predicted are zero contribute
    zero error rather than being dropped.
    """
    _check(actual, predicted)
    total = 0.0
    for a, p in zip(actual, predicted, strict=True):
        denominator = (abs(a) + abs(p)) / 2.0
        total += 0.0 if denominator == 0.0 else abs(a - p) / denominator / 2.0
    return total / len(actual)


def skill_score(
    actual: Sequence[float],
    predicted: Sequence[float],
    baseline: Sequence[float],
) -> float:
    """Fractional improvement in MAE over a baseline forecast.

    ``1.0`` is perfect, ``0.0`` is exactly as good as the baseline, and a
    negative value means the model is worse than doing nothing clever. This is
    the number that belongs in a review, not the raw error.
    """
    _check(actual, predicted)
    _check(actual, baseline)
    baseline_error = mae(actual, baseline)
    if baseline_error == 0.0:
        # A perfect baseline cannot be improved on. Report parity rather than
        # dividing by zero or flattering the model.
        return 0.0
    return 1.0 - (mae(actual, predicted) / baseline_error)
