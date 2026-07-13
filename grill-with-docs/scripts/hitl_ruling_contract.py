"""Pure consumer contract for interview-time ADR ruling handoffs."""

import copy
import json
from pathlib import Path


DIRECT_OUTPUT_KEYS = {
    "draft_adr_path",
    "structured_report_path",
    "final_status",
    "needs_user_ruling",
}
OUTER_REPORT_KEYS = {
    "operation",
    "final_status",
    "draft_adr_path",
    "structured_report_path",
    "needs_user_ruling",
    "ruling_request",
    "draft_operation",
    "preflight_review",
    "full_quality_review_completed",
    "full_quality_review_notice",
    "scan_status",
    "final_scan_status",
    "scan_rewrite_request_status",
    "scan_rewrite_loops",
    "skipped_steps",
    "child_report_paths",
    "evidence_status",
    "errors",
}
PREFLIGHT_REVIEW_KEYS = {
    "state",
    "review_mode",
    "preflight_status",
    "report_path",
    "blocking_count",
    "blocking",
    "glossary_approval_action_data",
}
NECESSITY_GATE = "adr_necessity_of_existence_check"
NECESSITY_TERMINAL = "not_an_adr_candidate"
NECESSITY_RULING_KEYS = {"origin", "terminal_result", "findings"}
WRITE_CONTEXT_RULING_KEYS = {"origin", "context_ruling"}
CONTEXT_RULING_KEYS = {"missing_term", "suggested_ruling_input"}
PREFLIGHT_CONTEXT_RULING_KEYS = {"origin", "glossary_approval_action_data"}
GLOSSARY_ACTION_DATA_KEYS = {
    "target_wording",
    "why_ordinary_prose_cannot_preserve_decision_meaning",
    "context_change_kind",
    "proposed_wording",
    "required_user_action",
    "full_quality_review_notice",
}
REVIEW_FINDING_KEYS = {
    "issue",
    "gate_id",
    "evidence_location",
    "why_it_matters",
    "suggested_fix",
    "action_data",
}
GLOSSARY_GATE = "context_glossary_approval_need_check"
FINAL_STATUSES = {
    "hitl_preflight_passed",
    "no_adr",
    "needs_context_ruling",
    "needs_user_ruling",
    "failed",
}
NOT_RUN_PREFLIGHT_REVIEW = {
    "state": "not_run",
    "review_mode": "context_glossary_approval_preflight",
    "preflight_status": None,
    "report_path": None,
    "blocking_count": 0,
    "blocking": [],
    "glossary_approval_action_data": [],
}
HITL_SKIPPED_STEPS = [
    "full ADR quality review",
    "draft ADR acceptance review/fix loop",
    "scan-supersession",
    "main-agent scan review and durable scan-result validation",
    "draft-side supersedes writes produced by scan",
    "scan rewrite loop",
    "post-scan quality-review rerun",
]


def _project_necessity_finding(finding):
    return {key: value for key, value in finding.items() if key != "action_data"}


def _valid_raw_necessity_finding(finding):
    if not isinstance(finding, dict):
        return False
    expected_keys = set(REVIEW_FINDING_KEYS)
    if "reason" in finding:
        expected_keys.add("reason")
    if set(finding) != expected_keys or finding.get("gate_id") != NECESSITY_GATE:
        return False
    if finding["action_data"] is not None:
        return False
    if any(
        not isinstance(finding[key], str) or not finding[key]
        for key in REVIEW_FINDING_KEYS - {"action_data"}
    ):
        return False
    return "reason" not in finding or (
        isinstance(finding["reason"], str) and bool(finding["reason"])
    )


def _necessity_findings(raw_blocking):
    return [
        finding
        for finding in raw_blocking
        if isinstance(finding, dict) and finding.get("gate_id") == NECESSITY_GATE
    ]


def _expected_necessity_ruling(raw_blocking):
    findings = _necessity_findings(raw_blocking)
    return {
        "origin": "preflight",
        "terminal_result": NECESSITY_TERMINAL,
        "findings": [_project_necessity_finding(finding) for finding in findings],
    }


