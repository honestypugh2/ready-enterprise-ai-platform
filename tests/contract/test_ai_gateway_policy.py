"""The AI Gateway policy says what the README says it does.

The policy is XML that only Azure API Management executes, so these tests do
the next best thing: compose every variant ``infra/modules/apim.bicep`` can
deploy, exactly as Bicep does, and check each one. They cannot prove the
gateway behaves; ``IMPLEMENTATION_STATUS.md`` records what was observed live.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from itertools import product
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INFRA = REPO_ROOT / "infra"
POLICY = INFRA / "apim" / "ai-gateway.policy.xml"
FRAGMENTS = INFRA / "apim" / "fragments"
APIM_BICEP = INFRA / "modules" / "apim.bicep"
RBAC_BICEP = INFRA / "modules" / "rbac.bicep"
MAIN_BICEP = INFRA / "main.bicep"
PREVIEW_REGISTER = REPO_ROOT / "docs" / "operations" / "preview-register.md"

ENTRA_MARKER = "<!-- @fragment entra-jwt -->"
CONTENT_SAFETY_MARKER = "<!-- @fragment content-safety -->"

# The current GA Microsoft.ApiManagement API version. A newer GA replaces this
# value; a preview may be used only with a row in the preview register.
APIM_GA_API_VERSION = "2024-05-01"

# Renamed by Microsoft to llm-token-limit and llm-emit-token-metric, which also
# govern non-Azure-OpenAI model APIs.
OBSOLETE_POLICIES = {"azure-openai-token-limit", "azure-openai-emit-token-metric"}

BASE_NAMED_VALUES = {
    "tokens-per-minute-per-user",
    "allowed-workload-ids",
    "trusted-proxy-subscription-ids",
}
ENTRA_NAMED_VALUES = {"entra-openid-config", "entra-audience"}
CONTENT_SAFETY_NAMED_VALUES = {"content-safety-threshold"}

# Azure Monitor custom-metric limit enforced by API Management for this policy.
MAX_CUSTOM_DIMENSIONS = 5


def _compose(*, entra: bool, content_safety: bool) -> str:
    """Mirror the two ``replace()`` calls that build ``policyXml`` in apim.bicep."""
    policy = POLICY.read_text()
    entra_xml = (FRAGMENTS / "entra-jwt.xml").read_text() if entra else ""
    safety_xml = (FRAGMENTS / "content-safety.xml").read_text() if content_safety else ""
    return policy.replace(ENTRA_MARKER, entra_xml).replace(CONTENT_SAFETY_MARKER, safety_xml)


VARIANTS = [
    pytest.param(entra, safety, id=f"entra={entra}-content_safety={safety}")
    for entra, safety in product([False, True], repeat=2)
]


def _parse(entra: bool, content_safety: bool) -> ET.Element:
    return ET.fromstring(_compose(entra=entra, content_safety=content_safety))


def _inbound(root: ET.Element) -> ET.Element:
    inbound = root.find("inbound")
    assert inbound is not None
    return inbound


def test_bicep_composes_the_policy_with_the_markers_this_test_uses() -> None:
    bicep = APIM_BICEP.read_text()
    policy = POLICY.read_text()
    for marker in (ENTRA_MARKER, CONTENT_SAFETY_MARKER):
        assert marker in bicep, f"apim.bicep no longer replaces {marker}"
        assert policy.count(marker) == 1, f"the policy must contain {marker} exactly once"
    assert "loadTextContent('../apim/fragments/entra-jwt.xml')" in bicep
    assert "loadTextContent('../apim/fragments/content-safety.xml')" in bicep


@pytest.mark.parametrize(("entra", "content_safety"), VARIANTS)
def test_every_deployable_policy_variant_is_well_formed_xml(
    entra: bool, content_safety: bool
) -> None:
    assert _parse(entra, content_safety).tag == "policies"


@pytest.mark.parametrize(("entra", "content_safety"), VARIANTS)
def test_the_gateway_uses_the_current_llm_policy_names(entra: bool, content_safety: bool) -> None:
    tags = [element.tag for element in _parse(entra, content_safety).iter()]
    assert not OBSOLETE_POLICIES.intersection(tags)
    assert tags.count("llm-token-limit") == 1
    assert tags.count("llm-emit-token-metric") == 1


@pytest.mark.parametrize(("entra", "content_safety"), VARIANTS)
def test_the_token_budget_is_keyed_on_the_resolved_caller_identity(
    entra: bool, content_safety: bool
) -> None:
    limit = _parse(entra, content_safety).find("inbound/llm-token-limit")
    assert limit is not None
    assert limit.get("counter-key") == '@((string)context.Variables["userId"])'
    assert limit.get("tokens-per-minute") == "{{tokens-per-minute-per-user}}"


@pytest.mark.parametrize(("entra", "content_safety"), VARIANTS)
def test_the_caller_is_resolved_before_the_backend_credential_replaces_authorization(
    entra: bool, content_safety: bool
) -> None:
    children = list(_inbound(_parse(entra, content_safety)))
    resolves_user = next(
        index
        for index, element in enumerate(children)
        if element.tag == "choose"
        and any(v.get("name") == "userId" for v in element.iter("set-variable"))
    )
    backend_token = next(
        index
        for index, element in enumerate(children)
        if element.tag == "authentication-managed-identity"
    )
    overwrite = next(
        index
        for index, element in enumerate(children)
        if element.tag == "set-header" and element.get("name") == "Authorization"
    )
    assert resolves_user < backend_token < overwrite


@pytest.mark.parametrize("content_safety", [False, True])
def test_entra_validation_is_composed_only_when_entra_is_configured(content_safety: bool) -> None:
    without = _compose(entra=False, content_safety=content_safety)
    assert "validate-jwt" not in without
    assert "{{entra-" not in without

    jwt = _parse(True, content_safety).find("inbound/choose/when/validate-jwt")
    assert jwt is not None
    assert jwt.get("require-signed-tokens") == "true"
    assert jwt.get("require-expiration-time") == "true"


@pytest.mark.parametrize(("entra", "content_safety"), VARIANTS)
def test_every_named_value_a_variant_references_is_created_for_that_variant(
    entra: bool, content_safety: bool
) -> None:
    referenced = set(
        re.findall(r"\{\{([a-z0-9-]+)\}\}", _compose(entra=entra, content_safety=content_safety))
    )
    expected = set(BASE_NAMED_VALUES)
    if entra:
        expected |= ENTRA_NAMED_VALUES
    if content_safety:
        expected |= CONTENT_SAFETY_NAMED_VALUES
    assert referenced == expected

    bicep = APIM_BICEP.read_text()
    for name in expected:
        assert f"name: '{name}'" in bicep, f"apim.bicep does not create named value {name}"


@pytest.mark.parametrize(("entra", "content_safety"), VARIANTS)
def test_token_metrics_carry_only_bounded_dimensions(entra: bool, content_safety: bool) -> None:
    metric = _parse(entra, content_safety).find("inbound/llm-emit-token-metric")
    assert metric is not None
    names = [dimension.get("name", "") for dimension in metric.iter("dimension")]
    assert 0 < len(names) <= MAX_CUSTOM_DIMENSIONS
    # API Management keeps 100 values per dimension and silently drops the
    # rest, so a per-user or per-request dimension loses data without error.
    unbounded = [n for n in names if re.search(r"user|correlation|request|ip", n, re.IGNORECASE)]
    assert unbounded == []


def test_the_workload_dimension_is_bounded_by_a_registered_allowlist() -> None:
    policy = POLICY.read_text()
    assert '"{{allowed-workload-ids}}"' in policy
    assert '"unregistered"' in policy


def test_content_safety_is_off_unless_an_operator_switches_it_on() -> None:
    assert "llm-content-safety" not in _compose(entra=True, content_safety=False)
    assert "param enableContentSafety bool = false" in APIM_BICEP.read_text()
    assert "param enableContentSafety bool = false" in MAIN_BICEP.read_text()


@pytest.mark.parametrize("entra", [False, True])
def test_content_safety_moderates_prompt_attacks_and_completions_when_enabled(
    entra: bool,
) -> None:
    root = _parse(entra, True)
    safety = root.find("inbound/llm-content-safety")
    assert safety is not None
    assert safety.get("shield-prompt") == "true"
    assert safety.get("enforce-on-completions") == "true"
    categories = {c.get("name") for c in safety.iter("category")}
    assert categories == {"Hate", "SelfHarm", "Sexual", "Violence"}
    assert f"name: '{safety.get('backend-id')}'" in APIM_BICEP.read_text()

    children = [element.tag for element in _inbound(root)]
    assert children.index("llm-content-safety") < children.index("set-backend-service")


@pytest.mark.parametrize(("entra", "content_safety"), VARIANTS)
def test_semantic_caching_never_appears_on_the_entitlement_scoped_route(
    entra: bool, content_safety: bool
) -> None:
    tags = {element.tag for element in _parse(entra, content_safety).iter()}
    assert not {t for t in tags if "semantic-cache" in t or t.startswith("cache-")}


def test_a_request_that_names_no_api_version_is_refused() -> None:
    root = _parse(False, False)
    refusal = next(
        when
        for when in root.iter("when")
        if "api-version" in when.get("condition", "") and when.find("return-response") is not None
    )
    status = refusal.find("return-response/set-status")
    assert status is not None
    assert status.get("code") == "400"
    assert re.search(r"name: 'api-version', type: 'string', required: true", APIM_BICEP.read_text())


def test_the_backend_is_selected_explicitly_so_its_circuit_breaker_applies() -> None:
    selected = _parse(False, False).find("inbound/set-backend-service")
    assert selected is not None
    assert selected.get("backend-id") == "foundry"
    bicep = APIM_BICEP.read_text()
    assert "circuitBreaker:" in bicep
    assert "acceptRetryAfter: true" in bicep


def test_one_throttled_deployment_cannot_trip_the_breaker_for_every_deployment() -> None:
    # One backend serves all deployments, so a 429-triggered trip would let a
    # single caller cut everyone off by exhausting one small deployment.
    ranges = re.findall(r"\{ min: (\d+), max: (\d+) \}", APIM_BICEP.read_text())
    assert ranges, "no circuit-breaker status ranges found; the scan is broken"
    assert all(not int(low) <= 429 <= int(high) for low, high in ranges)


def _user_id_assignments(root: ET.Element) -> list[tuple[str, str]]:
    """(branch condition, assigned value) for every way the policy sets userId."""
    found = []
    for branch in root.iter():
        if branch.tag not in {"when", "otherwise"}:
            continue
        for assignment in branch.findall("set-variable"):
            if assignment.get("name") == "userId":
                found.append((branch.get("condition", ""), assignment.get("value", "")))
    return found


@pytest.mark.parametrize(("entra", "content_safety"), VARIANTS)
def test_only_a_registered_proxy_subscription_can_name_the_user(
    entra: bool, content_safety: bool
) -> None:
    assignments = _user_id_assignments(_parse(entra, content_safety))
    from_header = [(c, v) for c, v in assignments if '"x-user-id"' in v]
    assert len(from_header) == 1
    condition, _ = from_header[0]
    assert "{{trusted-proxy-subscription-ids}}" in condition
    assert "context.Subscription" in condition


@pytest.mark.parametrize(("entra", "content_safety"), VARIANTS)
def test_each_identity_source_has_its_own_budget_key_prefix(
    entra: bool, content_safety: bool
) -> None:
    # APIM subscription ids cannot contain ':', so `sub:<id>` can never be
    # spelled as `sub:<id>:user:<name>`, and neither can be spelled as `oid:`.
    values = [value for _, value in _user_id_assignments(_parse(entra, content_safety))]
    assert all(v.startswith(('@("oid:"', '@("sub:"')) for v in values)
    named_by_proxy = [v for v in values if '":user:"' in v]
    assert len(named_by_proxy) == 1
    assert '"x-user-id"' in named_by_proxy[0]
    assert any(v.startswith('@("oid:"') for v in values) is entra


def test_no_proxy_is_trusted_unless_an_operator_names_one() -> None:
    bicep = APIM_BICEP.read_text()
    assert "param trustedProxySubscriptionIds string[] = []" in bicep
    assert "empty(trustedProxySubscriptionIds) ? 'none'" in bicep
    assert "param trustedProxySubscriptionIds string[] = []" in MAIN_BICEP.read_text()


def test_gateway_resources_are_on_ga_unless_the_preview_is_registered() -> None:
    register = PREVIEW_REGISTER.read_text()
    found = []
    for path in INFRA.rglob("*.bicep"):
        found += re.findall(r"'(Microsoft\.ApiManagement/[\w/]+)@([\w-]+)'", path.read_text())
    assert found, "no API Management resources found; the scan is broken"
    unregistered = [
        f"{kind}@{version}"
        for kind, version in found
        if version != APIM_GA_API_VERSION and f"`{kind}` | `{version}`" not in register
    ]
    assert unregistered == []


def test_prompts_and_completions_are_never_logged() -> None:
    bicep = APIM_BICEP.read_text()
    assert "var noBody = { bytes: 0 }" in bicep
    bodies = re.findall(r"body:\s*([\w{}: ]+?)\s*}", bicep)
    assert bodies, "no diagnostic body settings found; the scan is broken"
    assert set(bodies) == {"noBody"}
    # Prompt and completion logging exists only on preview API versions.
    assert "largeLanguageModel" not in bicep


def test_every_logged_attribution_header_is_one_the_policy_actually_emits() -> None:
    match = re.search(r"var attributionHeaders = \[([^\]]+)\]", APIM_BICEP.read_text())
    assert match is not None
    logged = set(re.findall(r"'([\w-]+)'", match.group(1)))
    root = _parse(False, False)
    outbound = root.find("outbound")
    assert outbound is not None
    emitted = {header.get("name") for header in outbound.iter("set-header")}
    limit = root.find("inbound/llm-token-limit")
    assert limit is not None
    emitted.add(limit.get("tokens-consumed-header-name"))
    assert logged <= emitted


def test_the_gateway_identity_can_only_infer_moderate_and_publish_metrics() -> None:
    blocks = re.split(r"\nresource ", RBAC_BICEP.read_text())
    granted = {
        role
        for block in blocks
        if "principalId: apimPrincipalId" in block
        for role in re.findall(r"roleIds\.(\w+)\)", block)
    }
    assert granted == {
        "cognitiveServicesOpenAiUser",
        "cognitiveServicesUser",
        "monitoringMetricsPublisher",
    }
    moderation = next(
        b for b in blocks if "roleIds.cognitiveServicesUser)" in b and "apimPrincipalId" in b
    )
    assert "enableContentSafety" in moderation.splitlines()[0]


def test_legacy_tls_is_disabled_with_the_key_names_api_management_honours() -> None:
    bicep = APIM_BICEP.read_text()
    prefix = "Microsoft.WindowsAzure.ApiManagement.Gateway.Security"
    # The singular `Protocol` form is stored by the service and has no effect.
    assert f"{prefix}.Protocol." not in bicep
    assert f"{prefix}.Backend.Protocol." not in bicep
    for side in ("", "Backend."):
        for protocol in ("Tls10", "Tls11", "Ssl30"):
            assert f"'{prefix}.{side}Protocols.{protocol}': 'False'" in bicep
