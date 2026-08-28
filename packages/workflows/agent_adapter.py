"""Bounded agent adapter.

Optional. Present so that the *option* of an agent is a design choice with a
visible cost, rather than an assumption baked into the architecture.

Everything an agent needs to be operable in production is enforced here rather
than requested in a prompt: an allow-list of typed tools, a step budget, a wall
clock budget, a spend budget, termination conditions, a kill switch, and a
complete record of every invocation including the refused ones.

A tool that is not registered cannot be called even if the model names it
correctly, and repeated requests for tools that do not exist are counted rather
than discarded — they are one of the earliest observable symptoms of prompt
injection.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from contracts.action import ActionKind
from contracts.common import CostCategory, utcnow
from contracts.errors import BudgetExceededError, KillSwitchEngagedError, UnauthorizedWriteError
from observability import METRICS
from observability.logging_config import get_logger
from security.identity import IdentityContext

logger = get_logger(__name__)

ToolHandler = Callable[[dict[str, Any], IdentityContext], Awaitable[dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class ToolContract:
    """A tool as a typed API product: owner, scope, impact, schema, handler."""

    name: str
    description: str
    owner: str
    required_scope: str
    required_fields: frozenset[str]
    handler: ToolHandler
    mutates_system_of_record: bool = False
    requires_human_approval: bool = False


@dataclass(frozen=True, slots=True)
class AgentBudget:
    """Termination conditions. All four are enforced, not advisory."""

    max_steps: int = 8
    max_tool_calls: int = 6
    max_wall_clock_s: float = 30.0
    max_cost_units: float = 25.0


@dataclass(slots=True)
class ToolInvocationRecord:
    """One attempt, successful or refused. The refusals are the useful half."""

    tool_name: str
    accepted: bool
    reason_code: str | None
    latency_ms: float
    occurred_at: datetime = field(default_factory=utcnow)


class BoundedAgentAdapter:
    """Runs an agent under enforced authority limits."""

    def __init__(
        self,
        *,
        tools: dict[str, ToolContract],
        identity: IdentityContext,
        budget: AgentBudget | None = None,
        kill_switch: bool = False,
    ) -> None:
        self._tools = tools
        self._identity = identity
        self._budget = budget or AgentBudget()
        self.kill_switch = kill_switch
        self.invocations: list[ToolInvocationRecord] = []
        self._steps = 0
        self._cost_units = 0.0
        self._started = time.monotonic()

    @property
    def allowed_tools(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    @property
    def terminated(self) -> bool:
        return (
            self._steps >= self._budget.max_steps
            or len([i for i in self.invocations if i.accepted]) >= self._budget.max_tool_calls
            or (time.monotonic() - self._started) >= self._budget.max_wall_clock_s
            or self._cost_units >= self._budget.max_cost_units
        )

    async def invoke(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        approval_id: str | None = None,
        cost_units: float = 1.0,
    ) -> dict[str, Any]:
        """Resolve, validate, authorize, then execute. Always in that order.

        Validation before authorization means a malformed request never reaches
        an authorization decision. Authorization before execution means a
        well-formed request from an unentitled caller never reaches a system of
        record.
        """
        started = time.perf_counter()
        self._steps += 1

        def refuse(reason: str) -> None:
            self.invocations.append(
                ToolInvocationRecord(
                    tool_name=tool_name,
                    accepted=False,
                    reason_code=reason,
                    latency_ms=(time.perf_counter() - started) * 1000.0,
                )
            )

        if self.kill_switch:
            refuse("KILL_SWITCH_ENGAGED")
            raise KillSwitchEngagedError("agent is administratively disabled")

        if self.terminated:
            refuse("BUDGET_EXHAUSTED")
            raise BudgetExceededError("agent budget exhausted before this call")

        contract = self._tools.get(tool_name)
        if contract is None:
            # Counted, not swallowed: repeated unknown-tool requests are an
            # early symptom of injection.
            refuse("UNKNOWN_TOOL")
            METRICS.unauthorized_attempts += 1
            logger.warning(
                "unknown_tool_requested",
                extra={"tool": tool_name, "principal_id": self._identity.principal_id},
            )
            raise UnauthorizedWriteError(f"tool not available: {tool_name}")

        missing = contract.required_fields - set(arguments)
        if missing:
            refuse("SCHEMA_VIOLATION")
            raise UnauthorizedWriteError(
                f"{tool_name} missing required arguments: {sorted(missing)}"
            )

        if not self._identity.has_role(contract.required_scope):
            refuse("SCOPE_MISSING")
            METRICS.unauthorized_attempts += 1
            raise UnauthorizedWriteError(
                f"principal lacks scope '{contract.required_scope}' for {tool_name}"
            )

        if contract.requires_human_approval and not approval_id:
            refuse("APPROVAL_MISSING")
            raise UnauthorizedWriteError(f"{tool_name} requires a recorded human approval")

        if contract.mutates_system_of_record:
            # The agent proposes; only the scoped writer mutates. A tool that
            # claims otherwise is a configuration error, caught here.
            refuse("AGENT_MAY_NOT_MUTATE")
            METRICS.unauthorized_attempts += 1
            raise UnauthorizedWriteError(
                f"{tool_name} mutates a system of record and is not agent-invocable"
            )

        result = await contract.handler(arguments, self._identity)
        self._cost_units += cost_units
        self.invocations.append(
            ToolInvocationRecord(
                tool_name=tool_name,
                accepted=True,
                reason_code=None,
                latency_ms=(time.perf_counter() - started) * 1000.0,
            )
        )
        return result

    def summary(self) -> dict[str, Any]:
        accepted = [i for i in self.invocations if i.accepted]
        refused = [i for i in self.invocations if not i.accepted]
        return {
            "steps": self._steps,
            "accepted_calls": len(accepted),
            "refused_calls": len(refused),
            "refusal_reasons": sorted({i.reason_code for i in refused if i.reason_code}),
            "cost_units": self._cost_units,
            "cost_category": CostCategory.LOW.value,
            "terminated": self.terminated,
            "allowed_tools": self.allowed_tools,
        }


def read_only_tool(
    *,
    name: str,
    description: str,
    owner: str,
    required_scope: str,
    required_fields: frozenset[str],
    handler: ToolHandler,
) -> ToolContract:
    """Helper that makes the safe shape the easy shape."""
    return ToolContract(
        name=name,
        description=description,
        owner=owner,
        required_scope=required_scope,
        required_fields=required_fields,
        handler=handler,
        mutates_system_of_record=False,
        requires_human_approval=False,
    )


MUTATING_ACTIONS: frozenset[ActionKind] = frozenset(
    {
        ActionKind.CREATE_WORK_ORDER,
        ActionKind.CREATE_INCIDENT,
        ActionKind.QUARANTINE_BATCH,
    }
)
