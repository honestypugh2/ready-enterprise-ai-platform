"""Microsoft Foundry / Azure OpenAI reasoning adapter.

Isolated behind ``Reasoner`` so that an SDK change touches one adapter and
nothing else. Three properties are deliberate:

* **Entra-first auth.** A bearer token provider scoped to
  ``https://cognitiveservices.azure.com/.default``. No key is read from
  configuration and no connection string is accepted.
* **Structured output, then validated anyway.** The response schema is supplied
  to the service *and* the parsed result is validated locally, because a
  boundary you only validate on one side is not validated.
* **Grounding enforced after generation.** Citations are checked against the
  passages retrieved in this turn. An ungrounded answer is withheld, not
  returned with a caveat.

Client library surfaces in this area change. Validate the call shape against
current Azure OpenAI / Foundry documentation before relying on it in a customer
environment; the structure of this module is the part intended to be copied.
"""

from __future__ import annotations

import json
import time
from typing import Any

from contracts.reasoning import Citation, ProposedAction, ReasoningRequest, Recommendation
from reasoning.base import ReasoningUnavailableError, UngroundedOutputError
from reasoning.prompts import OUTPUT_SCHEMA, render

COGNITIVE_SERVICES_SCOPE = "https://cognitiveservices.azure.com/.default"


class FoundryReasoner:
    """Calls a Foundry model deployment and refuses to return ungrounded output."""

    def __init__(
        self,
        *,
        endpoint: str,
        deployment: str,
        api_version: str,
        credential: Any,
        route_id: str,
        model_version: str = "deployment-pinned",
        max_output_tokens: int = 800,
        temperature: float = 0.0,
        timeout_ms: int = 20_000,
        client: Any | None = None,
    ) -> None:
        self.model_name = deployment
        self.model_version = model_version
        self.route_id = route_id
        self._endpoint = endpoint
        self._deployment = deployment
        self._api_version = api_version
        self._credential = credential
        self._max_output_tokens = max_output_tokens
        self._temperature = temperature
        self._timeout_s = timeout_ms / 1000.0
        self._client = client

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from azure.identity import get_bearer_token_provider  # noqa: PLC0415  (optional extra)
            from openai import AsyncAzureOpenAI  # noqa: PLC0415  (optional extra)
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise ReasoningUnavailableError(
                "azure-identity and openai are required; run `uv sync --extra azure`"
            ) from exc

        self._client = AsyncAzureOpenAI(
            azure_endpoint=self._endpoint,
            api_version=self._api_version,
            azure_ad_token_provider=get_bearer_token_provider(
                self._credential, COGNITIVE_SERVICES_SCOPE
            ),
            timeout=self._timeout_s,
        )
        return self._client

    async def healthy(self) -> bool:
        try:
            self._ensure_client()
        except ReasoningUnavailableError:
            return False
        return True

    async def explain(self, request: ReasoningRequest) -> Recommendation:
        started = time.perf_counter()
        client = self._ensure_client()
        prompt = render(request)

        try:
            response = await client.chat.completions.create(
                model=self._deployment,
                messages=[
                    {"role": "system", "content": prompt.system},
                    {"role": "user", "content": prompt.user},
                ],
                temperature=self._temperature,
                max_tokens=self._max_output_tokens,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "defect_explanation",
                        "strict": True,
                        "schema": OUTPUT_SCHEMA,
                    },
                },
            )
        except Exception as exc:
            raise ReasoningUnavailableError(
                f"Foundry model call failed: {type(exc).__name__}",
                correlation_id=request.correlation_id,
            ) from exc

        content = response.choices[0].message.content if response.choices else None
        if not content:
            raise ReasoningUnavailableError(
                "model returned an empty response", correlation_id=request.correlation_id
            )

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ReasoningUnavailableError(
                "model response was not valid JSON", correlation_id=request.correlation_id
            ) from exc

        usage = getattr(response, "usage", None)
        return self._to_recommendation(
            request=request,
            parsed=parsed,
            started=started,
            input_tokens=getattr(usage, "prompt_tokens", None),
            output_tokens=getattr(usage, "completion_tokens", None),
        )

    def _to_recommendation(
        self,
        *,
        request: ReasoningRequest,
        parsed: dict[str, Any],
        started: float,
        input_tokens: int | None,
        output_tokens: int | None,
    ) -> Recommendation:
        known_refs = {item.citation_ref: item for item in request.evidence.items}

        citations: list[Citation] = []
        invented: list[str] = []
        for raw in parsed.get("citations") or []:
            ref = str(raw.get("citation_ref", ""))
            item = known_refs.get(ref)
            if item is None:
                # An invented source is dropped and reported, never rendered.
                invented.append(ref)
                continue
            citations.append(
                Citation(
                    citation_ref=ref,
                    source_id=item.source_id,
                    source_title=item.source_title,
                    source_uri=item.source_uri,
                    quoted_span=str(raw.get("quoted_span", ""))[:1000] or item.passage[:400],
                    supports_claim=str(raw.get("supports_claim", ""))[:1000] or item.source_title,
                )
            )

        refused = bool(parsed.get("refused")) or (not citations and bool(known_refs))
        refusal_reason = parsed.get("refusal_reason")
        if refused and not refusal_reason:
            refusal_reason = "The model produced no resolvable citation for the supplied evidence."

        missing = [str(entry) for entry in (parsed.get("missing_information") or [])]
        if invented:
            missing.append(f"Model referenced sources that were not retrieved: {invented}.")

        proposed_raw = parsed.get("proposed_action")
        proposed = None
        if proposed_raw and not refused:
            proposed = ProposedAction(
                action_kind=str(proposed_raw.get("action_kind", "notify_supervisor")),
                target_system=str(proposed_raw.get("target_system", "mock-erp")),
                summary=str(proposed_raw.get("summary", ""))[:500] or "No summary supplied",
            )

        try:
            return Recommendation(
                request_id=request.request_id,
                correlation_id=request.correlation_id,
                headline=str(parsed.get("headline", ""))[:200] or "Explanation unavailable",
                rationale=str(parsed.get("rationale", ""))[:4000] or "No rationale supplied",
                proposed_action=None if refused else proposed,
                citations=tuple(citations),
                missing_information=tuple(missing),
                self_reported_confidence=float(parsed.get("self_reported_confidence", 0.5)),
                refused=refused,
                refusal_reason=refusal_reason if refused else None,
                model_name=self.model_name,
                model_version=self.model_version,
                prompt_id=request.prompt_id,
                prompt_version=request.prompt_version,
                route_id=self.route_id,
                latency_ms=(time.perf_counter() - started) * 1000.0,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        except ValueError as exc:
            # The contract itself rejects an ungrounded, non-refusing answer.
            raise UngroundedOutputError(
                f"model output failed the grounding contract: {exc}",
                correlation_id=request.correlation_id,
            ) from exc