def _valid_context_ruling(context_ruling):
    return (
        isinstance(context_ruling, dict)
        and set(context_ruling) == CONTEXT_RULING_KEYS
        and all(
            isinstance(context_ruling[key], str) and context_ruling[key]
            for key in CONTEXT_RULING_KEYS
        )
    )


def _valid_write_context_ruling_outer(outer_report, ruling_request):
    draft_operation = outer_report.get("draft_operation")
    return (
        outer_report.get("draft_adr_path") is None
        and outer_report.get("preflight_review") == NOT_RUN_PREFLIGHT_REVIEW
        and isinstance(draft_operation, dict)
        and draft_operation.get("status") == "needs_context_ruling"
        and draft_operation.get("context_ruling") == ruling_request.get("context_ruling")
    )


def _valid_glossary_action_data(action_data):
    if not isinstance(action_data, dict) or set(action_data) != GLOSSARY_ACTION_DATA_KEYS:
        return False
    if action_data["context_change_kind"] not in {"new_term", "changed_term"}:
        return False
    proposed_wording = action_data["proposed_wording"]
    if proposed_wording is not None and (
        not isinstance(proposed_wording, str) or not proposed_wording
    ):
        return False
    return all(
        isinstance(action_data[key], str) and action_data[key]
        for key in GLOSSARY_ACTION_DATA_KEYS
        - {"context_change_kind", "proposed_wording"}
    )


def _valid_raw_glossary_finding(finding):
    return (
        isinstance(finding, dict)
        and set(finding) == REVIEW_FINDING_KEYS
        and finding.get("gate_id") == GLOSSARY_GATE
        and _valid_glossary_action_data(finding.get("action_data"))
        and all(
            isinstance(finding[key], str) and finding[key]
            for key in REVIEW_FINDING_KEYS - {"action_data"}
        )
    )


def _valid_preflight_context_ruling_outer(outer_report, ruling_request):
    draft_path = outer_report.get("draft_adr_path")
    draft_operation = outer_report.get("draft_operation")
    preflight_review = outer_report["preflight_review"]
    blocking = preflight_review["blocking"]
    glossary_data = ruling_request["glossary_approval_action_data"]
    return (
        isinstance(draft_path, str)
        and bool(draft_path)
        and preflight_review.get("state") == "completed"
        and preflight_review.get("review_mode")
        == "context_glossary_approval_preflight"
        and preflight_review.get("preflight_status") == "failed"
        and preflight_review.get("blocking_count") == len(blocking)
        and bool(blocking)
        and all(_valid_raw_glossary_finding(finding) for finding in blocking)
        and [finding["action_data"] for finding in blocking] == glossary_data
        and isinstance(draft_operation, dict)
        and draft_operation.get("status") == "written"
        and draft_operation.get("target_adr_path") == draft_path
    )


def _valid_child_report_linkage(preflight_review, child_report_paths):
    report_path = preflight_review.get("report_path")
    if report_path is None:
        return child_report_paths == []
    return (
        isinstance(report_path, str)
        and bool(report_path)
        and child_report_paths == [report_path]
    )


def _valid_review_bookkeeping(outer_report, scan_status, skipped_steps):
    return (
        outer_report.get("full_quality_review_completed") is False
        and isinstance(outer_report.get("full_quality_review_notice"), str)
        and bool(outer_report["full_quality_review_notice"])
        and outer_report.get("scan_status") == scan_status
        and outer_report.get("final_scan_status") == scan_status
        and outer_report.get("scan_rewrite_request_status") == scan_status
        and outer_report.get("scan_rewrite_loops") == []
        and outer_report.get("skipped_steps") == skipped_steps
    )


def _valid_written_preflight_bookkeeping(outer_report):
    return (
        _valid_review_bookkeeping(
            outer_report, "skipped_for_hitl", HITL_SKIPPED_STEPS
        )
        and _valid_child_report_linkage(
            outer_report["preflight_review"], outer_report.get("child_report_paths")
        )
    )


def _valid_write_terminal_bookkeeping(outer_report):
    return (
        _valid_review_bookkeeping(outer_report, "not_run", [])
        and outer_report.get("preflight_review") == NOT_RUN_PREFLIGHT_REVIEW
        and outer_report.get("child_report_paths") == []
    )


