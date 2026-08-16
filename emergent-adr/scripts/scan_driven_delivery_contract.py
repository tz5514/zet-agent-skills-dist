"""Scan-owning draft delivery orchestration used by `produce`.

Drives the shared scan-cycle mechanical layer around scan-free `revise`:
pre-acceptance evidence closure when revise hands back scan-evidence findings,
post-acceptance tail close after a quality pass, accepted rewrite→rescan
ordering, and the named tail-evidence re-review budget terminal. One delivery
run shares a single review-round budget across every revise call so the limit
cannot silently multiply. The detailed delivery report keeps the scan fields
callers already read from the pre-split revise report. Existing-draft
finalization is `finalize-draft-adrs` (separate orchestration; does not call
this module).
"""

import json
from pathlib import Path

from revise_contract import (
    FINAL_BLOCKED_AFTER_REVIEW_LIMIT,
    FINAL_FAILED,
    FINAL_NEEDS_SCAN_EVIDENCE,
    FINAL_NEEDS_USER_RULING,
    FINAL_PASSED,
    MAX_REVIEW_ROUNDS,
    run_revise,
)
from scan_cycle_contract import (
    BUDGET_EXHAUSTED,
    CLOSE_PASSED,
    CLOSE_PENDING,
    CLOSE_REREVIEW_REQUIRED,
    SCAN_ROLE_PRE_ACCEPTANCE,
    ScanCycle,
    read_atomic_decisions,
    read_draft_supersedes,
    resolve_owed_rereview,
)


# disposition results that only the scan-owning driver can complete
DISPOSITION_RESULT_BY_SCAN_SUPERSESSION = "dispositioned_by_scan_supersession"
DISPOSITION_RESULT_SCAN_AWAITING_REWRITE = "scan_returned_awaiting_rewrite"
DISPOSITION_RESULT_SCAN_AWAITING_REVIEW = "scan_returned_awaiting_review"

REPORT_FILENAME = "revise_report.json"
OPERATION = "revise"


