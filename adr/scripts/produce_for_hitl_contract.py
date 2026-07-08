"""Mechanical produce-for-HITL orchestration contract helpers.

The lightweight human-in-the-loop draft flow runs `write`, then a
CONTEXT.md glossary approval preflight quality review, and stops. It never runs
full ADR quality review, never runs supersession scanning, and never claims a
complete produce-style acceptance pass. This module keeps the final-status
semantics, the JSON report contract, and the shared machine-handoff envelope in
one place so the dispatcher section, report examples, and tests stay aligned
without duplicating the full flow rules.
"""

import json
from pathlib import Path

from context_derivation import derive_context_root


OPERATION = "produce-for-HITL"
PREFLIGHT_REVIEW_MODE = "context_glossary_approval_preflight"
REPORT_FILENAME = "produce_for_hitl_report.json"

FINAL_STATUS_HITL_PREFLIGHT_PASSED = "hitl_preflight_passed"
FINAL_STATUS_NO_ADR = "no_adr"
FINAL_STATUS_NEEDS_CONTEXT_RULING = "needs_context_ruling"
FINAL_STATUS_FAILED = "failed"

# write outcomes the orchestration recognises. Only a written draft with a
# usable path continues to the preflight path; no_adr and needs_context_ruling
# are early write terminals.
WRITE_STATUS_WRITTEN = "written"
WRITE_STATUS_NO_ADR = "no_adr"
WRITE_STATUS_NEEDS_CONTEXT_RULING = "needs_context_ruling"

FULL_QUALITY_REVIEW_NOTICE = (
    "Full ADR quality review has not run; this run only completed the lightweight "
    "human-in-the-loop write and CONTEXT.md glossary approval preflight."
)

# Scan bookkeeping. A written draft that reaches the preflight path records the
# scan as an intentional human-in-the-loop skip; an early write terminal never
# reached that path, so its scan bookkeeping stays unrun.
SCAN_SKIPPED_FOR_HITL = "skipped_for_hitl"
SCAN_NOT_RUN = "not_run"

EVIDENCE_CLEAN = "clean"
EVIDENCE_DEGRADED = "degraded"
EVIDENCE_FAILED = "failed"

# The full-flow responsibilities the lightweight flow intentionally skips once a
# written draft reaches the preflight path. Promotion is deliberately absent
# because it is not part of the end-to-end produce flow either.
SKIPPED_STEPS = [
    "full ADR quality review",
    "draft ADR acceptance review/fix loop",
    "scan-supersession",
    "main-agent scan review and durable scan-result validation",
    "draft-side supersedes writes produced by scan",
    "scan rewrite loop",
    "post-scan quality-review rerun",
]


def run_produce_for_hitl(*, inputs, write_fn, preflight_fn, run_dir):
    """Orchestrate the lightweight human-in-the-loop draft flow.

    ``write_fn`` and ``preflight_fn`` are injected so the orchestration can be
    driven with test doubles for the ``write`` and ``quality-review`` sub-
    operations. ``run_dir`` is the OS tmp structured run directory the JSON
    report is persisted into. Returns the persisted ``report`` and the direct
    output handoff envelope.
    """
    try:
        write_input = _build_write_input(inputs)
    except Exception as exc:
        # Building the write input can fail before write runs — e.g. a modify
        # target path that is structurally invalid and yields no bounded context.
        # That is an invalid target state: a non-user-ruling failure that still
        # persists a report instead of escaping as a crash.
        report = _build_write_terminal_report(
            FINAL_STATUS_FAILED,
            None,
            inputs,
            [{"stage": "input", "kind": "invalid_target_state", "detail": str(exc)}],
        )
        return _persist_and_handoff(report, run_dir)
    write_result, write_error = _invoke_write(write_fn, write_input)
    classification, errors = _classify_write(write_result, write_error)
    if classification == WRITE_STATUS_WRITTEN:
        draft_adr_path = write_result["target_adr_path"]
        preflight_outcome = preflight_fn(_build_preflight_request(draft_adr_path))
        report = _build_preflight_path_report(write_result, draft_adr_path, preflight_outcome)
    else:
        report = _build_write_terminal_report(classification, write_result, write_input, errors)
    return _persist_and_handoff(report, run_dir)


