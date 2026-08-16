"""Mechanical produce orchestration contract.

`produce` is the human-invoked end-to-end draft ADR delivery entry: it calls
`write`, then drives the shared scan-cycle through scan-driven delivery around
scan-free `revise`. It owns draft-creation supersession scanning (pre-acceptance
closure, post-acceptance tail, rewrite→rescan, and the named tail-evidence
re-review terminal) and shares one review-round budget across every revise call
in a single produce run. Sub-operations are injected as callables.
"""

import json
from pathlib import Path

from revise_contract import FULL_QUALITY_REVIEW
from scan_driven_delivery_contract import run_scan_driven_delivery


OPERATION = "produce"
REPORT_FILENAME = "produce_report.json"

HANDOFF_DELIVERED = "delivered"
HANDOFF_LEFT_IN_DRAFT = "left_in_draft"
HANDOFF_STOPPED_BEFORE_DRAFT = "stopped_before_draft"


def run_produce(
    *,
    inputs,
    write_fn,
    quality_review_fn,
    scan_fn,
    run_dir,
    scan_rewrite_loops=None,
    accept_rewrite_fn=None,
    atomic_decisions_fn=None,
    supersedes_fn=None,
):
    """Write the draft, then drive scan-owning delivery. Early write terminals
    never reach revise or scan."""
    write_result = write_fn(_write_request(inputs))
    if write_result.get("status") == "needs_context_ruling":
        return _finalize(
            run_dir,
            draft_adr_path=None,
            final_status="needs_context_ruling",
            needs_user_ruling=True,
            delivery_report_path=None,
            advanced_to_delivery=False,
            handoff_status=HANDOFF_STOPPED_BEFORE_DRAFT,
            context_ruling=write_result.get("context_ruling"),
            skipped_steps=["quality_review", "scan_supersession"],
        )

    draft_adr_path = write_result.get("target_adr_path") or inputs.get("target_adr_path")
    delivery = run_scan_driven_delivery(
        inputs={
            "draft_adr_path": draft_adr_path,
            "quality_review_mode": FULL_QUALITY_REVIEW,
            "source_decision_extract_path": write_result.get("source_decision_extract_path")
            or inputs.get("source_decision_extract_path"),
            "source_material": inputs.get("source_material"),
        },
        write_fn=write_fn,
        quality_review_fn=quality_review_fn,
        scan_fn=scan_fn,
        run_dir=Path(run_dir) / "delivery",
        scan_rewrite_loops=scan_rewrite_loops,
        accept_rewrite_fn=accept_rewrite_fn,
        atomic_decisions_fn=atomic_decisions_fn,
        supersedes_fn=supersedes_fn,
    )
    delivery_report = delivery["report"]
    final_status = delivery_report["final_status"]
    return _finalize(
        run_dir,
        draft_adr_path=draft_adr_path,
        final_status=final_status,
        needs_user_ruling=delivery_report["needs_user_ruling"],
        delivery_report_path=delivery_report["structured_report_path"],
        advanced_to_delivery=True,
        handoff_status=(
            HANDOFF_DELIVERED if final_status == "passed" else HANDOFF_LEFT_IN_DRAFT
        ),
    )


def _write_request(inputs):
    request = {
        "mode": inputs.get("mode", "create"),
        "source_material": inputs.get("source_material"),
    }
    if "bounded_context_path" in inputs:
        request["bounded_context_path"] = inputs["bounded_context_path"]
    if "target_adr_path" in inputs:
        request["target_adr_path"] = inputs["target_adr_path"]
    return request


def _finalize(
    run_dir,
    *,
    draft_adr_path,
    final_status,
    needs_user_ruling,
    delivery_report_path,
    advanced_to_delivery,
    handoff_status,
    context_ruling=None,
    skipped_steps=None,
):
    report = {
        "operation": OPERATION,
        "final_status": final_status,
        "draft_adr_path": draft_adr_path,
        "structured_report_path": None,
        "needs_user_ruling": needs_user_ruling,
        "revise_report_path": delivery_report_path,
        "advanced_to_delivery": advanced_to_delivery,
        "handoff_status": handoff_status,
        "context_ruling": context_ruling,
        "skipped_steps": list(skipped_steps or []),
    }
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    report_path = run_dir / REPORT_FILENAME
    report["structured_report_path"] = str(report_path)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"direct_output": _direct_output(report), "report": report}


def _direct_output(report):
    return {
        "draft_adr_path": report["draft_adr_path"],
        "structured_report_path": report["structured_report_path"],
        "final_status": report["final_status"],
        "needs_user_ruling": report["needs_user_ruling"],
    }
