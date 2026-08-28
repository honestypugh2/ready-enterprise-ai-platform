"""API application.

A thin HTTP surface over the governed workflow. It owns validation, identity
resolution, correlation and telemetry; every governance decision belongs to the
planes underneath it.
"""

from api.main import app, create_app

__all__ = ["app", "create_app"]
