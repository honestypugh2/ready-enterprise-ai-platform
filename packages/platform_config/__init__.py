"""Typed configuration.

Configuration fails fast at start-up when a required value is missing, which
converts a class of production incidents into a deployment failure. Local mock
mode is the default and requires no cloud credential of any kind.
"""

from platform_config.settings import (
    ConnectorSettings,
    DetectorSettings,
    ExecutionMode,
    GovernanceSettings,
    ObservabilitySettings,
    PlatformSettings,
    PredictiveSettings,
    ReasoningSettings,
    RetrievalSettings,
    get_settings,
    reset_settings_cache,
)

__all__ = [
    "ConnectorSettings",
    "DetectorSettings",
    "ExecutionMode",
    "GovernanceSettings",
    "ObservabilitySettings",
    "PlatformSettings",
    "PredictiveSettings",
    "ReasoningSettings",
    "RetrievalSettings",
    "get_settings",
    "reset_settings_cache",
]
