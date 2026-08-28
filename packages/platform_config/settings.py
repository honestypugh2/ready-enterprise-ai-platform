"""Settings for all three execution modes."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class ExecutionMode(StrEnum):
    """Which dependencies the platform is permitted to reach.

    ``LOCAL_MOCK`` is the default and is the only mode guaranteed to run with no
    Azure subscription, no credential and no network access.
    """

    LOCAL_MOCK = "local_mock"
    AZURE_DEV = "azure_dev"
    PRODUCTION = "production"


class DetectorSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REAP_DETECTOR_", extra="ignore")

    provider: str = Field(default="mock", pattern=r"^(mock|onnx|aml)$")
    model_name: str = "surface-defect-detector"
    model_version: str = "0.3.0-demo"
    decision_threshold: float = Field(default=0.62, ge=0.0, le=1.0)
    timeout_ms: int = Field(default=2_000, gt=0)
    max_attempts: int = Field(default=2, ge=1, le=5)
    onnx_model_path: Path | None = None
    aml_endpoint_url: str | None = None
    aml_deployment_name: str | None = None


class RetrievalSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REAP_RETRIEVAL_", extra="ignore")

    provider: str = Field(default="local", pattern=r"^(local|azure_search)$")
    knowledge_dir: Path = REPO_ROOT / "data" / "knowledge"
    index_name: str = "manufacturing-knowledge"
    top_k: int = Field(default=5, ge=1, le=50)
    search_endpoint: str | None = None
    semantic_configuration: str = "default"


class ReasoningSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REAP_REASONING_", extra="ignore")

    provider: str = Field(default="mock", pattern=r"^(mock|foundry|model_router)$")
    endpoint: str | None = None
    small_model_deployment: str = "gpt-4o-mini"
    frontier_model_deployment: str = "gpt-4o"
    api_version: str = "2024-10-21"
    max_output_tokens: int = Field(default=800, ge=32, le=8_000)
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    timeout_ms: int = Field(default=20_000, gt=0)


class ConnectorSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REAP_CONNECTOR_", extra="ignore")

    provider: str = Field(
        default="mock_erp", pattern=r"^(mock_erp|mock_servicenow|mock_d365|http)$"
    )
    base_url: str | None = None
    # Writes are dry-run until deliberately enabled. Nothing in this repository
    # creates a real ticket, order or business record by default.
    dry_run: bool = True
    timeout_ms: int = Field(default=10_000, gt=0)
    max_attempts: int = Field(default=3, ge=1, le=10)


class ObservabilitySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REAP_OTEL_", extra="ignore")

    service_name: str = "ready-enterprise-ai-platform"
    # Off by default so the CLI and demo output stay readable. Turn on with
    # REAP_OTEL_CONSOLE_EXPORTER=true to see the raw spans.
    console_exporter: bool = False
    applicationinsights_connection_string: str | None = None
    sample_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    redaction_enabled: bool = True


class GovernanceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REAP_GOVERNANCE_", extra="ignore")

    policy_path: Path = REPO_ROOT / "packages" / "policy_engine" / "policies" / "manufacturing.yaml"
    routing_policy_path: Path = (
        REPO_ROOT / "packages" / "model_router" / "policies" / "routing.yaml"
    )
    approval_expiry_hours: int = Field(default=8, ge=1, le=168)
    kill_switch_engaged: bool = False
    max_workflow_steps: int = Field(default=24, ge=4, le=200)
    max_cost_units_per_task: float = Field(default=100.0, gt=0)


class PredictiveSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REAP_PREDICTIVE_", extra="ignore")

    provider: str = Field(
        default="seasonal_naive", pattern=r"^(seasonal_naive|moving_average|aml)$"
    )
    horizon: int = Field(default=14, ge=1, le=365)
    season_length: int = Field(default=7, ge=1, le=365)
    window: int = Field(default=7, ge=1, le=365)
    # A forecast that cannot beat seasonal-naive by this margin is not adding
    # information. Consumers read `Forecast.adds_information`; this is the bar.
    minimum_baseline_skill: float = Field(default=0.0, ge=-1.0, le=1.0)
    timeout_ms: int = Field(default=5_000, gt=0)
    max_attempts: int = Field(default=2, ge=1, le=5)
    aml_endpoint_url: str | None = None
    aml_deployment_name: str | None = None


class PlatformSettings(BaseSettings):
    """Root settings object. One instance per process, cached."""

    model_config = SettingsConfigDict(
        env_prefix="REAP_",
        env_file=(".env",),
        env_file_encoding="utf-8",
        extra="ignore",
        env_nested_delimiter="__",
    )

    mode: ExecutionMode = ExecutionMode.LOCAL_MOCK
    environment: str = Field(default="local", pattern=r"^(local|dev|test|prod)$")
    tenant_label: str = "demo-tenant"
    workload_id: str = "manufacturing-quality"
    data_dir: Path = REPO_ROOT / "data"
    state_dir: Path = REPO_ROOT / ".reap-state"

    detector: DetectorSettings = Field(default_factory=DetectorSettings)
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    reasoning: ReasoningSettings = Field(default_factory=ReasoningSettings)
    connector: ConnectorSettings = Field(default_factory=ConnectorSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)
    governance: GovernanceSettings = Field(default_factory=GovernanceSettings)
    predictive: PredictiveSettings = Field(default_factory=PredictiveSettings)

    @property
    def is_local_mock(self) -> bool:
        return self.mode is ExecutionMode.LOCAL_MOCK

    @property
    def azure_enabled(self) -> bool:
        return self.mode in {ExecutionMode.AZURE_DEV, ExecutionMode.PRODUCTION}

    @model_validator(mode="after")
    def _mode_consistency(self) -> Self:
        if self.is_local_mock:
            # Local mode is a promise, so it is enforced rather than documented.
            for name, provider in (
                ("detector", self.detector.provider),
                ("retrieval", self.retrieval.provider),
                ("reasoning", self.reasoning.provider),
                ("predictive", self.predictive.provider),
            ):
                if provider not in {"mock", "local", "onnx", "seasonal_naive", "moving_average"}:
                    raise ValueError(
                        f"local_mock mode cannot use {name} provider '{provider}'; "
                        "set REAP_MODE=azure_dev to reach cloud dependencies"
                    )
            if not self.connector.dry_run:
                raise ValueError("local_mock mode requires connector dry_run=true")

        if self.mode is ExecutionMode.PRODUCTION:
            missing = [
                field
                for field, value in (
                    (
                        "REAP_OTEL_APPLICATIONINSIGHTS_CONNECTION_STRING",
                        self.observability.applicationinsights_connection_string,
                    ),
                    ("REAP_RETRIEVAL_SEARCH_ENDPOINT", self.retrieval.search_endpoint),
                    ("REAP_REASONING_ENDPOINT", self.reasoning.endpoint),
                )
                if not value
            ]
            if missing:
                raise ValueError("production mode requires: " + ", ".join(missing))
        return self


@lru_cache(maxsize=1)
def get_settings() -> PlatformSettings:
    return PlatformSettings()


def reset_settings_cache() -> None:
    """Test hook. Production code never calls this."""
    get_settings.cache_clear()