def run_scan_driven_delivery(
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
    revise_fn=None,
):
    """Complete draft delivery including supersession scanning. `revise_fn`
    defaults to scan-free `run_revise`; inject a double in tests. Returns the
    same envelope shape the pre-split revise delivery used."""
    revise_fn = revise_fn or run_revise
    draft_adr_path = inputs["draft_adr_path"]
    supersedes_fn = supersedes_fn or read_draft_supersedes
    scan_cycle = ScanCycle(
        draft_adr_path=draft_adr_path,
        scan_fn=scan_fn,
        write_fn=write_fn,
        accept_rewrite_fn=accept_rewrite_fn,
        atomic_decisions_fn=atomic_decisions_fn or read_atomic_decisions,
        scan_rewrite_loops=scan_rewrite_loops,
    )

    rounds_already_consumed = 0
    quality_rounds = []
    child_revise_paths = []
    degradation_notes = []
    evidence_status = "clean"
    last_pass_round_supersedes = None

    while True:
        revise_inputs = {
            **inputs,
            "rounds_already_consumed": rounds_already_consumed,
            "scan_state": scan_cycle.fresh_completed_scan_state(),
        }
        # each revise call gets its own run subdir so reports do not overwrite
        revise_run = Path(run_dir) / f"revise_{rounds_already_consumed}"
        revise_result = revise_fn(
            inputs=revise_inputs,
            write_fn=write_fn,
            quality_review_fn=quality_review_fn,
            run_dir=revise_run,
        )
        report = revise_result["report"]
        rounds_already_consumed += report["rounds_consumed"]
        quality_rounds.extend(report.get("quality_review_rounds") or [])
        if report.get("structured_report_path"):
            child_revise_paths.append(report["structured_report_path"])
        degradation_notes.extend(report.get("degradation_notes") or [])
        if report.get("evidence_status") == "degraded_reviewer_evidence":
            evidence_status = "degraded_reviewer_evidence"

        status = report["final_status"]
        if status == FINAL_NEEDS_SCAN_EVIDENCE:
            scan_result, gate = scan_cycle.run(SCAN_ROLE_PRE_ACCEPTANCE)
            _annotate_last_scan_disposition(quality_rounds, scan_result, gate)
            if gate["pending_scan_result"] is not None:
                return _finalize_delivery(
                    run_dir=run_dir,
                    draft_adr_path=draft_adr_path,
                    final_status=FINAL_NEEDS_USER_RULING,
                    needs_user_ruling=True,
                    quality_rounds=quality_rounds,
                    scan_cycle=scan_cycle,
                    degradation_notes=degradation_notes,
                    evidence_status=evidence_status,
                    child_revise_paths=child_revise_paths,
                    pending_scan_result=gate["pending_scan_result"],
                    unresolved_blocking_findings=report.get("unresolved_blocking_findings"),
                )
            if gate["stop_reason"] is not None:
                return _finalize_delivery(
                    run_dir=run_dir,
                    draft_adr_path=draft_adr_path,
                    final_status=FINAL_FAILED,
                    needs_user_ruling=False,
                    quality_rounds=quality_rounds,
                    scan_cycle=scan_cycle,
                    degradation_notes=degradation_notes,
                    evidence_status=evidence_status,
                    child_revise_paths=child_revise_paths,
                    errors=[{"stage": "scan", "kind": gate["stop_reason"], "detail": scan_result}],
                    unresolved_blocking_findings=report.get("unresolved_blocking_findings"),
                )
            # revise only hands back scan-evidence before the limit round, so a
            # successful closure always leaves budget for the follow-up review
            continue

        if status == FINAL_PASSED:
            last_pass_round_supersedes = supersedes_fn(draft_adr_path)
            close = scan_cycle.close_after_acceptance_pass(last_pass_round_supersedes)
            if close["kind"] == CLOSE_REREVIEW_REQUIRED:
                decision = resolve_owed_rereview(
                    can_rereview=rounds_already_consumed < MAX_REVIEW_ROUNDS,
                )
                if decision["kind"] == BUDGET_EXHAUSTED:
                    return _finalize_delivery(
                        run_dir=run_dir,
                        draft_adr_path=draft_adr_path,
                        final_status=FINAL_BLOCKED_AFTER_REVIEW_LIMIT,
                        needs_user_ruling=False,
                        quality_rounds=quality_rounds,
                        scan_cycle=scan_cycle,
                        degradation_notes=degradation_notes,
                        evidence_status=evidence_status,
                        child_revise_paths=child_revise_paths,
                        errors=[decision["error"]],
                    )
                continue
            return _finalize_scan_close(
                run_dir=run_dir,
                draft_adr_path=draft_adr_path,
                close=close,
                quality_rounds=quality_rounds,
                scan_cycle=scan_cycle,
                degradation_notes=degradation_notes,
                evidence_status=evidence_status,
                child_revise_paths=child_revise_paths,
            )

        return _finalize_delivery(
            run_dir=run_dir,
            draft_adr_path=draft_adr_path,
            final_status=status,
            needs_user_ruling=report.get("needs_user_ruling", False),
            quality_rounds=quality_rounds,
            scan_cycle=scan_cycle,
            degradation_notes=degradation_notes,
            evidence_status=evidence_status,
            child_revise_paths=child_revise_paths,
            ruling_request=report.get("ruling_request"),
            unresolved_blocking_findings=report.get("unresolved_blocking_findings"),
            errors=report.get("errors"),
        )