def _invoke_write(write_fn, write_input):
    try:
        return write_fn(write_input), None
    except Exception as exc:  # a write tool crash is a non-user-ruling failure
        return None, {"stage": "write", "kind": "tool_failure", "detail": str(exc)}


def _classify_write(write_result, write_error):
    # Returns the final_status the write stage resolves to (before any preflight)
    # plus the structured errors that terminal state carries. Only a written
    # draft with a usable path continues to the preflight path; everything else
    # is an early write terminal. Unknown/malformed results and invalid target
    # state collapse into a non-user-ruling failure.
    if write_error is not None:
        return FINAL_STATUS_FAILED, [write_error]
    status = write_result.get("status")
    if status == WRITE_STATUS_NO_ADR:
        return FINAL_STATUS_NO_ADR, []
    if status == WRITE_STATUS_NEEDS_CONTEXT_RULING:
        return FINAL_STATUS_NEEDS_CONTEXT_RULING, []
    if status == WRITE_STATUS_WRITTEN and write_result.get("target_adr_path"):
        return WRITE_STATUS_WRITTEN, []
    return FINAL_STATUS_FAILED, [_write_failure_error(write_result)]


def _write_failure_error(write_result):
    return {
        "stage": "write",
        "kind": "invalid_or_malformed_write_result",
        "detail": write_result,
    }


def _build_write_input(inputs):
    if inputs["mode"] == "modify":
        target_adr_path = inputs["target_adr_path"]
        return {
            "mode": "modify",
            "target_adr_path": target_adr_path,
            "bounded_context_path": _derive_bounded_context(target_adr_path),
            "source_material": inputs["source_material"],
        }
    return {
        "mode": "create",
        "bounded_context_path": inputs["bounded_context_path"],
        "source_material": inputs["source_material"],
    }


def _derive_bounded_context(target_adr_path):
    # A modify target is an existing draft ADR, so its bounded context is the
    # prefix before docs/adr/ and can be derived from the target path itself.
    return derive_context_root(target_adr_path)


def _build_preflight_request(draft_adr_path):
    # quality-review always persists its report now, so no persist flag is
    # passed — the request only names the target and the preflight mode.
    return {
        "target_adr_path": draft_adr_path,
        "review_mode": PREFLIGHT_REVIEW_MODE,
    }


def _build_preflight_path_report(write_result, draft_adr_path, preflight_outcome):
    # The written draft already reached the preflight path, so scan bookkeeping
    # is skipped-for-hitl and the full-flow skipped-step responsibilities apply
    # regardless of how preflight resolved. Only the terminal status, evidence,
    # ruling request, and errors depend on the preflight outcome.
    tool_failed = preflight_outcome.get("tool_failed", False)
    preflight_report = preflight_outcome.get("report")
    child_report_path = preflight_outcome.get("report_path")
    disposition = _preflight_disposition(tool_failed, preflight_report)
    evidence_status = disposition["evidence_status"]
    if evidence_status == EVIDENCE_CLEAN and child_report_path is None:
        # Preflight ran and resolved cleanly, but its child report could not be
        # retained or linked: the expected evidence exists yet is not fully
        # preserved, which is degraded rather than clean.
        evidence_status = EVIDENCE_DEGRADED
    return _base_report(
        final_status=disposition["final_status"],
        draft_adr_path=draft_adr_path,
        needs_user_ruling=disposition["needs_user_ruling"],
        ruling_request=disposition["ruling_request"],
        draft_operation=write_result,
        preflight_review=_preflight_review(tool_failed, preflight_report, child_report_path),
        scan_status=SCAN_SKIPPED_FOR_HITL,
        skipped_steps=list(SKIPPED_STEPS),
        child_report_paths=_child_report_paths(child_report_path),
        evidence_status=evidence_status,
        errors=disposition["errors"],
    )


