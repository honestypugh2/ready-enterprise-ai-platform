"""Composition root.

One place where the planes are wired together, so that every entry point — API,
worker, CLI, tests — gets the same object graph with the same controls attached.
Wiring scattered across entry points is how one of them ends up without the
kill switch.
"""

from __future__ import annotations

from dataclasses import dataclass

from approvals import ApprovalService, InMemoryApprovalStore, JsonFileApprovalStore
from audit import AuditStore, InMemoryAuditStore, JsonFileAuditStore
from connectors import ScopedWriter, mock_dynamics365, mock_erp, mock_servicenow
from connectors.base import EnterpriseConnector
from detector import build_detector
from detector.base import Detector
from events import EventPublisher, InMemoryEventBus, RecordingEventBus
from events.bus import EventBus
from model_router import PolicyRouter
from observability import configure_logging, configure_observability
from platform_config import ExecutionMode, PlatformSettings, get_settings
from policy_engine import PolicyEngine
from reasoning import build_reasoner
from reasoning.base import Reasoner
from retrieval import build_retriever
from retrieval.base import Retriever
from security.identity import WorkloadIdentity, resolve_credential
from workflows.quality_workflow import GovernedQualityWorkflow

_CONNECTORS = {
    "mock_erp": mock_erp,
    "mock_servicenow": mock_servicenow,
    "mock_d365": mock_dynamics365,
}

_REASONING_ROUTES = {
    "mock": "mock-reasoner",
    "foundry": "small-language-model",
    "model_router": "foundry-model-router",
}


@dataclass(slots=True)
class PlatformAssembly:
    """The wired platform, with the individual planes still reachable for tests."""

    settings: PlatformSettings
    workflow: GovernedQualityWorkflow
    detector: Detector
    retriever: Retriever
    router: PolicyRouter
    reasoner: Reasoner
    policy: PolicyEngine
    approvals: ApprovalService
    writer: ScopedWriter
    connector: EnterpriseConnector
    bus: EventBus
    audit_store: AuditStore

    async def health(self) -> dict[str, bool]:
        return {
            "detector": await self.detector.healthy(),
            "retrieval": await self.retriever.healthy(),
            "reasoning": await self.reasoner.healthy(),
            "connector": await self.connector.healthy(),
        }


def build_platform(
    settings: PlatformSettings | None = None,
    *,
    recording_bus: bool = False,
    persist_state: bool = False,
) -> PlatformAssembly:
    """Wire the platform for the configured execution mode."""
    resolved = settings or get_settings()
    configure_logging()

    credential = (
        None
        if resolved.mode is ExecutionMode.LOCAL_MOCK
        else resolve_credential(resolved, identity=WorkloadIdentity.API)
    )
    configure_observability(resolved, credential=credential)

    detector = build_detector(resolved, credential=credential)
    retriever = build_retriever(resolved, credential=credential)
    reasoning_route = _REASONING_ROUTES[resolved.reasoning.provider]
    router = PolicyRouter.from_path(
        resolved.governance.routing_policy_path,
        health_probe=lambda route_id: route_id == reasoning_route,
    )
    policy = PolicyEngine.from_path(resolved.governance.policy_path)

    # The route decision selects the reasoning deployment, so the reasoner is
    # built against the route the policy would choose rather than a default.
    reasoner = build_reasoner(resolved, credential=credential, route_id=reasoning_route)

    approvals = ApprovalService(
        store=(
            JsonFileApprovalStore(resolved.state_dir / "approvals")
            if persist_state
            else InMemoryApprovalStore()
        ),
        expiry_hours=resolved.governance.approval_expiry_hours,
    )
    audit_store: AuditStore = (
        JsonFileAuditStore(resolved.state_dir / "audit") if persist_state else InMemoryAuditStore()
    )

    connector_factory = _CONNECTORS.get(resolved.connector.provider)
    if connector_factory is None:
        raise ValueError(f"unsupported connector provider: {resolved.connector.provider}")
    connector = connector_factory()

    writer = ScopedWriter(
        connector=connector,
        approvals=approvals,
        dry_run_default=resolved.connector.dry_run,
        max_attempts=resolved.connector.max_attempts,
    )

    bus: EventBus = RecordingEventBus() if recording_bus else InMemoryEventBus()
    publisher = EventPublisher(bus, producer="quality-workflow")

    workflow = GovernedQualityWorkflow(
        detector=detector,
        retriever=retriever,
        router=router,
        reasoner=reasoner,
        policy=policy,
        approvals=approvals,
        writer=writer,
        publisher=publisher,
        audit_store=audit_store,
        workload_id=resolved.workload_id,
        max_steps=resolved.governance.max_workflow_steps,
        kill_switch=resolved.governance.kill_switch_engaged,
    )

    return PlatformAssembly(
        settings=resolved,
        workflow=workflow,
        detector=detector,
        retriever=retriever,
        router=router,
        reasoner=reasoner,
        policy=policy,
        approvals=approvals,
        writer=writer,
        connector=connector,
        bus=bus,
        audit_store=audit_store,
    )
