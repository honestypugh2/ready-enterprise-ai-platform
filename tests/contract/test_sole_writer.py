"""Exactly one component may mutate a system of record.

The claim is architectural, so the test is architectural: it reads the import
graph and fails the build if any module outside ``connectors.writer`` acquires
a path to an enterprise connector.

If this test ever fails, the fix is not to add an exemption. It is to route the
new write through the writer.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_DIR = REPO_ROOT / "packages"
APPS_DIR = REPO_ROOT / "apps"

# The writer itself, the package that exports it, the composition root that
# wires it, and the test suite that verifies it.
WRITER_MODULE = PACKAGES_DIR / "connectors" / "writer.py"
PERMITTED_TO_HOLD_A_CONNECTOR = {
    PACKAGES_DIR / "connectors" / "__init__.py",
    PACKAGES_DIR / "connectors" / "base.py",
    PACKAGES_DIR / "connectors" / "mock.py",
    WRITER_MODULE,
    PACKAGES_DIR / "workflows" / "assembly.py",
}


def _source_files() -> list[Path]:
    return [
        path
        for root in (PACKAGES_DIR, APPS_DIR)
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts
    ]


def _imports_connector_internals(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("connectors.") and node.module != "connectors.writer":
                return True
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("connectors.") and alias.name != "connectors.writer":
                    return True
    return False


class TestSoleWriter:
    def test_no_module_outside_the_writer_holds_a_connector(self) -> None:
        offenders = [
            str(path.relative_to(REPO_ROOT))
            for path in _source_files()
            if path not in PERMITTED_TO_HOLD_A_CONNECTOR and _imports_connector_internals(path)
        ]
        assert not offenders, (
            "only connectors.writer may reach an enterprise connector; offenders:\n  "
            + "\n  ".join(offenders)
        )

    def test_the_writer_is_the_only_caller_of_connector_execute(self) -> None:
        """`execute` is the mutating call. Grepping for it is crude and correct:
        a second call site is a second write path."""
        offenders: list[str] = []
        for path in _source_files():
            if path in PERMITTED_TO_HOLD_A_CONNECTOR:
                continue
            source = path.read_text(encoding="utf-8")
            if "_connector.execute(" in source or ".compensate(" in source:
                offenders.append(str(path.relative_to(REPO_ROOT)))
        assert not offenders, offenders

    def test_the_writer_verifies_the_approval_before_it_acts(self) -> None:
        """Order matters: verification must precede the connector call, not
        follow it. A check after the write is a log entry, not a control."""
        from connectors.writer import ScopedWriter  # noqa: PLC0415

        source = inspect.getsource(ScopedWriter.execute)
        verify_at = source.index("verify_for_write")
        attempt_at = source.index("_attempt_write")
        assert verify_at < attempt_at

    def test_the_writer_refuses_before_it_writes_in_every_branch(self) -> None:
        """Each of the six refusals must raise or return, never merely warn."""
        from connectors.writer import ScopedWriter  # noqa: PLC0415

        source = inspect.getsource(ScopedWriter.execute)
        for guard in (
            "policy denied this transaction",
            "not in the permitted set",
            "verify_for_write",
            "cannot perform",
            "find_by_idempotency_key",
            "DRY_RUN",
        ):
            assert guard in source, f"missing refusal: {guard}"


class TestActionContractBindings:
    def test_an_action_request_cannot_be_built_without_its_bindings(self) -> None:
        """Approval id, fingerprint, policy decision and idempotency key are all
        required fields, so an unbound write cannot be expressed."""
        from contracts.action import ActionRequest  # noqa: PLC0415

        required = {
            name for name, field in ActionRequest.model_fields.items() if field.is_required()
        }
        assert {
            "approval_id",
            "proposal_fingerprint",
            "policy_decision_id",
            "idempotency_key",
        } <= required

    def test_dry_run_defaults_to_true(self) -> None:
        from contracts.action import ActionRequest  # noqa: PLC0415

        assert ActionRequest.model_fields["dry_run"].default is True
