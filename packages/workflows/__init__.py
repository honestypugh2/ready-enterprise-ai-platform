"""Agent and workflow plane.

``GovernedQualityWorkflow`` is the default architecture: an explicit,
terminating sequence of twelve steps. An agent adapter is available for the
cases where dynamic tool selection genuinely earns its coordination cost, and it
runs under the same bounded authority as the workflow.

The test to apply before reaching for an agent: what does the agent decide that
a workflow could not decide? If the only answer is the wording of the response,
what is needed is a model call inside an application, not an agent runtime with
tools, memory and its own identity.
"""

from workflows.agent_adapter import AgentBudget, BoundedAgentAdapter, ToolInvocationRecord
from workflows.assembly import PlatformAssembly, build_platform
from workflows.quality_workflow import (
    WORKFLOW_STEPS,
    GovernedQualityWorkflow,
    WorkflowOutcome,
)

__all__ = [
    "WORKFLOW_STEPS",
    "AgentBudget",
    "BoundedAgentAdapter",
    "GovernedQualityWorkflow",
    "PlatformAssembly",
    "ToolInvocationRecord",
    "WorkflowOutcome",
    "build_platform",
]
