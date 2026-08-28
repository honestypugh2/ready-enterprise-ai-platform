"""Enterprise action plane.

Adapters know how to talk to a system of record. ``ScopedWriter`` is the only
component permitted to use one, and it refuses six different ways before it
performs a single mutation.

Every connector is dry-run by default. Nothing in this repository creates a
real ticket, order or work order unless an operator deliberately turns dry run
off outside local mode.
"""

from connectors.base import (
    ConnectorError,
    DuplicateWriteError,
    EnterpriseConnector,
)
from connectors.mock import (
    MockConnectorState,
    MockEnterpriseConnector,
    mock_dynamics365,
    mock_erp,
    mock_servicenow,
)
from connectors.writer import ScopedWriter, fingerprint_proposal

__all__ = [
    "ConnectorError",
    "DuplicateWriteError",
    "EnterpriseConnector",
    "MockConnectorState",
    "MockEnterpriseConnector",
    "ScopedWriter",
    "fingerprint_proposal",
    "mock_dynamics365",
    "mock_erp",
    "mock_servicenow",
]
