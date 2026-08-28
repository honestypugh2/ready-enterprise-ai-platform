"""Authorization: entitlements at retrieval, roles at approval, identity at the write.

Three separate controls, tested separately, because they fail separately:

* **Retrieval** trims by entitlement and classification *before* scoring, so an
  unentitled document is never ranked and never leaks through a score or a
  "no results for your query" difference.
* **Approvals** enforce role match and separation of duties, so being logged in
  is not the same as being allowed to decide.
* **The writer** re-verifies the binding at execution time, so an authorization
  that was valid at proposal time is not assumed still valid at write time.
"""

from __future__ import annotations

import pytest

from approvals import ApprovalService
from contracts.approval import ApprovalDecision, ApprovalEvidence, ApprovalState
from contracts.common import Classification
from contracts.errors import ApprovalRequiredError
from contracts.retrieval import RetrievalQuery, RetrievalStrategy
from retrieval.local import LocalKnowledgeRetriever
from security.identity import IdentityContext, WorkloadIdentity
from tests.conftest import FIXED_NOW, REPO_ROOT

KNOWLEDGE_DIR = REPO_ROOT / "data" / "knowledge"


@pytest.fixture
def retriever() -> LocalKnowledgeRetriever:
    return LocalKnowledgeRetriever(knowledge_dir=KNOWLEDGE_DIR)


def query_for(identity: IdentityContext, **overrides: object) -> RetrievalQuery:
    defaults: dict[str, object] = {
        "correlation_id": "corr-authorization-test",
        "text": "seal gap disposition and approval requirements",
        "strategy": RetrievalStrategy.HYBRID,
        "entitlement_groups": identity.entitlement_groups,
        "top_k": 20,
    }
    return RetrievalQuery(**{**defaults, **overrides})  # type: ignore[arg-type]


class TestRetrievalEntitlements:
    async def test_two_identities_get_different_answers_from_one_index(
        self, retriever: LocalKnowledgeRetriever
    ) -> None:
        """The demonstration that matters: entitlement is a property of the
        caller, not of the index, and one corpus serves both correctly."""
        operator = IdentityContext.local_demo_operator()
        approver = IdentityContext.local_demo_approver("maintenance_lead")

        operator_result = await retriever.search(query_for(operator))
        approver_result = await retriever.search(query_for(approver))

        operator_sources = {item.source_id for item in operator_result.items}
        approver_sources = {item.source_id for item in approver_result.items}
        assert operator_sources < approver_sources

    async def test_empty_entitlements_means_entitled_to_nothing(
        self, retriever: LocalKnowledgeRetriever
    ) -> None:
        """The default that has caused real breaches is "no groups means no
        filter". Here it means no documents."""
        result = await retriever.search(
            RetrievalQuery(
                correlation_id="corr-empty-entitlements",
                text="seal gap disposition",
                entitlement_groups=frozenset(),
                top_k=20,
            )
        )
        assert result.items == ()
        assert result.trimmed_count > 0

    async def test_classification_ceiling_is_applied_independently_of_groups(
        self, retriever: LocalKnowledgeRetriever
    ) -> None:
        """Being in the group is not sufficient. A caller operating at INTERNAL
        cannot pull a CONFIDENTIAL passage even from a corpus they can read."""
        approver = IdentityContext.local_demo_approver("maintenance_lead")
        unrestricted = await retriever.search(query_for(approver))
        restricted = await retriever.search(
            query_for(approver, max_classification=Classification.INTERNAL)
        )

        confidential = {
            item.source_id
            for item in unrestricted.items
            if item.classification is Classification.CONFIDENTIAL
        }
        assert confidential, "fixture no longer contains a confidential passage"
        assert not confidential & {item.source_id for item in restricted.items}

    async def test_trimming_happens_before_scoring_not_after_ranking(
        self, retriever: LocalKnowledgeRetriever
    ) -> None:
        """If filtering happened after top-k, a restricted document would
        consume a slot and the entitled caller would silently get fewer
        results. Asking for one result must return one real result."""
        approver = IdentityContext.local_demo_approver("maintenance_lead")
        narrow = await retriever.search(query_for(approver, top_k=1))
        assert len(narrow.items) == 1

    async def test_an_unentitled_document_never_appears_with_a_score(
        self, retriever: LocalKnowledgeRetriever
    ) -> None:
        operator = IdentityContext.local_demo_operator()
        result = await retriever.search(query_for(operator))
        for item in result.items:
            assert item.access_groups & operator.entitlement_groups