def _preflight_disposition(tool_failed, preflight_report):
    if tool_failed:
        return _failed_disposition([{"stage": "preflight", "kind": "tool_failure"}])
    preflight_status = preflight_report["preflight_status"]
    if preflight_status == "passed":
        return {
            "final_status": FINAL_STATUS_HITL_PREFLIGHT_PASSED,
            "needs_user_ruling": False,
            "ruling_request": None,
            "evidence_status": EVIDENCE_CLEAN,
            "errors": [],
        }
    if preflight_status == "failed":
        # A glossary approval need is a user ruling, not a failure: write and
        # preflight evidence are both present, so evidence stays clean.
        return {
            "final_status": FINAL_STATUS_NEEDS_CONTEXT_RULING,
            "needs_user_ruling": True,
            "ruling_request": {
                "origin": "preflight",
                "glossary_approval_action_data": _glossary_action_data(preflight_report["blocking"]),
            },
            "evidence_status": EVIDENCE_CLEAN,
            "errors": [],
        }
    # preflight could not evaluate because the draft was structurally unreadable.
    return _failed_disposition(
        [{"stage": "preflight", "kind": "structural_unreadability", "findings": preflight_report["blocking"]}]
    )


def _failed_disposition(errors):
    return {
        "final_status": FINAL_STATUS_FAILED,
        "needs_user_ruling": False,
        "ruling_request": None,
        "evidence_status": EVIDENCE_FAILED,
        "errors": errors,
    }


def _child_report_paths(child_report_path):
    return [child_report_path] if child_report_path is not None else []


def _build_write_terminal_report(classification, write_result, write_input, errors):
    # Early write terminals never reached the preflight path, so scan bookkeeping
    # stays unrun and the preflight-path skipped-step responsibilities do not
    # apply. A valid write outcome with a persisted report is clean evidence; a
    # tool or structural failure is failed evidence.
    needs_user_ruling = classification == FINAL_STATUS_NEEDS_CONTEXT_RULING
    ruling_request = _write_ruling_request(write_result) if needs_user_ruling else None
    evidence_status = EVIDENCE_FAILED if classification == FINAL_STATUS_FAILED else EVIDENCE_CLEAN
    draft_operation = write_result if write_result is not None else write_input
    return _base_report(
        final_status=classification,
        draft_adr_path=None,
        needs_user_ruling=needs_user_ruling,
        ruling_request=ruling_request,
        draft_operation=draft_operation,
        preflight_review=_not_run_preflight_review(),
        scan_status=SCAN_NOT_RUN,
        skipped_steps=[],
        child_report_paths=[],
        evidence_status=evidence_status,
        errors=errors,
    )


def _write_ruling_request(write_result):
    return {"origin": "write", "context_ruling": write_result.get("context_ruling")}


def _not_run_preflight_review():
    return {
        "state": "not_run",
        "review_mode": PREFLIGHT_REVIEW_MODE,
        "preflight_status": None,
        "report_path": None,
        "blocking_count": 0,
        "glossary_approval_action_data": [],
    }


def _preflight_review(tool_failed, preflight_report, child_report_path):
    if tool_failed:
        return {
            "state": "tool_failed",
            "review_mode": PREFLIGHT_REVIEW_MODE,
            "preflight_status": None,
            "report_path": child_report_path,
            "blocking_count": 0,
            "glossary_approval_action_data": [],
        }
    blocking = preflight_report["blocking"]
    return {
        "state": "completed",
        "review_mode": PREFLIGHT_REVIEW_MODE,
        "preflight_status": preflight_report["preflight_status"],
        "report_path": child_report_path,
        "blocking_count": len(blocking),
        "glossary_approval_action_data": _glossary_action_data(blocking),
    }


def _glossary_action_data(blocking):
    return [finding["action_data"] for finding in blocking if "action_data" in finding]


def _base_report(
    *,
    final_status,
    draft_adr_path,
    needs_user_ruling,
    ruling_request,
    draft_operation,
    preflight_review,
    scan_status,
    skipped_steps,
    child_report_paths,
    evidence_status,
    errors,
):
    return {
        "operation": OPERATION,
        "final_status": final_status,
        "draft_adr_path": draft_adr_path,
        "structured_report_path": None,
        "needs_user_ruling": needs_user_ruling,
        "ruling_request": ruling_request,
        "draft_operation": draft_operation,
        "preflight_review": preflight_review,
        "full_quality_review_completed": False,
        "full_quality_review_notice": FULL_QUALITY_REVIEW_NOTICE,
        "scan_status": scan_status,
        "final_scan_status": scan_status,
        "scan_rewrite_request_status": scan_status,
        "scan_rewrite_loops": [],
        "skipped_steps": skipped_steps,
        "child_report_paths": child_report_paths,
        "evidence_status": evidence_status,
        "errors": errors,
    }


def _persist_and_handoff(report, run_dir):
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
