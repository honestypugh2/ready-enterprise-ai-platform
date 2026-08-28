"""The HTTP surface, end to end.

The API is where the architecture becomes someone else's dependency, so these
tests cover the contract rather than the internals: status codes that mean what
they say, a correlation id that survives the round trip, security headers on
every response, and an approval flow that is genuinely two requests.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(api_client: Any) -> TestClient:
    return api_client  # type: ignore[return-value]


def run_scenario(client: TestClient, scenario_id: str, **headers: str) -> dict[str, Any]:
    response = client.post(
        "/v1/inspections/scenario", json={"scenario_id": scenario_id}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestHealthProbes:
    def test_liveness_does_not_depend_on_downstream_planes(self, client: TestClient) -> None:
        """A liveness probe that calls dependencies restarts a healthy replica
        because something else is down."""
        assert client.get("/livez").status_code == 200

    def test_readiness_reports_each_plane_separately(self, client: TestClient) -> None:
        body = client.get("/readyz").json()
        assert set(body.get("planes", body)) >= {"detector", "retrieval", "reasoning"}

    def test_health_declares_the_execution_mode(self, client: TestClient) -> None:
        """Every response says whether it came from mocks or from Azure. A demo
        that does not name its mode invites the audience to assume the wrong one."""
        body = client.get("/healthz").json()
        assert body["mode"] == "local_mock"


class TestRequestHygiene:
    def test_a_supplied_correlation_id_is_echoed_back(self, client: TestClient) -> None:
        response = client.get("/healthz", headers={"x-correlation-id": "corr-abcdef123456"})
        assert response.headers["x-correlation-id"] == "corr-abcdef123456"

    def test_a_hostile_correlation_id_is_replaced_not_reflected(self, client: TestClient) -> None:
        """An unvalidated header lands in logs and traces, which makes it an
        injection surface for whatever reads them."""
        response = client.get("/healthz", headers={"x-correlation-id": "<script>alert(1)</script>"})
        assert response.headers["x-correlation-id"].startswith("corr_")

    def test_security_headers_are_present_on_every_response(self, client: TestClient) -> None:
        headers = client.get("/healthz").headers
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["X-Frame-Options"] == "DENY"
        assert "default-src 'none'" in headers["Content-Security-Policy"]
        assert headers["Cache-Control"] == "no-store"

    def test_an_unknown_field_is_rejected_rather_than_ignored(self, client: TestClient) -> None:
        """``extra="forbid"`` on the wire contract. Silently ignoring a field a
        caller sent is how a client ships a bug it cannot see."""
        response = client.post(
            "/v1/inspections/scenario",
            json={"scenario_id": "major-defect", "force_approve": True},
        )
        assert response.status_code == 422

    def test_a_malformed_frame_hash_is_rejected_at_the_boundary(self, client: TestClient) -> None:
        response = client.post(
            "/v1/inspections",
            json={
                "line_id": "DEMO-L1",
                "station_id": "ST-07",
                "product_sku": "SKU-88421",
                "frame_hash": "not-a-hash",
            },
        )
        assert response.status_code == 422

    def test_an_unknown_scenario_is_a_404_not_a_500(self, client: TestClient) -> None:
        response = client.post("/v1/inspections/scenario", json={"scenario_id": "does-not-exist"})
        assert response.status_code == 404


class TestInspectionResponseIsSelfDescribing:
    def test_the_response_carries_the_whole_transaction(self, client: TestClient) -> None:
        body = run_scenario(client, "major-defect")
        for section in ("detection", "route", "evidence", "recommendation", "policy", "audit"):
            assert body[section] is not None, section

    def test_the_detection_names_its_model_and_threshold(self, client: TestClient) -> None:
        body = run_scenario(client, "major-defect")
        detection = body["detection"]
        assert detection["model_version"]
        assert detection["threshold"] == pytest.approx(0.62)
        assert detection["execution_location"] == "mock"

    def test_the_policy_result_names_the_rule_that_fired(self, client: TestClient) -> None:
        """ "The model decided" is not an audit answer. A rule id is."""
        body = run_scenario(client, "major-defect")
        assert "R040-safety-relevant-major" in body["policy"]["matched_rules"]
        assert body["policy"]["policy_version"]
        assert body["policy"]["policy_sha"].startswith("sha256:")

    def test_the_audit_chain_reports_its_own_verification(self, client: TestClient) -> None:
        body = run_scenario(client, "major-defect")
        assert body["audit"]["chain_verified"] is True
        assert body["audit"]["steps"]

    def test_no_evidence_passage_text_is_returned_on_the_wire(self, client: TestClient) -> None:
        """Citations reference the evidence store; they do not copy it. The
        passage a caller may read is decided by the store's access control, not
        by whoever called this endpoint."""
        body = run_scenario(client, "major-defect")
        for item in body["evidence"]["items"]:
            assert "passage" not in item

    def test_cost_is_reported_without_a_currency_figure(self, client: TestClient) -> None:
        body = run_scenario(client, "major-defect")
        cost = body["cost"]
        assert cost["estimated_total"] is None
        assert cost["currency"] == "UNSPECIFIED"
        assert cost["units_by_surface"]


class TestApprovalFlowIsTwoRequests:
    def test_a_gated_transaction_stops_and_returns_an_approval(self, client: TestClient) -> None:
        body = run_scenario(client, "major-defect")
        assert body["status"] == "awaiting_approval"
        assert body["action"] is None
        assert body["approval"]["state"] == "pending"

    def test_the_approval_surface_carries_evidence_not_just_a_summary(
        self, client: TestClient
    ) -> None:
        """An approver asked to click "approve" on a sentence is a rubber stamp
        with a name attached."""
        body = run_scenario(client, "major-defect")
        approval = body["approval"]
        assert approval["evidence"]
        assert approval["proposal_fingerprint"].startswith("sha256:")
        assert approval["expires_at"]

    def test_a_decision_completes_the_transaction(self, client: TestClient) -> None:
        created = run_scenario(client, "major-defect")
        approval_id = created["approval"]["approval_id"]

        response = client.post(
            f"/v1/approvals/{approval_id}/decision",
            json={
                "approver_principal_id": "synthetic-approver-1",
                "approver_role": "maintenance_lead",
                "decision": "approved",
                "rationale": "Evidence, policy result and downstream effect reviewed.",
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "completed"
        # Local mode: a receipt, never a record.
        assert body["action"]["status"] == "dry_run"

    def test_the_requester_cannot_approve_their_own_proposal(self, client: TestClient) -> None:
        created = run_scenario(client, "major-defect")
        approval_id = created["approval"]["approval_id"]

        response = client.post(
            f"/v1/approvals/{approval_id}/decision",
            json={
                "approver_principal_id": "synthetic-operator-001",
                "approver_role": "maintenance_lead",
                "decision": "approved",
                "rationale": "approving my own request",
            },
        )
        assert response.status_code == 403

    def test_dual_control_needs_two_calls_from_two_principals(self, client: TestClient) -> None:
        created = run_scenario(client, "critical-defect")
        approval_id = created["approval"]["approval_id"]
        payload = {
            "approver_principal_id": "synthetic-approver-1",
            "approver_role": "plant_manager",
            "decision": "approved",
            "rationale": "First of two approvals; evidence reviewed.",
        }

        first = client.post(f"/v1/approvals/{approval_id}/decision", json=payload)
        assert first.status_code == 200
        assert first.json()["status"] != "completed"

        second = client.post(
            f"/v1/approvals/{approval_id}/decision",
            json={**payload, "approver_principal_id": "synthetic-approver-2"},
        )
        assert second.status_code == 200
        assert second.json()["status"] == "completed"

    def test_an_unknown_approval_is_a_404(self, client: TestClient) -> None:
        response = client.post(
            "/v1/approvals/does-not-exist/decision",
            json={
                "approver_principal_id": "synthetic-approver-1",
                "approver_role": "maintenance_lead",
                "decision": "approved",
                "rationale": "no such approval",
            },
        )
        assert response.status_code == 404

    def test_pending_approvals_are_listable(self, client: TestClient) -> None:
        run_scenario(client, "major-defect")
        listed = client.get("/v1/approvals").json()
        assert listed
        assert all("proposal_fingerprint" not in row for row in listed)


class TestTransactionRetrieval:
    def test_a_transaction_can_be_fetched_by_correlation_id(self, client: TestClient) -> None:
        created = run_scenario(client, "major-defect")
        fetched = client.get(f"/v1/inspections/{created['correlation_id']}")
        assert fetched.status_code == 200
        assert fetched.json()["correlation_id"] == created["correlation_id"]

    def test_an_unknown_correlation_id_is_a_404(self, client: TestClient) -> None:
        assert client.get("/v1/inspections/corr-nope").status_code == 404


class TestGovernanceEndpoints:
    def test_the_active_policy_is_inspectable(self, client: TestClient) -> None:
        """Policy that cannot be read is policy that cannot be reviewed."""
        body = client.get("/v1/governance/policy").json()
        assert body["version"]
        assert body["sha"].startswith("sha256:")
        assert body["rules"]

    def test_the_routing_policy_is_inspectable(self, client: TestClient) -> None:
        body = client.get("/v1/governance/routing-policy").json()
        assert body["version"]
        assert body["candidates"]

    def test_the_readiness_scorecard_is_published(self, client: TestClient) -> None:
        body = client.get("/v1/governance/readyai").json()
        assert "dimensions" in body

    def test_an_audit_receipt_is_retrievable_by_correlation_id(self, client: TestClient) -> None:
        created = run_scenario(client, "major-defect")
        body = client.get(f"/v1/governance/audit/{created['correlation_id']}").json()
        assert body["chain_verified"] is True