class TestApprovalAuthorization:
    @staticmethod
    async def _pending(service: ApprovalService, *, dual: bool = False):
        return await service.request(
            correlation_id="corr-approval-authz",
            policy_decision_id="pol_authz_test",
            proposal_fingerprint="sha256:" + "a" * 64,
            requested_by="synthetic-operator-001",
            required_role="maintenance_lead",
            dual_control_required=dual,
            proposed_action_summary="raise a maintenance work order",
            evidence=ApprovalEvidence(
                citations=("MS-118",),
                authoritative_values=(("label", "seal_gap"),),
                policy_reason_codes=("SAFETY_RELEVANT_MAJOR_DEFECT",),
                expected_downstream_effect="create_work_order in mock-erp",
                detection_summary="Seal gap at 88% confidence",
            ),
            now=FIXED_NOW,
        )

    @staticmethod
    def _decision(principal: str, *, role: str = "maintenance_lead") -> ApprovalDecision:
        return ApprovalDecision(
            approver_principal_id=principal,
            approver_role=role,
            state=ApprovalState.APPROVED,
            rationale="Evidence, policy result and downstream effect reviewed.",
            decided_at=FIXED_NOW,
        )

    async def test_the_wrong_role_cannot_approve(self, approvals: ApprovalService) -> None:
        record = await self._pending(approvals)
        with pytest.raises(ApprovalRequiredError):
            await approvals.decide(
                record.approval_id,
                self._decision("synthetic-approver-op", role="line_operator"),
                now=FIXED_NOW,
            )

    async def test_the_requester_cannot_approve_their_own_proposal(
        self, approvals: ApprovalService
    ) -> None:
        """Separation of duties. The most commonly skipped control, and the one
        an auditor asks about first."""
        record = await self._pending(approvals)
        with pytest.raises(ApprovalRequiredError):
            await approvals.decide(
                record.approval_id, self._decision("synthetic-operator-001"), now=FIXED_NOW
            )

    async def test_dual_control_needs_two_distinct_principals(
        self, approvals: ApprovalService
    ) -> None:
        record = await self._pending(approvals, dual=True)

        record = await approvals.decide(
            record.approval_id, self._decision("approver-one"), now=FIXED_NOW
        )
        assert record.state is ApprovalState.PENDING
        assert not record.state.permits_write

        record = await approvals.decide(
            record.approval_id, self._decision("approver-two"), now=FIXED_NOW
        )
        assert record.state is ApprovalState.APPROVED

    async def test_the_same_principal_twice_does_not_satisfy_dual_control(
        self, approvals: ApprovalService
    ) -> None:
        """Two clicks from one person is one person. This is the bug that makes
        a dual-control feature decorative."""
        record = await self._pending(approvals, dual=True)
        record = await approvals.decide(
            record.approval_id, self._decision("approver-one"), now=FIXED_NOW
        )
        record = await approvals.decide(
            record.approval_id, self._decision("approver-one"), now=FIXED_NOW
        )
        assert record.state is ApprovalState.PENDING


class TestWorkloadIdentitySeparation:
    def test_every_plane_has_its_own_identity(self) -> None:
        """A shared service principal makes an audit log say "the platform did
        it". Distinct identities are what make attribution possible and what
        keep a compromised reasoning path unable to write."""
        values = {identity.value for identity in WorkloadIdentity}
        assert len(values) == len(WorkloadIdentity)
        assert WorkloadIdentity.REASONING_CLIENT != WorkloadIdentity.SCOPED_WRITER

    def test_local_mode_uses_no_credential_at_all(self, settings) -> None:
        from security.identity import resolve_credential  # noqa: PLC0415

        assert resolve_credential(settings, identity=WorkloadIdentity.API) is None

    def test_the_demo_identity_is_labelled_synthetic(self) -> None:
        """A demo identity that looks like a real person ends up quoted in a
        deck as a real person."""
        operator = IdentityContext.local_demo_operator()
        assert operator.principal_id.startswith("synthetic-")
        assert "Demo" in operator.display_name


class TestApiIdentityIsNotAuthentication:
    def test_the_header_based_identity_is_documented_as_a_demo_control(self) -> None:
        """The header selects a persona so the entitlement demonstration works
        offline. If this ever stops being labelled, someone will ship it."""
        import inspect  # noqa: PLC0415

        from api.dependencies import get_identity  # noqa: PLC0415

        doc = inspect.getdoc(get_identity) or ""
        assert "not authentication" in doc.lower()

    def test_an_unknown_role_header_does_not_grant_operator_privileges(self) -> None:
        from api.dependencies import get_identity  # noqa: PLC0415

        identity = get_identity(x_demo_role="plant_manager")
        assert identity.roles == frozenset({"plant_manager"})
        assert "line_operator" not in identity.roles