def _valid_preflight_summary(preflight_review):
    blocking = preflight_review["blocking"]
    expected_glossary = [
        finding["action_data"]
        for finding in blocking
        if isinstance(finding, dict)
        and finding.get("gate_id") == GLOSSARY_GATE
        and isinstance(finding.get("action_data"), dict)
    ]
    return (
        preflight_review.get("review_mode")
        == "context_glossary_approval_preflight"
        and preflight_review.get("blocking_count") == len(blocking)
        and preflight_review.get("glossary_approval_action_data")
        == expected_glossary
    )


def _valid_written_preflight_outer(outer_report):
    draft_path = outer_report.get("draft_adr_path")
    draft_operation = outer_report.get("draft_operation")
    return (
        isinstance(draft_path, str)
        and bool(draft_path)
        and isinstance(draft_operation, dict)
        and draft_operation.get("status") == "written"
        and draft_operation.get("target_adr_path") == draft_path
        and _valid_written_preflight_bookkeeping(outer_report)
        and _valid_preflight_summary(outer_report["preflight_review"])
    )


def _expected_retained_evidence(outer_report):
    return (
        "clean"
        if outer_report["preflight_review"].get("report_path") is not None
        else "degraded"
    )


def _valid_failed_source(outer_report):
    errors = outer_report.get("errors")
    if not (
        outer_report.get("ruling_request") is None
        and outer_report.get("evidence_status") == "failed"
        and isinstance(errors, list)
        and len(errors) == 1
        and isinstance(errors[0], dict)
    ):
        return False
    error = errors[0]
    stage = error.get("stage")
    kind = error.get("kind")
    draft_path = outer_report.get("draft_adr_path")
    if draft_path is None:
        return (
            (stage, kind)
            in {
                ("input", "invalid_target_state"),
                ("write", "tool_failure"),
                ("write", "invalid_or_malformed_write_result"),
            }
            and _valid_write_terminal_bookkeeping(outer_report)
        )

    preflight_review = outer_report["preflight_review"]
    if not (
        _valid_written_preflight_outer(outer_report)
        and stage == "preflight"
    ):
        return False
    state = preflight_review.get("state")
    preflight_status = preflight_review.get("preflight_status")
    blocking = preflight_review["blocking"]
    if kind == "tool_failure":
        return state == "tool_failed" and preflight_status is None and blocking == []
    if kind == "invalid_preflight_report":
        return state == "invalid" and preflight_status is None and blocking == []
    if kind == "structural_unreadability":
        return (
            state == "completed"
            and preflight_status not in {"passed", "failed"}
            and error.get("findings") == blocking
        )
    if kind in {
        "necessity_terminal_finding_mismatch",
        "invalid_necessity_finding_schema",
    }:
        return state == "completed"
    return False


def _outer_coherence_error(outer_report):
    final_status = outer_report.get("final_status")
    if final_status == "failed":
        return None if _valid_failed_source(outer_report) else "invalid_outer_coherence"
    if final_status == "no_adr":
        draft_operation = outer_report.get("draft_operation")
        if not (
            outer_report.get("draft_adr_path") is None
            and isinstance(draft_operation, dict)
            and draft_operation.get("status") == "no_adr"
            and outer_report.get("ruling_request") is None
            and outer_report.get("evidence_status") == "clean"
            and outer_report.get("errors") == []
            and _valid_write_terminal_bookkeeping(outer_report)
        ):
            return "invalid_outer_coherence"
        return None
    if final_status == "needs_context_ruling":
        ruling_request = outer_report.get("ruling_request")
        origin = ruling_request.get("origin") if isinstance(ruling_request, dict) else None
        if origin == "write":
            coherent = (
                outer_report.get("draft_adr_path") is None
                and outer_report.get("evidence_status") == "clean"
                and outer_report.get("errors") == []
                and _valid_write_terminal_bookkeeping(outer_report)
                and _valid_write_context_ruling_outer(outer_report, ruling_request)
            )
        elif origin == "preflight":
            coherent = (
                outer_report.get("evidence_status")
                == _expected_retained_evidence(outer_report)
                and outer_report.get("errors") == []
                and _valid_written_preflight_outer(outer_report)
                and _valid_preflight_context_ruling_outer(outer_report, ruling_request)
            )
        else:
            coherent = False
        return None if coherent else "invalid_context_ruling_handoff"
    if final_status == "needs_user_ruling":
        preflight_review = outer_report["preflight_review"]
        if not (
            _valid_written_preflight_outer(outer_report)
            and preflight_review.get("state") == "completed"
            and preflight_review.get("preflight_status") == "failed"
            and outer_report.get("evidence_status")
            == _expected_retained_evidence(outer_report)
            and outer_report.get("errors") == []
        ):
            return "invalid_necessity_handoff"
        return None
    preflight_review = outer_report["preflight_review"]
    if not (
        _valid_written_preflight_outer(outer_report)
        and preflight_review.get("state") == "completed"
        and preflight_review.get("preflight_status") == "passed"
        and preflight_review.get("blocking") == []
        and outer_report.get("ruling_request") is None
        and outer_report.get("evidence_status")
        == _expected_retained_evidence(outer_report)
        and outer_report.get("errors") == []
    ):
        return "invalid_outer_coherence"
    return None