def _annotate_last_scan_disposition(quality_rounds, scan_result, gate):
    """Rewrite the hand-back scan-evidence disposition into the driver's
    completed scan disposition result on the most recent round."""
    dispositions = quality_rounds[-1].get("blocking_finding_dispositions") or []
    if gate["pending_scan_result"] is not None:
        result = (
            DISPOSITION_RESULT_SCAN_AWAITING_REWRITE
            if scan_result["status"] == "awaiting_rewrite"
            else DISPOSITION_RESULT_SCAN_AWAITING_REVIEW
        )
    elif gate["stop_reason"] is not None:
        return
    else:
        result = DISPOSITION_RESULT_BY_SCAN_SUPERSESSION
    for item in dispositions:
        if item.get("disposition_class") == "scan_evidence":
            item["disposition_result"] = result


def _finalize_scan_close(
    *,
    run_dir,
    draft_adr_path,
    close,
    quality_rounds,
    scan_cycle,
    degradation_notes,
    evidence_status,
    child_revise_paths,
):
    if close["kind"] == CLOSE_PASSED:
        return _finalize_delivery(
            run_dir=run_dir,
            draft_adr_path=draft_adr_path,
            final_status=FINAL_PASSED,
            needs_user_ruling=False,
            quality_rounds=quality_rounds,
            scan_cycle=scan_cycle,
            degradation_notes=degradation_notes,
            evidence_status=evidence_status,
            child_revise_paths=child_revise_paths,
        )
    if close["kind"] == CLOSE_PENDING:
        return _finalize_delivery(
            run_dir=run_dir,
            draft_adr_path=draft_adr_path,
            final_status=FINAL_NEEDS_USER_RULING,
            needs_user_ruling=True,
            quality_rounds=quality_rounds,
            scan_cycle=scan_cycle,
            degradation_notes=degradation_notes,
            evidence_status=evidence_status,
            child_revise_paths=child_revise_paths,
            pending_scan_result=close["pending_scan_result"],
        )
    return _finalize_delivery(
        run_dir=run_dir,
        draft_adr_path=draft_adr_path,
        final_status=FINAL_FAILED,
        needs_user_ruling=False,
        quality_rounds=quality_rounds,
        scan_cycle=scan_cycle,
        degradation_notes=degradation_notes,
        evidence_status=evidence_status,
        child_revise_paths=child_revise_paths,
        errors=[{
            "stage": "scan",
            "kind": close["stop_reason"],
            "detail": close["scan_result"],
        }],
    )


def _finalize_delivery(
    *,
    run_dir,
    draft_adr_path,
    final_status,
    needs_user_ruling,
    quality_rounds,
    scan_cycle,
    degradation_notes,
    evidence_status,
    child_revise_paths,
    ruling_request=None,
    pending_scan_result=None,
    unresolved_blocking_findings=None,
    errors=None,
):
    last_scan = scan_cycle.last_scan
    last_result = last_scan["result"] if last_scan is not None else {}
    scan_status = last_result.get("status", "not_run")
    report = {
        "operation": OPERATION,
        "final_status": final_status,
        "draft_adr_path": draft_adr_path,
        "structured_report_path": None,
        "needs_user_ruling": needs_user_ruling,
        "ruling_request": ruling_request,
        "quality_review_rounds": quality_rounds,
        "final_review_state": quality_rounds[-1]["review_status"] if quality_rounds else None,
        "unresolved_blocking_findings": list(unresolved_blocking_findings or []),
        "refused_findings": [],
        "scan_status": scan_status,
        "final_scan_status": scan_status,
        "scan_rewrite_request_status": scan_status,
        "scan_rewrite_loops": list(scan_cycle.scan_rewrite_loops),
        "scan_invalidated_by_atomic_decisions_change": scan_cycle.scan_invalidated,
        "pending_scan_result": pending_scan_result,
        "scanner_output_structural_validation": last_result.get(
            "scanner_output_structural_validation", False
        ),
        "main_agent_scan_review": last_result.get("main_agent_scan_review", False),
        "scans": list(scan_cycle.scans),
        "degradation_notes": list(degradation_notes),
        "child_report_paths": list(child_revise_paths),
        "skipped_steps": [],
        "evidence_status": evidence_status,
        "errors": list(errors or []),
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
