"""Azure Machine Learning adapter for the predictive plane.

Same shape and the same reasoning as ``detector/aml.py``: the endpoint's HTTPS
scoring contract directly, Entra-first authentication, and schema validation of
everything that comes back. A forecasting endpoint is an untrusted boundary in
exactly the way an inference endpoint is.

The one difference that matters: this adapter refuses to return a forecast
whose interval it cannot establish. A point estimate with fabricated bounds is
worse than no forecast, because it looks like a measurement.
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from contracts.common import ExecutionLocation, Provenance, utcnow
from predictive_models.base import (
    Forecast,
    ForecastPoint,
    ForecastRequest,
    ForecastUnavailableError,
)

# Entra token audience for AML data-plane calls, not a credential.
AML_TOKEN_SCOPE = "https://ml.azure.com/.default"  # noqa: S105


class AzureMLForecaster:
    """Calls an AML managed online endpoint that serves a forecasting model."""

    def __init__(
        self,
        *,
        scoring_uri: str,
        model_name: str = "demand-forecaster",
        model_version: str = "unknown",
        deployment_name: str | None = None,
        timeout_ms: int = 5_000,
        max_attempts: int = 2,
        credential: Any | None = None,
        api_key_env: str = "REAP_PREDICTIVE_AML_KEY",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not scoring_uri.startswith("https://"):
            raise ValueError("AML scoring_uri must be https")
        self.scoring_uri = scoring_uri
        self.model_name = model_name
        self.model_version = model_version
        self.deployment_name = deployment_name
        self._timeout_s = timeout_ms / 1000.0
        self._max_attempts = max_attempts
        self._credential = credential
        self._api_key_env = api_key_env
        self._client = client

    async def _auth_header(self) -> str:
        if self._credential is not None:
            token = self._credential.get_token(AML_TOKEN_SCOPE)
            return f"Bearer {token.token}"
        api_key = os.environ.get(self._api_key_env)
        if api_key:
            return f"Bearer {api_key}"
        raise ForecastUnavailableError(
            "no credential supplied and no endpoint key present; "
            "provide a managed identity credential for Entra-based auth",
            retryable=False,
        )

    async def healthy(self) -> bool:
        client = self._client or httpx.AsyncClient(timeout=self._timeout_s)
        try:
            response = await client.get(self.scoring_uri.rsplit("/score", 1)[0] + "/")
        except httpx.HTTPError:
            return False
        else:
            return response.status_code < 500
        finally:
            if self._client is None:
                await client.aclose()

    async def forecast(self, request: ForecastRequest) -> Forecast:
        started = time.perf_counter()
        headers = {
            "Content-Type": "application/json",
            "Authorization": await self._auth_header(),
            "x-ms-client-request-id": request.request_id,
        }
        if self.deployment_name:
            headers["azureml-model-deployment"] = self.deployment_name

        payload = {
            "input_data": {
                "series_id": request.series_id,
                "metric": request.metric,
                "horizon": request.horizon,
                "season_length": request.season_length,
                "history": [
                    {"at": point.at.isoformat(), "value": point.value} for point in request.history
                ],
            }
        }

        client = self._client or httpx.AsyncClient(timeout=self._timeout_s)
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self._max_attempts),
                wait=wait_exponential_jitter(initial=0.1, max=1.0),
                retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
                reraise=True,
            ):
                with attempt:
                    response = await client.post(self.scoring_uri, json=payload, headers=headers)
                    response.raise_for_status()
                    return self._parse(request, response.json(), started)
        except httpx.HTTPError as exc:
            raise ForecastUnavailableError(f"AML forecasting endpoint failed: {exc}") from exc
        finally:
            if self._client is None:
                await client.aclose()
        raise ForecastUnavailableError("AML forecasting endpoint returned no response")

    def _parse(self, request: ForecastRequest, body: Any, started: float) -> Forecast:
        if not isinstance(body, dict):
            raise ForecastUnavailableError("endpoint returned a non-object body", retryable=False)
        raw_points = body.get("forecast")
        if not isinstance(raw_points, list) or not raw_points:
            raise ForecastUnavailableError("endpoint returned no forecast points", retryable=False)

        points: list[ForecastPoint] = []
        for entry in raw_points:
            if not isinstance(entry, dict):
                raise ForecastUnavailableError("malformed forecast point", retryable=False)
            missing = {"at", "value", "lower", "upper"} - entry.keys()
            if missing:
                # Refuse rather than synthesise bounds. See module docstring.
                raise ForecastUnavailableError(
                    f"forecast point is missing required fields: {sorted(missing)}",
                    retryable=False,
                )
            points.append(
                ForecastPoint(
                    at=datetime.fromisoformat(str(entry["at"])),
                    value=float(entry["value"]),
                    lower=float(entry["lower"]),
                    upper=float(entry["upper"]),
                )
            )

        skill = body.get("baseline_skill")
        return Forecast(
            request_id=request.request_id,
            correlation_id=request.correlation_id,
            series_id=request.series_id,
            metric=request.metric,
            model_name=str(body.get("model_name") or self.model_name),
            model_version=str(body.get("model_version") or self.model_version),
            points=tuple(points),
            interval_confidence=float(body.get("interval_confidence", 0.80)),
            baseline_name=str(body.get("baseline_name") or "seasonal_naive"),
            baseline_skill=None if skill is None else float(skill),
            latency_ms=(time.perf_counter() - started) * 1000.0,
            execution_location=ExecutionLocation.AZURE_REGIONAL,
            generated_at=utcnow(),
            provenance=Provenance(
                producer=self.model_name,
                producer_version=self.model_version,
                execution_location=ExecutionLocation.AZURE_REGIONAL,
                notes=(
                    f"AML managed online endpoint; deployment={self.deployment_name or 'default'}"
                ),
            ),
        )


__all__ = ["AML_TOKEN_SCOPE", "AzureMLForecaster"]