def validate_handoff(direct_output, outer_report):
    if not isinstance(direct_output, dict) or set(direct_output) != DIRECT_OUTPUT_KEYS:
        return False, "direct_outer_mismatch"
    if not isinstance(outer_report, dict) or set(outer_report) != OUTER_REPORT_KEYS:
        return False, "direct_outer_mismatch"
    if outer_report.get("operation") != "produce-for-HITL":
        return False, "direct_outer_mismatch"
    if any(
        direct_output[key] != outer_report.get(key) for key in DIRECT_OUTPUT_KEYS
    ):
        return False, "direct_outer_mismatch"
    final_status = outer_report.get("final_status")
    needs_user_ruling = outer_report.get("needs_user_ruling")
    draft_adr_path = outer_report.get("draft_adr_path")
    if (
        final_status not in FINAL_STATUSES
        or not isinstance(needs_user_ruling, bool)
        or not isinstance(outer_report.get("structured_report_path"), str)
        or not outer_report["structured_report_path"]
        or (draft_adr_path is not None and (not isinstance(draft_adr_path, str) or not draft_adr_path))
        or (final_status in {"needs_user_ruling", "hitl_preflight_passed"} and not draft_adr_path)
        or (final_status in {"needs_user_ruling", "needs_context_ruling"}) != needs_user_ruling
    ):
        return False, "direct_outer_mismatch"
    preflight_review = outer_report.get("preflight_review")
    if (
        not isinstance(preflight_review, dict)
        or set(preflight_review) != PREFLIGHT_REVIEW_KEYS
        or not isinstance(preflight_review.get("blocking"), list)
    ):
        return False, "direct_outer_mismatch"

    coherence_error = _outer_coherence_error(outer_report)
    if coherence_error is not None:
        return False, coherence_error

    ruling_request = outer_report.get("ruling_request")
    if final_status == "needs_user_ruling":
        draft_operation = outer_report.get("draft_operation")
        raw_blocking = preflight_review["blocking"]
        raw_findings = _necessity_findings(raw_blocking)
        raw_glossary_findings = [
            finding
            for finding in raw_blocking
            if isinstance(finding, dict) and finding.get("gate_id") == GLOSSARY_GATE
        ]
        glossary_data = preflight_review.get("glossary_approval_action_data")
        if (
            preflight_review.get("state") != "completed"
            or preflight_review.get("review_mode")
            != "context_glossary_approval_preflight"
            or preflight_review.get("preflight_status") != "failed"
            or not isinstance(draft_operation, dict)
            or draft_operation.get("status") != "written"
            or draft_operation.get("target_adr_path") != draft_adr_path
            or outer_report.get("evidence_status") == "failed"
            or outer_report.get("errors") != []
            or preflight_review.get("blocking_count")
            != len(raw_blocking)
            or len(raw_findings) + len(raw_glossary_findings) != len(raw_blocking)
            or not raw_findings
            or not all(_valid_raw_necessity_finding(finding) for finding in raw_findings)
            or not isinstance(glossary_data, list)
            or not all(
                _valid_raw_glossary_finding(finding)
                for finding in raw_glossary_findings
            )
            or glossary_data
            != [finding["action_data"] for finding in raw_glossary_findings]
            or not isinstance(ruling_request, dict)
            or set(ruling_request) != NECESSITY_RULING_KEYS
            or ruling_request.get("origin") != "preflight"
            or ruling_request.get("terminal_result") != NECESSITY_TERMINAL
            or not isinstance(ruling_request.get("findings"), list)
        ):
            return False, "invalid_necessity_handoff"
        if ruling_request != _expected_necessity_ruling(preflight_review["blocking"]):
            return False, "necessity_ruling_projection_mismatch"
    if final_status == "needs_context_ruling":
        origin = ruling_request.get("origin")
        if origin == "write":
            if (
                set(ruling_request) != WRITE_CONTEXT_RULING_KEYS
                or not _valid_context_ruling(ruling_request.get("context_ruling"))
                or not _valid_write_context_ruling_outer(
                    outer_report, ruling_request
                )
            ):
                return False, "invalid_context_ruling_handoff"
        else:
            glossary_data = ruling_request.get("glossary_approval_action_data")
            if (
                set(ruling_request) != PREFLIGHT_CONTEXT_RULING_KEYS
                or not isinstance(glossary_data, list)
                or not glossary_data
                or not all(_valid_glossary_action_data(item) for item in glossary_data)
                or glossary_data
                != preflight_review.get("glossary_approval_action_data")
                or not _valid_preflight_context_ruling_outer(
                    outer_report, ruling_request
                )
            ):
                return False, "invalid_context_ruling_handoff"
    return True, None


