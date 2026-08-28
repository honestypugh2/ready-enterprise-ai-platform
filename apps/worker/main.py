"""Event worker.

Consumes the facts the workflow publishes and does the work that must not sit
in the request path: persisting evidence, tracking drift signals, counting
approvals that nobody has acted on, and raising an operational signal when a
transaction stalls at the approval gate.

Two properties matter here and are enforced rather than assumed:

* **A subscriber cannot write to a system of record.** The worker holds no
  connector and no writer. ``tests/contract/test_sole_writer.py`` fails the
  build if that ever changes.
* **A failing subscriber degrades that subscriber only.** The bus catches
  handler exceptions, so a bad handler cannot roll back a completed
  transaction that has already been audited.

In local mode this runs against the in-process bus, which delivers exactly the
same envelopes Service Bus would. That is what makes the worker testable
offline instead of only in a deployed environment.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
from collections import Counter
from dataclasses import dataclass, field

from contracts.events import EventEnvelope, EventType
from observability.logging_config import get_logger
from observability.metrics import METRICS
from platform_config import PlatformSettings, get_settings
from workflows import PlatformAssembly, build_platform

logger = get_logger(__name__)

# The events this worker reacts to. Subscribing to everything makes the log
# noisy and hides which facts actually drive downstream work.
SUBSCRIBED = (
    EventType.PREDICTION_CREATED,
    EventType.POLICY_EVALUATED,
    EventType.APPROVAL_REQUESTED,
    EventType.APPROVAL_DECIDED,
    EventType.ACTION_EXECUTED,
    EventType.ACTION_FAILED,
    EventType.AUDIT_SEALED,
    EventType.KILL_SWITCH_ENGAGED,
)


@dataclass(slots=True)
class WorkerState:
    """What the worker has observed. Readable by a health probe."""

    handled: Counter[str] = field(default_factory=Counter)
    pending_approvals: set[str] = field(default_factory=set)
    failed_actions: int = 0
    sealed_audits: int = 0

    @property
    def total_handled(self) -> int:
        return sum(self.handled.values())

    def snapshot(self) -> dict[str, object]:
        return {
            "handled_total": self.total_handled,
            "handled_by_type": dict(self.handled),
            "pending_approvals": len(self.pending_approvals),
            "failed_actions": self.failed_actions,
            "sealed_audits": self.sealed_audits,
        }


class EventWorker:
    """Subscribes to the platform bus and reacts to published facts."""

    def __init__(self, assembly: PlatformAssembly) -> None:
        self._assembly = assembly
        self.state = WorkerState()

    def register(self) -> None:
        for event_type in SUBSCRIBED:
            self._assembly.bus.subscribe(event_type, self._handle)

    async def _handle(self, envelope: EventEnvelope) -> None:
        self.state.handled[envelope.event_type.value] += 1

        match envelope.event_type:
            case EventType.APPROVAL_REQUESTED:
                self.state.pending_approvals.add(envelope.subject)
            case EventType.APPROVAL_DECIDED:
                self.state.pending_approvals.discard(envelope.subject)
            case EventType.ACTION_FAILED:
                self.state.failed_actions += 1
            case EventType.AUDIT_SEALED:
                self.state.sealed_audits += 1
            case EventType.KILL_SWITCH_ENGAGED:
                # Loud on purpose: an administrative stop is the one event an
                # operator must never have to go looking for.
                logger.warning(
                    "kill_switch_observed",
                    extra={"correlation_id": envelope.correlation_id},
                )
            case _:
                pass

        logger.info(
            "event_handled",
            extra={
                "event_type": envelope.event_type.value,
                "correlation_id": envelope.correlation_id,
                "subject": envelope.subject,
                "producer": envelope.producer,
            },
        )

    async def run_forever(self, *, heartbeat_seconds: float = 30.0) -> None:
        """Report state on an interval until cancelled."""
        while True:
            await asyncio.sleep(heartbeat_seconds)
            logger.info("worker_heartbeat", extra=self.state.snapshot() | METRICS.snapshot())

    async def close(self) -> None:
        await self._assembly.bus.close()


def build_worker(settings: PlatformSettings | None = None) -> EventWorker:
    """Compose a worker on the shared platform assembly."""
    worker = EventWorker(build_platform(settings or get_settings()))
    worker.register()
    return worker


async def main() -> None:
    settings = get_settings()
    worker = build_worker(settings)

    logger.info(
        "worker_started",
        extra={
            "mode": settings.mode.value,
            "workload_id": settings.workload_id,
            "subscribed": [e.value for e in SUBSCRIBED],
        },
    )

    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        # Draining on a signal is what makes a rolling deployment safe.
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stopping.set)

    heartbeat = asyncio.create_task(worker.run_forever())
    await stopping.wait()

    heartbeat.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await heartbeat
    await worker.close()

    logger.info("worker_stopped", extra=worker.state.snapshot())


if __name__ == "__main__":
    asyncio.run(main())
