"""Routing and policy plane.

Routing is an architecture decision, not configuration buried in application
code. Every decision records the candidates considered, the ones excluded and
why, the reason codes, the policy version and its hash.

A route you cannot explain after the fact is not a policy. It is a coincidence.
"""

from model_router.router import NoEligibleRouteError, PolicyRouter
from model_router.schema import (
    RouteDefinition,
    RoutingCondition,
    RoutingPolicy,
    RoutingRule,
    load_routing_policy,
)

__all__ = [
    "NoEligibleRouteError",
    "PolicyRouter",
    "RouteDefinition",
    "RoutingCondition",
    "RoutingPolicy",
    "RoutingRule",
    "load_routing_policy",
]
