"""Azure Machine Learning managed online endpoint adapter.

Deliberately implemented against the endpoint's HTTPS scoring contract rather
than a high-level SDK helper. Two reasons:

1. The scoring contract (POST to the scoring URI, bearer token, optional
   ``azureml-model-deployment`` header for a named deployment) is stable, while
   SDK convenience surfaces change between releases.
2. It keeps ``azure-ai-ml`` out of the request path entirely, so the adapter has
   the small dependency footprint an inference hop deserves.

Authentication is Entra-first: a managed identity token scoped to
``https://ml.azure.com/.default``. Key-based auth is supported only because
some development endpoints are provisioned that way, and it is never the
default.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from contracts.common import ExecutionLocation
from contracts.detection import DetectionRequest, Prediction
from detector.base import BaseDetector, DetectorUnavailableError

# Entra token audience for AML data-plane calls, not a credential.
AML_TOKEN_SCOPE = "https://ml.azure.com/.default"  # noqa: S105


class AzureMLEndpointDetector(BaseDetector):
    """Calls a managed online endpoint and validates whatever comes back.

    The endpoint is an untrusted boundary like any other: its response is
    schema-checked before a single value reaches the workflow.
    """

    def __init__(
        self,
        *,
        scoring_uri: str,
        model_name: str,
        model_version: str,
        deployment_name: str | None = None,
        decision_threshold: float = 0.62,
        timeout_ms: int = 2_000,
        max_attempts: int = 2,
        credential: Any | None = None,
        api_key_env: str = "REAP_DETECTOR_AML_KEY",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(decision_threshold=decision_threshold)
        if not scoring_uri.startswith("https://"):
            raise ValueError("AML scoring_uri must be https")
        self.scoring_uri = scoring_uri
        self.model_name = model_name
        self.model_version = model_version
        self.deployment_name = deployment_name
        self.execution_location = ExecutionLocation.AZURE_REGIONAL
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
        raise DetectorUnavailableError(
            "no credential supplied and no endpoint key present; "
            "provide a managed identity credential for Entra-based auth"
        )

    async def healthy(self) -> bool:
        client = self._client or httpx.AsyncClient(timeout=self._timeout_s)
        try:
            response = await client.get(self.scoring_uri.rsplit("/score", 1)[0] + "/")
            return response.status_code < 500
        except httpx.HTTPError:
            return False
        finally:
            if self._client is None:
                await client.aclose()

    async def _infer(self, request: DetectionRequest) -> tuple[Prediction, ...]:
        headers = {
            "Content-Type": "application/json",
            "Authorization": await self._auth_header(),
            # Correlates the platform trace with the endpoint's own telemetry.
            "x-ms-client-request-id": request.request_id,
        }
        if self.deployment_name:
            headers["azureml-model-deployment"] = self.deployment_name

        payload = {
            "input_data": {
                "frame_uri": request.frame_uri,
                "frame_hash": request.frame_hash,
                "line_id": request.line_id,
                "station_id": request.station_id,
                "product_sku": request.product_sku,
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
                    return self._parse(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            raise DetectorUnavailableError(
                f"AML endpoint call failed: {type(exc).__name__}",
                correlation_id=request.request_id,
            ) from exc
        finally:
            if self._client is None:
                await client.aclose()
        raise DetectorUnavailableError("AML endpoint exhausted retries")

    def _parse(self, body: Any) -> tuple[Prediction, ...]:
        """Validate the endpoint response. A malformed body is an outage, not a prediction."""
        raw = body.get("predictions") if isinstance(body, dict) else body
        if not isinstance(raw, list) or not raw:
            raise ValueError("AML response did not contain a predictions list")
        parsed: list[Prediction] = []
        for entry in raw:
            if not isinstance(entry, dict):
                raise ValueError("AML prediction entry was not an object")
            box = entry.get("bounding_box")
            parsed.append(
                Prediction(
                    label=str(entry["label"]),
                    confidence=float(entry["confidence"]),
                    threshold=self.decision_threshold,
                    bounding_box=tuple(box) if box else None,
                )
            )
        return tuple(parsed)
