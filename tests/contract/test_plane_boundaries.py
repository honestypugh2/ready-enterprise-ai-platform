"""Architectural boundaries, enforced rather than described.

Every rule in this file is a claim the README makes. A claim about architecture
that nothing checks is a claim that decays on the first busy Friday.

The checks are static: they read the import graph rather than executing code,
so a violation is caught even on a path no test happens to exercise.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_DIR = REPO_ROOT / "packages"
APPS_DIR = REPO_ROOT / "apps"

PLANES = {
    "contracts",
    "detector",
    "predictive_models",
    "events",
    "model_router",
    "retrieval",
    "reasoning",
    "workflows",
    "policy_engine",
    "approvals",
    "connectors",
    "audit",
    "observability",
    "evaluation",
    "security",
    "cost_attribution",
    "platform_config",
    "readyai",
    "cli",
}

# A plane may depend on contracts, on shared infrastructure, and on the specific
# planes named here. Anything else is a boundary violation.
ALLOWED_DEPENDENCIES: dict[str, set[str]] = {
    "contracts": set(),
    "platform_config": set(),
    "security": {"platform_config"},
    "observability": {"security", "platform_config"},
    "detector": {"platform_config"},
    "predictive_models": {"platform_config"},
    "events": {"observability", "platform_config", "security"},
    "retrieval": {"security", "observability", "platform_config"},
    "reasoning": {"security", "observability", "platform_config", "retrieval"},
    "model_router": {"observability", "platform_config"},
    "policy_engine": set(),
    "approvals": set(),
    "audit": {"security"},
    "connectors": {"approvals"},
    "cost_attribution": set(),
    # The orchestrator is the one place permitted to know about everything.
    "workflows": PLANES - {"workflows", "evaluation", "readyai", "cli"},
    "evaluation": PLANES - {"evaluation", "readyai", "cli"},
    "readyai": set(),
    "cli": PLANES - {"cli"},
}


def _python_files(root: Path) -> Iterator[Path]:
    for path in root.rglob("*.py"):
        if "__pycache__" not in path.parts:
            yield path


def _imported_top_level_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module.split(".")[0])
    return modules


def _plane_of(path: Path) -> str:
    return path.relative_to(PACKAGES_DIR).parts[0]


class TestPlaneBoundaries:
    @pytest.mark.parametrize("plane", sorted(PLANES))
    def test_plane_imports_only_what_it_is_allowed_to(self, plane: str) -> None:
        """A plane may depend on `contracts`; it may not reach into another
        plane's internals. That rule is what makes each plane independently
        reviewable, testable and replaceable."""
        plane_dir = PACKAGES_DIR / plane
        if not plane_dir.is_dir():
            pytest.skip(f"{plane} is not present")

        permitted = ALLOWED_DEPENDENCIES[plane] | {"contracts", plane}
        violations: list[str] = []

        for path in _python_files(plane_dir):
            for module in _imported_top_level_modules(path):
                if module in PLANES and module not in permitted:
                    violations.append(f"{path.relative_to(REPO_ROOT)} imports '{module}'")

        assert not violations, (
            f"plane '{plane}' may depend on {sorted(permitted)} but also imports:\n  "
            + "\n  ".join(violations)
        )

    def test_contracts_depends_on_no_other_plane(self) -> None:
        """Contracts is the shared vocabulary. If it depended on a plane, every
        plane would transitively depend on that one."""
        for path in _python_files(PACKAGES_DIR / "contracts"):
            imported = _imported_top_level_modules(path)
            assert not (imported & (PLANES - {"contracts"})), path.name

    def test_every_plane_declares_a_public_interface(self) -> None:
        """`__all__` is the boundary. Without it, every symbol is public by
        accident and refactoring a private helper becomes a breaking change."""
        missing: list[str] = []
        for plane in sorted(PLANES):
            init = PACKAGES_DIR / plane / "__init__.py"
            if not init.is_file():
                continue
            tree = ast.parse(init.read_text(encoding="utf-8"))
            declares = any(
                isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets)
                for node in tree.body
            )
            if not declares:
                missing.append(plane)
        assert not missing, f"planes without __all__: {missing}"

    def test_no_plane_is_left_as_a_placeholder(self) -> None:
        placeholders = [
            plane
            for plane in sorted(PLANES)
            if (PACKAGES_DIR / plane / "__init__.py").is_file()
            and "Placeholder" in (PACKAGES_DIR / plane / "__init__.py").read_text("utf-8")
        ]
        assert not placeholders, f"unimplemented planes: {placeholders}"


class TestReasoningCannotDecide:
    def test_the_reasoning_plane_cannot_import_the_writer_or_approvals(self) -> None:
        """The model proposes and explains. It has no path to permit or perform."""
        forbidden = {"connectors", "approvals", "policy_engine"}
        for path in _python_files(PACKAGES_DIR / "reasoning"):
            assert not (_imported_top_level_modules(path) & forbidden), path.name

    def test_the_recommendation_contract_has_no_verdict_field(self) -> None:
        """Enforced by the shape of the contract rather than by prompt text."""
        from contracts.reasoning import Recommendation  # noqa: PLC0415

        fields = set(Recommendation.model_fields)
        forbidden = {
            "approved",
            "approval",
            "severity",
            "disposition",
            "allowed",
            "permitted_actions",
            "external_reference",
        }
        assert not (fields & forbidden), f"reasoning must not carry a verdict: {fields & forbidden}"


class TestAppBoundaries:
    def test_apps_do_not_reach_past_the_composition_root(self) -> None:
        """The API and the worker consume the assembled platform. Wiring lives in
        one place so that no entry point ends up without the kill switch."""
        forbidden = {"policy_engine", "connectors", "approvals", "detector"}
        offenders: list[str] = []
        for path in _python_files(APPS_DIR):
            # Routers legitimately read approval state; they cannot write.
            if path.name in {"approvals.py", "governance.py"}:
                continue
            for module in _imported_top_level_modules(path) & forbidden:
                offenders.append(f"{path.relative_to(REPO_ROOT)} imports '{module}'")
        assert not offenders, "\n".join(offenders)