def necessity_ruling_identity(resolved_draft_path, raw_validated_necessity_findings):
    if not raw_validated_necessity_findings or any(
        not _valid_raw_necessity_finding(finding)
        for finding in raw_validated_necessity_findings
    ):
        raise ValueError("necessity identity requires raw validated necessity findings")
    sorted_findings = sorted(
        raw_validated_necessity_findings,
        key=lambda finding: json.dumps(
            finding,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8"),
    )
    return (
        str(Path(resolved_draft_path).resolve()),
        NECESSITY_TERMINAL,
        NECESSITY_GATE,
        tuple(copy.deepcopy(finding) for finding in sorted_findings),
    )


def route_handoff(
    direct_output,
    outer_report,
    *,
    seen_necessity_identities,
    glossary_ruling_completed=False,
):
    ok, reason = validate_handoff(direct_output, outer_report)
    if not ok:
        return {"action": "invalid_handoff", "reason": reason}

    final_status = outer_report["final_status"]
    if final_status == "needs_user_ruling":
        raw_blocking = outer_report["preflight_review"]["blocking"]
        necessity_findings = _necessity_findings(raw_blocking)
        identity = necessity_ruling_identity(
            outer_report["draft_adr_path"], necessity_findings
        )
        if identity not in seen_necessity_identities:
            return {
                "action": "present_necessity_and_stop",
                "necessity_identity": identity,
                "ruling_request": outer_report["ruling_request"],
            }
        glossary_data = outer_report["preflight_review"].get(
            "glossary_approval_action_data", []
        )
        if glossary_data and not glossary_ruling_completed:
            return {
                "action": "present_glossary_and_stop",
                "glossary_approval_action_data": glossary_data,
            }
        return {"action": "resume_documentation_flow"}

    if final_status == "needs_context_ruling":
        ruling_request = outer_report["ruling_request"]
        if ruling_request["origin"] == "write":
            return {
                "action": "present_glossary_and_stop",
                "context_ruling": ruling_request["context_ruling"],
            }
        return {
            "action": "present_glossary_and_stop",
            "glossary_approval_action_data": outer_report["preflight_review"].get(
                "glossary_approval_action_data", []
            ),
        }
    if final_status in {"hitl_preflight_passed", "no_adr"}:
        return {"action": "resume_documentation_flow"}
    return {"action": "stop_failed_delivery"}
