"""Reasoner protocol.

The interface is deliberately narrow: evidence in, structured explanation out.
There is no method here through which a reasoner could write, approve, or
change an authoritative value.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from contracts.errors import UpstreamUnavailableError
from contracts.reasoning import ReasoningRequest, Recommendation


class ReasoningUnavailableError(UpstreamUnavailableError):
    plane = "reasoning"


class UngroundedOutputError(UpstreamUnavailableError):
    """The model produced an answer with no resolvable citation.

    Treated as a defect rather than a degraded answer: a confident paragraph
    with a decorative footnote is worse than an explicit refusal.
    """

    retryable = False
    plane = "reasoning"


@runtime_checkable
class Reasoner(Protocol):
    model_name: str
    model_version: str
    route_id: str

    async def explain(self, request: ReasoningRequest) -> Recommendation: ...
    async def healthy(self) -> bool: ...
