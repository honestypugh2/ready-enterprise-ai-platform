"""Policy-aware model router.

Selects the component that answers a request, and records why. The rejected
candidates are the interesting half of the log: a decision that only shows the
winner cannot be reviewed, only accepted.

Nothing here hard-codes a frontier model as a default. A frontier route is
reachable only through a rule that names a capability the cheaper routes do not
have.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from contracts.common import CostCategory
from contracts.routing import (
    RouteCandidate,
    RouteDecision,
    RouteExclusion,
    RouteRequest,
)
from model_router.schema import RouteDefinition, RoutingPolicy, RoutingRule, load_routing_policy

_COST_ORDER: dict[CostCategory, int] = {
    CostCategory.NONE: 0,
    CostCategory.NEGLIGIBLE: 1,
    CostCategory.LOW: 2,
    CostCategory.MEDIUM: 3,
    CostCategory.HIGH: 4,
}

HealthProbe = Callable[[str], bool]


class PolicyRouter:
    """Deterministic router over a versioned routing policy."""

    def __init__(
        self,
        policy: RoutingPolicy,
        *,
        health_probe: HealthProbe | None = None,
    ) -> None:
        self._policy = policy
        # Availability is a runtime fact, kept out of the policy document so
        # that an outage does not require a policy change.
        self._health = health_probe or (lambda _route_id: True)

    @classmethod
    def from_path(cls, path: Path, *, health_probe: HealthProbe | None = None) -> PolicyRouter:
        return cls(load_routing_policy(path), health_probe=health_probe)

    @property
    def version(self) -> str:
        return self._policy.version

    @property
    def sha(self) -> str:
        return self._policy.sha

    def candidates(self) -> tuple[RouteCandidate, ...]:
        return tuple(
            RouteCandidate(
                route_id=definition.route_id,
                kind=definition.kind,
                supports=frozenset(definition.supports),
                capabilities=frozenset(definition.capabilities),
                typical_latency_ms=definition.typical_latency_ms,
                max_classification=definition.max_classification,
                cost_category=definition.cost_category,
                execution_location=definition.execution_location,
                residency=definition.residency,
                deterministic=definition.deterministic,
                enabled=definition.enabled,
                evaluation_ref=definition.evaluation_ref,
            )
            for definition in self._policy.routes
        )

    def route(self, request: RouteRequest) -> RouteDecision:
        matched_rule = self._first_rule(request)
        preferred = list(matched_rule.prefer) if matched_rule else list(self._policy.fallback.order)
        allow_unproven = matched_rule.allow_unproven if matched_rule else True

        reason_codes: list[str] = [
            matched_rule.reason_code if matched_rule else "NO_RULE_MATCHED_USING_FALLBACK"
        ]
        exclusions: list[RouteExclusion] = []
        considered: list[str] = []

        selected = self._select(preferred, request, allow_unproven, considered, exclusions)
        is_fallback = False

        if selected is None:
            if not request.fallback_eligible:
                raise NoEligibleRouteError(
                    "no route satisfied the request and fallback is not permitted",
                    exclusions=tuple(exclusions),
                )
            is_fallback = True
            reason_codes.append(self._policy.fallback.reason_code)
            selected = self._select(
                list(self._policy.fallback.order), request, True, considered, exclusions
            )

        if selected is None:
            raise NoEligibleRouteError(
                "no route satisfied the request, including the fallback chain",
                exclusions=tuple(exclusions),
            )

        if selected.deterministic:
            reason_codes.append("DETERMINISTIC_ROUTE_PREFERRED")
        if selected.evaluation_ref is None:
            reason_codes.append("ROUTE_HAS_NO_EVALUATION_EVIDENCE")

        return RouteDecision(
            request_id=request.request_id,
            correlation_id=request.correlation_id,
            selected_route=selected.route_id,
            selected_kind=selected.kind,
            reason_codes=tuple(dict.fromkeys(reason_codes)),
            candidates_considered=tuple(dict.fromkeys(considered)),
            excluded=tuple(exclusions),
            policy_version=self._policy.version,
            policy_sha=self._policy.sha,
            cost_category=selected.cost_category,
            latency_target_ms=min(request.max_latency_ms, selected.typical_latency_ms * 4),
            execution_location=selected.execution_location,
            is_fallback=is_fallback,
        )

    # -- internals ---------------------------------------------------------

    def _first_rule(self, request: RouteRequest) -> RoutingRule | None:
        for rule in self._policy.rules:
            condition = rule.when
            checks: tuple[tuple[object | None, bool], ...] = (
                (condition.task_type_in, request.task_type in (condition.task_type_in or ())),
                (
                    condition.requires_capabilities,
                    set(condition.requires_capabilities or ()).issubset(
                        request.required_capabilities
                    ),
                ),
                (
                    condition.classification_at_least,
                    condition.classification_at_least is not None
                    and request.classification.rank >= condition.classification_at_least.rank,
                ),
                (
                    condition.max_latency_ms_below,
                    request.max_latency_ms < (condition.max_latency_ms_below or 0),
                ),
                (
                    condition.business_risk_in,
                    request.business_risk in (condition.business_risk_in or ()),
                ),
                (
                    condition.upstream_confidence_below,
                    request.upstream_confidence is not None
                    and request.upstream_confidence < (condition.upstream_confidence_below or 0.0),
                ),
                (condition.residency_equals, request.residency == condition.residency_equals),
            )
            if all(ok for specified, ok in checks if specified is not None):
                return rule
        return None

    def _select(
        self,
        preferred: list[str],
        request: RouteRequest,
        allow_unproven: bool,
        considered: list[str],
        exclusions: list[RouteExclusion],
    ) -> RouteDefinition | None:
        eligible: list[RouteDefinition] = []
        for route_id in preferred:
            definition = self._policy.route(route_id)
            if definition is None:
                continue
            considered.append(route_id)
            reason = self._reject(definition, request, allow_unproven)
            if reason is None:
                eligible.append(definition)
            else:
                exclusions.append(
                    RouteExclusion(route_id=route_id, reason_code=reason[0], detail=reason[1])
                )
        if not eligible:
            return None
        # Proven routes first, then cheapest, then fastest. Evidence outranks
        # cost deliberately: a cheaper route with no benchmark is a saving you
        # cannot defend. Preference order in the rule only breaks exact ties, so
        # a rule cannot smuggle in an expensive default by listing it first.
        return min(
            eligible,
            key=lambda d: (
                d.evaluation_ref is None,
                _COST_ORDER[d.cost_category],
                d.typical_latency_ms,
            ),
        )

    def _reject(
        self, definition: RouteDefinition, request: RouteRequest, allow_unproven: bool
    ) -> tuple[str, str] | None:
        if not definition.enabled:
            return ("ROUTE_DISABLED", "route is administratively disabled")
        if request.task_type not in definition.supports:
            return ("TASK_UNSUPPORTED", f"does not support {request.task_type.value}")
        missing = request.required_capabilities - set(definition.capabilities)
        if missing:
            return ("CAPABILITY_MISSING", f"missing: {sorted(missing)}")
        if definition.max_classification.rank < request.classification.rank:
            return (
                "CLASSIFICATION_EXCEEDED",
                f"route accepts up to {definition.max_classification.value}",
            )
        if request.residency and definition.residency and definition.residency != request.residency:
            return ("RESIDENCY_MISMATCH", f"route residency is {definition.residency}")
        if definition.typical_latency_ms > request.max_latency_ms:
            return (
                "LATENCY_BUDGET_EXCEEDED",
                f"{definition.typical_latency_ms}ms > {request.max_latency_ms}ms budget",
            )
        if _COST_ORDER[definition.cost_category] > _COST_ORDER[request.cost_ceiling]:
            return (
                "COST_CEILING_EXCEEDED",
                f"{definition.cost_category.value} > {request.cost_ceiling.value}",
            )
        if (
            self._policy.require_evaluation_evidence
            and definition.evaluation_ref is None
            and not allow_unproven
        ):
            return ("NO_EVALUATION_EVIDENCE", "route has no benchmark reference")
        if not self._health(definition.route_id):
            return ("ROUTE_UNHEALTHY", "health probe reported unavailable")
        return None


class NoEligibleRouteError(RuntimeError):
    def __init__(self, message: str, *, exclusions: tuple[RouteExclusion, ...]) -> None:
        super().__init__(message)
        self.exclusions = exclusions
