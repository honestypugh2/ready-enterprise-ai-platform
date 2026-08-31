"""``reap`` — the demonstration and operations CLI.

The commands here are the same code paths the API uses, on purpose. A demo that
runs through a special "demo mode" proves nothing about the platform; this one
drives the real workflow, the real policy engine and the real writer.

Built on ``argparse`` rather than a CLI framework so the demonstration has no
dependency that could fail to resolve on a locked-down machine.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from cli.azure_demo import index_demo_corpus, run_preflight
from cli.render import bullet, field, heading, style, table, verdict
from cli.scenarios import DemoScenario, get_scenario, load_scenarios
from contracts.approval import ApprovalDecision, ApprovalState
from contracts.audit import AuditReceipt
from cost_attribution import RateCard
from platform_config import ExecutionMode, PlatformSettings, get_settings
from retrieval import AzureSearchRetriever
from security.identity import IdentityContext
from workflows import WorkflowOutcome, build_platform

EXIT_OK = 0
EXIT_GATE_FAILED = 1
EXIT_USAGE = 2


# ---------------------------------------------------------------------------
# demo
# ---------------------------------------------------------------------------


def _print_banner(settings: PlatformSettings) -> None:
    mode_colour = "green" if settings.mode is ExecutionMode.LOCAL_MOCK else "yellow"
    print(heading("ready-enterprise-ai-platform"))
    print(field("execution mode", settings.mode.value, colour=mode_colour))
    print(field("detector", settings.detector.provider))
    print(field("retrieval", settings.retrieval.provider))
    print(field("reasoning", settings.reasoning.provider))
    print(
        field(
            "connector",
            f"{settings.connector.provider} (dry_run={settings.connector.dry_run})",
        )
    )
    if settings.mode is ExecutionMode.LOCAL_MOCK:
        print(
            style(
                "  All planes are mocked. Nothing here reaches a network or writes a record.",
                "dim",
            )
        )


def _print_detection(outcome: WorkflowOutcome) -> None:
    detection = outcome.detection
    print(heading("1-2  Detect  ·  specialized model"))
    if detection is None:
        print(bullet(style("no detection was produced", "red")))
        return
    above = detection.primary_confidence >= detection.decision_threshold
    print(field("label", detection.primary_label, colour="bold"))
    print(
        field(
            "confidence",
            f"{detection.primary_confidence:.3f} (threshold {detection.decision_threshold:.2f})",
            colour="green" if above else "yellow",
        )
    )
    print(field("model", f"{detection.model_name} v{detection.model_version}"))
    print(field("executed", detection.execution_location.value))
    print(field("latency", f"{detection.latency_ms:.1f} ms"))
    print(field("input hash", detection.input_hash[:26] + "…"))
    print(style("  The detector produced a signal. It decided nothing.", "dim"))


def _print_route(outcome: WorkflowOutcome) -> None:
    route = outcome.route
    print(heading("3  Route  ·  why this component answered"))
    if route is None:
        print(bullet("no routing decision recorded"))
        return
    print(field("selected", f"{route.selected_route} ({route.selected_kind.value})", colour="bold"))
    print(field("reason codes", ", ".join(route.reason_codes)))
    sha = f" · {route.policy_sha[:18]}…" if route.policy_sha else ""
    print(field("policy version", f"{route.policy_version}{sha}"))
    print(field("cost category", route.cost_category.value))
    print(field("latency target", f"{route.latency_target_ms} ms"))
    if route.excluded:
        print(style("  excluded candidates:", "dim"))
        for exclusion in route.excluded:
            print(f"      {exclusion.route_id:<28} {style(exclusion.reason_code, 'yellow')}")


def _print_evidence(outcome: WorkflowOutcome) -> None:
    evidence = outcome.evidence
    print(heading("4  Retrieve  ·  governed evidence"))
    if evidence is None or evidence.is_empty:
        print(bullet(style("no evidence retrieved", "yellow")))
        return
    print(field("strategy", evidence.strategy.value))
    print(field("index", f"{evidence.index_name} v{evidence.index_version}"))
    print(field("returned / trimmed", f"{len(evidence.items)} / {evidence.trimmed_count}"))
    print(
        table(
            (
                (
                    item.citation_ref,
                    item.source_id,
                    item.authority,
                    item.classification.value,
                    f"{item.score:.3f}",
                )
                for item in evidence.items
            ),
            headers=("ref", "source", "authority", "class", "score"),
        )
    )
    if evidence.trimmed_count:
        print(
            style(
                f"  {evidence.trimmed_count} passage(s) trimmed at query time by entitlement.",
                "dim",
            )
        )


def _print_recommendation(outcome: WorkflowOutcome) -> None:
    recommendation = outcome.recommendation
    print(heading("5  Explain  ·  where the language model earns its place"))
    if recommendation is None:
        print(bullet("no recommendation generated"))
        return
    if recommendation.refused:
        print(field("refused", recommendation.refusal_reason, colour="yellow"))
        return
    print(field("headline", recommendation.headline, colour="bold"))
    print(field("model", f"{recommendation.model_name} via {recommendation.route_id}"))
    print(field("prompt", f"{recommendation.prompt_id} v{recommendation.prompt_version}"))
    print(field("citations", ", ".join(c.citation_ref for c in recommendation.citations)))
    if outcome.citation_report is not None:
        report = outcome.citation_report
        print(
            field(
                "citation precision",
                f"{report.precision:.2f}",
                colour="green" if report.is_valid else "red",
            )
        )
    print(style("  It explained. It did not decide, calculate or write.", "dim"))


def _print_policy(outcome: WorkflowOutcome) -> None:
    policy = outcome.policy
    print(heading("6-7  Validate  ·  deterministic policy"))
    if policy is None:
        print(bullet("no policy decision recorded"))
        return
    print(field("allowed", policy.allowed, colour="green" if policy.allowed else "red"))
    print(field("severity", policy.severity.value, colour="bold"))
    print(field("disposition", policy.disposition.value, colour="bold"))
    print(field("matched rules", ", ".join(policy.matched_rules)))
    print(field("reason codes", ", ".join(policy.reason_codes)))
    print(field("policy version", f"{policy.policy_version} · {policy.policy_sha[:18]}…"))
    print(
        field(
            "approval required",
            f"{policy.approval_required}"
            + (f" ({policy.approver_role})" if policy.approver_role else "")
            + (" · dual control" if policy.dual_control_required else ""),
            colour="yellow" if policy.approval_required else "green",
        )
    )
    print(field("permitted actions", ", ".join(a.value for a in policy.permitted_actions) or "—"))
    for obligation in policy.obligations:
        print(bullet(f"obligation {obligation.obligation_id}: {obligation.description}"))
    print(style("  This verdict came from code. The model cannot change it.", "dim"))


def _print_approval(outcome: WorkflowOutcome) -> None:
    approval = outcome.approval
    print(heading("8  Supervise  ·  human approval"))
    if approval is None:
        print(bullet(style("not required by policy for this disposition", "green")))
        return
    print(field("approval id", approval.approval_id))
    print(field("state", approval.state.value, colour="yellow"))
    print(field("required role", approval.request.required_role))
    print(field("dual control", approval.request.dual_control_required))
    print(field("expires", approval.request.expires_at.isoformat(timespec="seconds")))
    print(field("fingerprint", approval.proposal_fingerprint[:26] + "…"))
    evidence = approval.request.evidence
    print(style("  the approver sees, as data rather than prose:", "dim"))
    print(bullet(f"detection: {evidence.detection_summary}"))
    print(bullet(f"citations: {', '.join(evidence.citations) or '—'}"))
    print(bullet(f"policy: {', '.join(evidence.policy_reason_codes)}"))
    print(bullet(f"downstream effect: {evidence.expected_downstream_effect}"))
    for name, value in evidence.authoritative_values:
        print(bullet(f"authoritative {name} = {value}"))


def _print_action(outcome: WorkflowOutcome) -> None:
    receipt = outcome.action_receipt
    print(heading("9-10  Act  ·  sole scoped writer"))
    if receipt is None:
        print(bullet("no write was attempted"))
        return
    print(field("status", receipt.status.value, colour="bold"))
    print(field("target system", receipt.target_system))
    print(field("reference", receipt.external_reference or "—"))
    print(field("attempts", receipt.attempts))
    if receipt.error_code:
        print(field("error", f"{receipt.error_code}: {receipt.error_detail}", colour="red"))
    print(
        style(
            "  One service holds the write path. It refused six ways before acting.",
            "dim",
        )
    )


def _print_audit(outcome: WorkflowOutcome) -> None:
    audit = outcome.audit
    print(heading("11  Prove  ·  hash-chained audit receipt"))
    if audit is None:
        print(bullet(style("no audit receipt was sealed", "red")))
        return
    print(field("audit id", audit.audit_id, colour="bold"))
    print(field("correlation id", audit.correlation_id))
    print(field("chain head", audit.chain_head[:26] + "…"))
    print(field("steps", len(audit.steps)))
    print(verdict("chain verifies", ok=audit.verify_chain()))
    print(
        table(
            ((str(s.sequence), s.step_name, s.component, s.outcome) for s in audit.steps),
            headers=("#", "step", "component", "outcome"),
        )
    )


def _print_cost(outcome: WorkflowOutcome, *, rate_card: RateCard | None) -> None:
    print(heading("12  Measure  ·  consumption beyond tokens"))
    if outcome.cost is None:
        print(bullet("no cost ledger recorded"))
        return
    summary = outcome.cost.summarise(
        rate_card=rate_card, task_completed=outcome.status == "completed"
    )
    print(
        table(
            (
                (surface, f"{units:g}", summary.category_by_surface[surface].value)
                for surface, units in sorted(summary.units_by_surface.items())
            ),
            headers=("consumption surface", "units", "cost band"),
        )
    )
    print(field("basis", summary.basis.value))
    print(field("tokens in / out", f"{summary.total_input_tokens} / {summary.total_output_tokens}"))
    print(field("frontier calls avoided", summary.frontier_calls_avoided))
    if summary.cost_per_completed_task is None:
        print(
            style(
                "  No rate card supplied, so no currency figure is claimed. "
                "Units are facts; prices are the customer's.",
                "dim",
            )
        )
    else:
        print(
            field(
                "cost per completed task",
                f"{summary.cost_per_completed_task:.4f} {summary.currency} (estimated)",
                colour="bold",
            )
        )


async def _run_demo(args: argparse.Namespace) -> int:
    settings = get_settings()
    scenario: DemoScenario = get_scenario(args.scenario)
    assembly = build_platform(settings, persist_state=args.persist)

    _print_banner(settings)
    print(heading(f"scenario · {scenario.name}"))
    print(style(f"  {scenario.narrative}", "dim"))
    is_replenishment = scenario.id.endswith("replenishment")
    location_label = "warehouse / bin" if is_replenishment else "line / station"
    context_label = "sku / supplier:quantity" if is_replenishment else "sku / batch"
    print(field(location_label, f"{scenario.line_id} / {scenario.station_id}"))
    print(field(context_label, f"{scenario.product_sku} / {scenario.batch_id}"))
    print(field("classification", scenario.classification.value))

    operator = IdentityContext.local_demo_operator()
    outcome = await assembly.workflow.run(
        scenario.to_request(),
        identity=operator,
        batch_defect_count=scenario.batch_defect_count,
    )
    if isinstance(assembly.retriever, AzureSearchRetriever):
        await assembly.retriever.close()

    _print_detection(outcome)
    _print_route(outcome)
    _print_evidence(outcome)
    _print_recommendation(outcome)
    _print_policy(outcome)
    _print_approval(outcome)

    if outcome.awaiting_approval and not args.leave_pending:
        assert outcome.approval is not None
        role = outcome.approval.request.required_role
        decisions = 2 if outcome.approval.request.dual_control_required else 1
        target_state = ApprovalState.REJECTED if args.reject else ApprovalState.APPROVED

        print(heading("8b  Decision  ·  a named human, not the model"))
        for index in range(decisions):
            approver = IdentityContext.local_demo_approver(role)
            principal = f"{approver.principal_id}-{index + 1}"
            record = await assembly.approvals.decide(
                outcome.approval.approval_id,
                ApprovalDecision(
                    approver_principal_id=principal,
                    approver_role=role,
                    state=target_state,
                    rationale=(
                        "Rejected in demonstration to show the write path stays closed."
                        if args.reject
                        else "Evidence and policy result reviewed; proceed."
                    ),
                ),
            )
            print(
                field(
                    f"decision {index + 1}",
                    f"{principal} → {record.state.value}",
                    colour="red" if args.reject else "green",
                )
            )
            outcome.approval = record

        outcome = await assembly.workflow.complete(outcome, dry_run=settings.connector.dry_run)
        _print_action(outcome)
    elif outcome.awaiting_approval:
        print(
            style(
                "\n  Left pending. The write path stays closed until a human decides.",
                "yellow",
            )
        )

    _print_audit(outcome)
    _print_cost(outcome, rate_card=_load_rate_card(args.rate_card))

    print(heading("outcome"))
    print(field("status", outcome.status, colour="bold"))
    closing = (
        "\n  The signal proposed; policy decided; a separate human authorized; "
        "the scoped writer remained in dry-run.\n"
        if is_replenishment
        else (
            "\n  The specialized model found the defect.\n"
            "  The Enterprise AI platform proved what happened and governed what happened next.\n"
        )
    )
    print(style(closing, "cyan"))

    if args.json_out:
        payload = json.dumps(_outcome_as_dict(outcome), indent=2, default=str)
        await asyncio.to_thread(Path(args.json_out).write_text, payload, encoding="utf-8")
        print(field("written", args.json_out))
    return EXIT_OK


def _outcome_as_dict(outcome: WorkflowOutcome) -> dict[str, Any]:
    return {
        "correlation_id": outcome.correlation_id,
        "status": outcome.status,
        "halted_reason": outcome.halted_reason,
        "detection": outcome.detection.model_dump() if outcome.detection else None,
        "route": outcome.route.model_dump() if outcome.route else None,
        "policy": outcome.policy.model_dump() if outcome.policy else None,
        "approval": outcome.approval.model_dump() if outcome.approval else None,
        "action_receipt": outcome.action_receipt.model_dump() if outcome.action_receipt else None,
        "audit": outcome.audit.model_dump() if outcome.audit else None,
        "step_latencies_ms": outcome.step_latencies_ms,
    }


def _load_rate_card(path: str | None) -> RateCard | None:
    """Load a customer-supplied rate card. Without one, no currency is claimed."""
    if not path:
        return None
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    return RateCard(
        currency=document.get("currency", "UNSPECIFIED"),
        per_unit=dict(document.get("per_unit", {})),
        per_1k_input_tokens=document.get("per_1k_input_tokens"),
        per_1k_output_tokens=document.get("per_1k_output_tokens"),
    )


def _list_scenarios(_: argparse.Namespace) -> int:
    scenarios = load_scenarios()
    print(heading("demo scenarios"))
    print(
        table(
            (
                (
                    scenario.id,
                    scenario.pinned_label,
                    f"{scenario.pinned_confidence:.3f}",
                    str(scenario.expects.get("disposition", "—")),
                    "yes" if scenario.expects.get("approval_required") else "no",
                )
                for scenario in scenarios.values()
            ),
            headers=("id", "pinned label", "conf", "expected disposition", "approval"),
        )
    )
    print(style("\n  Pinned values are fixtures, not model performance.", "dim"))
    return EXIT_OK


async def _run_replenishment_demo(args: argparse.Namespace) -> int:
    print(heading("governed warehouse replenishment · synthetic fixture"))
    print(
        style(
            "  One story: reject an unsafe SKU, then approve and dry-run the exact safe order.",
            "dim",
        )
    )
    for scenario_id in ("unsafe-replenishment", "governed-replenishment"):
        scenario_args = argparse.Namespace(**vars(args), scenario=scenario_id)
        result = await _run_demo(scenario_args)
        if result != EXIT_OK:
            return result
    return EXIT_OK


# ---------------------------------------------------------------------------
# eval / ready / audit / doctor
# ---------------------------------------------------------------------------


async def _run_eval(args: argparse.Namespace) -> int:
    from evaluation import run_release_gate  # noqa: PLC0415

    report = await run_release_gate(
        dataset_path=Path(args.dataset) if args.dataset else None,
        report_path=Path(args.report) if args.report else None,
    )
    print(report.render_text())
    return EXIT_OK if report.release_gate_passed else EXIT_GATE_FAILED


def _run_ready(args: argparse.Namespace) -> int:
    from readyai import evaluate_gate, load_assessment  # noqa: PLC0415
    from readyai.scorecard import render_scorecard  # noqa: PLC0415

    assessment = load_assessment(Path(args.assessment))
    print(render_scorecard(assessment))
    return EXIT_OK if evaluate_gate(assessment).passed else EXIT_GATE_FAILED


def _verify_audit(args: argparse.Namespace) -> int:
    receipt = AuditReceipt.model_validate_json(Path(args.file).read_text(encoding="utf-8"))
    ok = receipt.verify_chain()
    print(heading("audit verification"))
    print(field("audit id", receipt.audit_id))
    print(field("correlation id", receipt.correlation_id))
    print(field("steps", len(receipt.steps)))
    print(verdict("hash chain intact", ok=ok))
    return EXIT_OK if ok else EXIT_GATE_FAILED


async def _doctor(_: argparse.Namespace) -> int:
    settings = get_settings()
    assembly = build_platform(settings)
    _print_banner(settings)

    print(heading("plane health"))
    health = await assembly.health()
    for plane, ok in health.items():
        print(verdict(plane, ok=ok))

    print(heading("governance artifacts"))
    print(field("policy", f"v{assembly.policy.version} · {assembly.policy.sha[:18]}…"))
    print(field("routing policy", f"v{assembly.router.version} · {assembly.router.sha[:18]}…"))
    print(field("writer", assembly.writer.system_name))
    print(field("dry run", settings.connector.dry_run))
    print(field("kill switch", settings.governance.kill_switch_engaged))
    return EXIT_OK if all(health.values()) else EXIT_GATE_FAILED


async def _azure_preflight(_: argparse.Namespace) -> int:
    checks = await run_preflight(get_settings())
    print(heading("live Azure demo preflight"))
    for check in checks:
        print(verdict(check.name, ok=check.ok), style(f"  {check.evidence}", "dim"))
    return EXIT_OK if all(check.ok for check in checks) else EXIT_GATE_FAILED


def _azure_index(args: argparse.Namespace) -> int:
    count, index_name = index_demo_corpus(
        get_settings(), include_adversarial=args.include_adversarial
    )
    print(heading("Azure AI Search demo corpus"))
    print(field("index", index_name))
    print(field("uploaded", f"{count} synthetic fixture passages"))
    print(field("adversarial corpus", "included" if args.include_adversarial else "excluded"))
    return EXIT_OK


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reap",
        description=(
            "ready-enterprise-ai-platform. Runs the governed workflow, the evaluation "
            "release gate and the READY AI scorecard against the real platform."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo = subparsers.add_parser("demo", help="run or list the demonstration scenarios")
    demo_sub = demo.add_subparsers(dest="demo_command", required=True)

    run = demo_sub.add_parser("run", help="run one scenario end to end")
    run.add_argument("--scenario", default="major-defect", help="scenario id (see `demo list`)")
    run.add_argument("--reject", action="store_true", help="reject at the approval gate")
    run.add_argument(
        "--leave-pending",
        action="store_true",
        help="stop at the approval gate without deciding",
    )
    run.add_argument("--persist", action="store_true", help="persist approvals and audit to disk")
    run.add_argument("--rate-card", help="path to a rate card; without one no currency is claimed")
    run.add_argument("--json-out", help="write the full outcome as JSON")
    run.set_defaults(handler=_run_demo, is_async=True)

    listing = demo_sub.add_parser("list", help="list available scenarios")
    listing.set_defaults(handler=_list_scenarios, is_async=False)

    replenish = demo_sub.add_parser(
        "replenish", help="run the governed warehouse replenishment story"
    )
    replenish.add_argument("--persist", action="store_true", help="persist audit to disk")
    replenish.add_argument("--rate-card", help="optional customer-supplied rate card")
    replenish.set_defaults(
        handler=_run_replenishment_demo,
        is_async=True,
        reject=False,
        leave_pending=False,
        json_out=None,
    )

    evaluate = subparsers.add_parser("eval", help="run the evaluation release gate")
    evaluate.add_argument("--dataset", help="path to an evaluation dataset")
    evaluate.add_argument("--report", help="write the evaluation report JSON here")
    evaluate.set_defaults(handler=_run_eval, is_async=True)

    ready = subparsers.add_parser("ready", help="score a workload with READY AI")
    ready.add_argument(
        "--assessment",
        default="data/evaluations/readyai-sample-assessment.json",
        help="path to an assessment document",
    )
    ready.set_defaults(handler=_run_ready, is_async=False)

    audit = subparsers.add_parser("audit", help="verify an audit receipt")
    audit.add_argument("--file", required=True, help="path to a sealed audit receipt JSON")
    audit.set_defaults(handler=_verify_audit, is_async=False)

    doctor = subparsers.add_parser("doctor", help="check configuration and plane health")
    doctor.set_defaults(handler=_doctor, is_async=True)

    azure = subparsers.add_parser("azure", help="prepare and verify the live Azure demo")
    azure_sub = azure.add_subparsers(dest="azure_command", required=True)
    preflight = azure_sub.add_parser("preflight", help="observe live-demo prerequisites")
    preflight.set_defaults(handler=_azure_preflight, is_async=True)
    index = azure_sub.add_parser("index", help="upload the synthetic Search demonstration corpus")
    index.add_argument(
        "--include-adversarial",
        action="store_true",
        help="also upload the labelled security-test corpus",
    )
    index.set_defaults(handler=_azure_index, is_async=False)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:  # pragma: no cover - argparse enforces this
        parser.print_help()
        return EXIT_USAGE
    try:
        return asyncio.run(handler(args)) if args.is_async else int(handler(args))
    except KeyboardInterrupt:  # pragma: no cover - interactive only
        print(style("\ninterrupted", "yellow"))
        return EXIT_USAGE
    except (KeyError, FileNotFoundError, ValueError) as exc:
        print(style(f"error: {exc}", "red"), file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
