"""Deterministic policy plane.

The authoritative verdict lives here, in ordered rules that execute in code
against a versioned, hash-stamped document. The reasoning plane may explain a
decision made here; it has no mechanism to change one.

Design rules this package holds itself to:

* First-match-wins, ordered. Ordering is part of the contract.
* Guards may only narrow an outcome, never widen it.
* An unmatched input takes the conservative default, because a policy whose
  default is "allow" is not a control.
"""

from policy_engine.engine import PolicyEngine, PolicyInput
from policy_engine.schema import (
    PolicyDocument,
    PolicyGuard,
    PolicyRule,
    RuleCondition,
    RuleOutcome,
    load_policy,
)

__all__ = [
    "PolicyDocument",
    "PolicyEngine",
    "PolicyGuard",
    "PolicyInput",
    "PolicyRule",
    "RuleCondition",
    "RuleOutcome",
    "load_policy",
]
