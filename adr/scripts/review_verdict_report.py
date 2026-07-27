"""Mechanical reviewer verdict payload validation and report generation.

The reviewer hand-writes only a minimal verdict payload — its mode's gate
evaluations, findings, and the integrity marker it read from the prompt file.
This module validates that payload (including the marker) and mechanically fills
in the full report schema: the skipped-gate bookkeeping, notices, and
mode-specific fields the reviewer never writes. Report shape matches the ADR
quality-review report schema; only its producer (this script) and delivery (a
persisted file, surfaced by a fixed-format path line) changed.

The HITL preflight has a smaller semantic input boundary: the reviewer supplies
only explicit gate results, findings, scope limitations, and the integrity
marker. This module normalizes representational details and supplies every field
that the preflight mode or dispatch already determines.
"""

import json
import re
from pathlib import Path

import review_prompt_assembly


REPORT_FILENAME = "reviewer_report.json"
# The fixed payload filename the assembled prompt instructs the reviewer to
# write, so the main agent can locate the payload next to the report.
VERDICT_PAYLOAD_FILENAME = "verdict_payload.json"
REPORT_PATH_LINE_PREFIX = "REVIEW_REPORT_PATH:"
_PATH_LINE_RE = re.compile(rf"(?m)^{re.escape(REPORT_PATH_LINE_PREFIX)}\s*(?P<path>\S.*)$")

_REPORT_SCHEMA_KEYS = {
    "target_adr_path",
    "review_mode",
    "review_status",
    "terminal_result",
    "preflight_status",
    "full_quality_review_completed",
    "full_quality_review_notice",
    "support_data_status",
    "source_decision_extract_status",
    "live_atomic_decision_corpus_status",
    "blocking",
    "non_blocking",
    "gate_coverage",
    "reference_closure",
    "scope_limitations",
    "skipped_gate_reasons",
    "reviewer_close_status",
}

QUALITY_REVIEW_MODE = "quality_review"
PREFLIGHT_MODE = "context_glossary_approval_preflight"
FROZEN_MODE = "frozen_glossary_review"

NECESSITY_GATE = "adr_necessity_of_existence_check"
NECESSITY_TERMINAL = "not_an_adr_candidate"

GLOSSARY_APPROVAL_GATE = "context_glossary_approval_need_check"
_FINDING_KEYS = {
    "issue",
    "evidence_location",
    "why_it_matters",
    "suggested_fix",
    "gate_id",
    "action_data",
}
_GLOSSARY_ACTION_DATA_KEYS = {
    "target_wording",
    "why_ordinary_prose_cannot_preserve_decision_meaning",
    "context_change_kind",
    "proposed_wording",
    "required_user_action",
    "full_quality_review_notice",
}
_SEMANTIC_FINDING_BASE_KEYS = _FINDING_KEYS - {"action_data"}
_SEMANTIC_GLOSSARY_ACTION_DATA_KEYS = (
    _GLOSSARY_ACTION_DATA_KEYS - {"full_quality_review_notice"}
)
PREFLIGHT_SEMANTIC_PAYLOAD_KEYS = {
    "integrity_marker",
    "gate_evaluations",
    "blocking",
    "non_blocking",
    "scope_limitations",
}
_PREFLIGHT_SEMANTIC_GATE_RESULTS = {
    "evaluated",
    "terminal",
}

STRUCTURAL_GATE = "adr_structural_reviewability_check"
# Preflight-only terminal: structural unreadability stops the preflight before
# the glossary approval analysis can run.
STRUCTURAL_BLOCKED_TERMINAL = "blocked_by_structural_unreadability"

# Each named terminal stops the review at one gate, and is only issued by the
# modes whose prompt carries its terminal-stop instruction.
_TERMINAL_STOP_GATE = {
    NECESSITY_TERMINAL: NECESSITY_GATE,
    STRUCTURAL_BLOCKED_TERMINAL: STRUCTURAL_GATE,
}
_TERMINAL_ALLOWED_MODES = {
    NECESSITY_TERMINAL: {QUALITY_REVIEW_MODE, PREFLIGHT_MODE, FROZEN_MODE},
    STRUCTURAL_BLOCKED_TERMINAL: {PREFLIGHT_MODE},
}

REQUIRED_PAYLOAD_KEYS = {
    "integrity_marker",
    "review_mode",
    "target_adr_path",
    "gate_evaluations",
    "blocking",
    "non_blocking",
    "reference_closure",
    "support_data_status",
    "source_decision_extract_status",
    "live_atomic_decision_corpus_status",
    "terminal_result",
    "scope_limitations",
    "reviewer_close_status",
}

# Reference closure belongs to the self-sufficiency check, which the preflight
# does not run. The field stays required (schema consumers change nothing), but
# in preflight mode it must be exactly this fixed not-evaluated value — a
# reviewer that did the out-of-mode resolution work, or merely claims a closure
# status, fails the round instead of being rewarded for wasted work.
PREFLIGHT_FIXED_REFERENCE_CLOSURE = {
    "status": "not_evaluated",
    "checked_references": [],
    "unresolved_references": [],
}

# Reason a mode-out gate is recorded skipped, per mode. quality_review runs every
# gate so it has no mode-out gates and no entry here.
_MODE_OUT_SKIP_REASON = {
    PREFLIGHT_MODE: "context_glossary_approval_preflight_complete",
    FROZEN_MODE: "frozen_out_of_scope",
}

_NOTICE = {
    FROZEN_MODE: (
        "The frozen glossary review ran the complete gate set except the CONTEXT.md "
        "glossary approval need check; full ADR quality review has not run."
    ),
    PREFLIGHT_MODE: "Full ADR quality review has not run.",
    NECESSITY_TERMINAL: "Full ADR quality review stopped at ADR necessity.",
}


def expand_preflight_semantic_payload(payload, *, target_adr_path):
    """Expand the preflight reviewer's semantic-only payload into the shared
    verdict payload. Missing semantic judgements remain invalid; this function
    derives representation and mode facts only."""
    if not isinstance(payload, dict) or set(payload) != PREFLIGHT_SEMANTIC_PAYLOAD_KEYS:
        return {"status": "invalid", "reason": "semantic_payload_schema_invalid"}
    if not (
        isinstance(payload["gate_evaluations"], dict)
        and isinstance(payload["blocking"], list)
        and isinstance(payload["non_blocking"], list)
        and isinstance(payload["scope_limitations"], list)
    ):
        return {"status": "invalid", "reason": "payload_field_type_invalid"}

    gate_evaluations = dict(payload["gate_evaluations"])
    if any(
        result in {"degraded", "not_evaluated"}
        for result in gate_evaluations.values()
    ):
        return {
            "status": "invalid",
            "reason": "preflight_gate_evaluation_incomplete",
        }
    if any(
        result not in _PREFLIGHT_SEMANTIC_GATE_RESULTS
        for result in gate_evaluations.values()
    ):
        return {"status": "invalid", "reason": "semantic_gate_evaluation_invalid"}
    terminal_gates = {
        gate for gate, result in gate_evaluations.items() if result == "terminal"
    }
    if terminal_gates - {STRUCTURAL_GATE}:
        return {"status": "invalid", "reason": "semantic_terminal_gate_invalid"}
    structural_terminal = STRUCTURAL_GATE in terminal_gates
    if structural_terminal:
        gate_evaluations[STRUCTURAL_GATE] = "evaluated"

    normalized_findings = {"blocking": [], "non_blocking": []}
    for severity in normalized_findings:
        for finding in payload[severity]:
            normalized = _expand_preflight_semantic_finding(finding)
            if normalized is None:
                return {"status": "invalid", "reason": "finding_schema_invalid"}
            normalized_findings[severity].append(normalized)

    has_blocking_structural = any(
        finding["gate_id"] == STRUCTURAL_GATE
        for finding in normalized_findings["blocking"]
    )
    has_blocking_necessity = any(
        finding["gate_id"] == NECESSITY_GATE
        for finding in normalized_findings["blocking"]
    )
    if structural_terminal and not has_blocking_structural:
        return {
            "status": "invalid",
            "reason": "structural_terminal_finding_mismatch",
        }
    if structural_terminal and any(
        finding["gate_id"] != STRUCTURAL_GATE
        for findings in normalized_findings.values()
        for finding in findings
    ):
        return {"status": "invalid", "reason": "conflicting_terminal_signals"}

    terminal_result = (
        STRUCTURAL_BLOCKED_TERMINAL
        if structural_terminal
        else NECESSITY_TERMINAL if has_blocking_necessity else None
    )
    expanded = {
        "integrity_marker": payload["integrity_marker"],
        "review_mode": PREFLIGHT_MODE,
        "target_adr_path": target_adr_path,
        "gate_evaluations": gate_evaluations,
        "blocking": normalized_findings["blocking"],
        "non_blocking": normalized_findings["non_blocking"],
        "reference_closure": dict(PREFLIGHT_FIXED_REFERENCE_CLOSURE),
        "support_data_status": "not_applicable",
        "source_decision_extract_status": "not_applicable",
        "live_atomic_decision_corpus_status": "not_applicable",
        "terminal_result": terminal_result,
        "scope_limitations": payload["scope_limitations"],
        "reviewer_close_status": "completed",
    }
    ok, reason = validate_verdict_payload(
        expanded,
        expanded["integrity_marker"],
    )
    if not ok:
        return {"status": "invalid", "reason": reason}
    return {"status": "valid", "payload": expanded}


def _expand_preflight_semantic_finding(finding):
    if not isinstance(finding, dict):
        return None
    gate_id = finding.get("gate_id")
    expected_keys = set(_SEMANTIC_FINDING_BASE_KEYS)
    if gate_id == GLOSSARY_APPROVAL_GATE:
        expected_keys.add("action_data")
    if gate_id == NECESSITY_GATE and "reason" in finding:
        expected_keys.add("reason")
    if set(finding) != expected_keys:
        return None

    evidence_location = finding.get("evidence_location")
    if isinstance(evidence_location, list):
        if not evidence_location or any(
            not isinstance(item, str) or not item for item in evidence_location
        ):
            return None
        evidence_location = "; ".join(evidence_location)

    normalized = {
        **finding,
        "evidence_location": evidence_location,
    }
    if gate_id != GLOSSARY_APPROVAL_GATE:
        normalized["action_data"] = None
        return normalized

    action_data = finding["action_data"]
    if not (
        isinstance(action_data, dict)
        and set(action_data) == _SEMANTIC_GLOSSARY_ACTION_DATA_KEYS
    ):
        return None
    normalized["action_data"] = {
        **action_data,
        "full_quality_review_notice": _NOTICE[PREFLIGHT_MODE],
    }
    return normalized


def validate_verdict_payload(payload, expected_integrity_marker):
    """Validate a reviewer verdict payload. Returns ``(ok, reason)`` — a
    structured signal, never a crash. A marker mismatch or absence, a malformed
    payload, an out-of-mode gate, or incomplete in-scope coverage all invalidate
    the round."""
    if not isinstance(payload, dict):
        return False, "payload_not_a_mapping"
    if payload.get("integrity_marker") != expected_integrity_marker:
        return False, "integrity_marker_mismatch"
    if REQUIRED_PAYLOAD_KEYS - set(payload):
        return False, "missing_payload_keys"
    reference_closure = payload["reference_closure"]
    if not (
        isinstance(payload["blocking"], list)
        and isinstance(payload["non_blocking"], list)
        and isinstance(payload["scope_limitations"], list)
        and isinstance(reference_closure, dict)
        and "status" in reference_closure
        and isinstance(reference_closure.get("checked_references"), list)
        and isinstance(reference_closure.get("unresolved_references"), list)
    ):
        return False, "payload_field_type_invalid"
    review_mode = payload["review_mode"]
    try:
        mode_gates = review_prompt_assembly.mode_gate_ids(review_mode)
    except ValueError:
        return False, "unknown_review_mode"
    canonical_gates = set(review_prompt_assembly.gate_ids())
    for finding in payload["blocking"] + payload["non_blocking"]:
        if not isinstance(finding, dict) or finding.get("gate_id") not in canonical_gates:
            return False, "finding_gate_unknown"
        if not _finding_schema_is_valid(finding):
            return False, "finding_schema_invalid"
    if review_mode == PREFLIGHT_MODE and reference_closure != PREFLIGHT_FIXED_REFERENCE_CLOSURE:
        return False, "preflight_reference_closure_not_fixed"
    gate_evaluations = payload["gate_evaluations"]
    if not isinstance(gate_evaluations, dict):
        return False, "gate_evaluations_not_a_mapping"
    if review_mode == PREFLIGHT_MODE and any(
        result != "evaluated" for result in gate_evaluations.values()
    ):
        return False, "preflight_gate_evaluation_incomplete"
    if any(gate not in mode_gates for gate in gate_evaluations):
        return False, "gate_outside_mode"
    allowed_modes = _TERMINAL_ALLOWED_MODES.get(payload["terminal_result"])
    if allowed_modes is not None and review_mode not in allowed_modes:
        return False, "terminal_outside_mode"
    has_blocking_necessity_finding = any(
        finding["gate_id"] == NECESSITY_GATE for finding in payload["blocking"]
    )
    if (payload["terminal_result"] == NECESSITY_TERMINAL) != has_blocking_necessity_finding:
        return False, "necessity_terminal_finding_mismatch"
    if any(
        finding["gate_id"] not in mode_gates
        for finding in payload["blocking"] + payload["non_blocking"]
    ):
        return False, "finding_gate_outside_mode"
    if set(gate_evaluations) != _expected_evaluated_gates(payload, mode_gates):
        return False, "gate_coverage_incomplete"
    return True, None


def _finding_schema_is_valid(finding):
    gate_id = finding["gate_id"]
    expected_keys = set(_FINDING_KEYS)
    if gate_id == NECESSITY_GATE and "reason" in finding:
        expected_keys.add("reason")
    if set(finding) != expected_keys:
        return False
    if any(
        not isinstance(finding[key], str) or not finding[key]
        for key in _FINDING_KEYS - {"action_data"}
    ):
        return False
    if gate_id == NECESSITY_GATE and "reason" in finding:
        if not isinstance(finding["reason"], str) or not finding["reason"]:
            return False
    action_data = finding["action_data"]
    if gate_id != GLOSSARY_APPROVAL_GATE:
        return action_data is None
    return (
        isinstance(action_data, dict)
        and set(action_data) == _GLOSSARY_ACTION_DATA_KEYS
        and action_data["context_change_kind"] in {"new_term", "changed_term"}
        and all(
            isinstance(value, str) and value
            for key, value in action_data.items()
            if key != "proposed_wording"
        )
        and (
            action_data["proposed_wording"] is None
            or isinstance(action_data["proposed_wording"], str)
        )
    )


def _expected_evaluated_gates(payload, mode_gates):
    # The reviewer must evaluate every gate the mode runs, unless a terminal
    # stopped the review — then only the gates up to and including the stopping
    # gate are evaluated and the later ones are mechanically skipped.
    terminal_stop_gate = _TERMINAL_STOP_GATE.get(payload["terminal_result"])
    if terminal_stop_gate is not None:
        all_gates = review_prompt_assembly.gate_ids()
        stop_index = all_gates.index(terminal_stop_gate)
        return {gate for gate in mode_gates if all_gates.index(gate) <= stop_index}
    return set(mode_gates)


def build_report(payload):
    """Build the full report schema from a validated verdict payload. The
    reviewer supplied only the gate evaluations and findings; this fills in the
    gate-coverage/skipped bookkeeping, review status, preflight status, and the
    full-review notice."""
    review_mode = payload["review_mode"]
    all_gates = review_prompt_assembly.gate_ids()
    mode_gates = review_prompt_assembly.mode_gate_ids(review_mode)
    gate_evaluations = payload["gate_evaluations"]
    terminal = payload["terminal_result"]

    # A structural-blocked preflight marks every unevaluated gate — in-mode and
    # mode-out alike — with the blocked reason, matching the existing preflight
    # helper; otherwise mode-out gates take the mode's skip reason and in-mode
    # unevaluated gates can only follow a necessity terminal stop.
    blocked = terminal == STRUCTURAL_BLOCKED_TERMINAL
    gate_coverage = {}
    skipped_gate_reasons = {}
    for gate in all_gates:
        if gate in gate_evaluations:
            gate_coverage[gate] = gate_evaluations[gate]
        elif gate not in mode_gates:
            gate_coverage[gate] = "skipped"
            skipped_gate_reasons[gate] = (
                STRUCTURAL_BLOCKED_TERMINAL if blocked else _MODE_OUT_SKIP_REASON[review_mode]
            )
        else:
            gate_coverage[gate] = "skipped"
            skipped_gate_reasons[gate] = (
                STRUCTURAL_BLOCKED_TERMINAL if blocked else "skipped_by_adr_necessity_failure"
            )

    completed = review_mode == QUALITY_REVIEW_MODE and terminal is None
    return {
        "target_adr_path": payload["target_adr_path"],
        "review_mode": review_mode,
        "review_status": _review_status(review_mode, gate_evaluations, payload),
        "terminal_result": terminal,
        "preflight_status": _preflight_status(review_mode, payload["blocking"], terminal),
        "full_quality_review_completed": completed,
        "full_quality_review_notice": None if completed else _notice(review_mode, terminal),
        "support_data_status": payload["support_data_status"],
        "source_decision_extract_status": payload["source_decision_extract_status"],
        "live_atomic_decision_corpus_status": payload["live_atomic_decision_corpus_status"],
        "blocking": payload["blocking"],
        "non_blocking": payload["non_blocking"],
        "gate_coverage": gate_coverage,
        "reference_closure": payload["reference_closure"],
        "scope_limitations": payload["scope_limitations"],
        "skipped_gate_reasons": skipped_gate_reasons,
        "reviewer_close_status": payload["reviewer_close_status"],
    }


def _review_status(review_mode, gate_evaluations, payload):
    if payload["blocking"] or payload["terminal_result"] is not None:
        # every named terminal is a stopped, non-passing review
        return "fail"
    if review_mode == PREFLIGHT_MODE:
        # A clean preflight is never a full-review pass.
        return "not_evaluated"
    values = set(gate_evaluations.values())
    # missing or degraded support data prevents a clean evaluation of the
    # support-data-dependent gates, which the report schema defines as degraded
    if "degraded" in values or payload["support_data_status"] in {"degraded", "missing"}:
        return "degraded"
    if "not_evaluated" in values:
        return "not_evaluated"
    return "pass"


def _preflight_status(review_mode, blocking, terminal):
    if review_mode != PREFLIGHT_MODE:
        return "not_applicable"
    if terminal == STRUCTURAL_BLOCKED_TERMINAL:
        return "blocked"
    return "failed" if blocking else "passed"


def _notice(review_mode, terminal):
    if terminal == NECESSITY_TERMINAL:
        return _NOTICE[NECESSITY_TERMINAL]
    return _NOTICE[review_mode]


def write_verdict_report(*, payload, expected_integrity_marker, run_dir):
    """Validate the verdict payload, build the full report, and persist it to the
    run directory. Returns a valid result with the report path and its
    fixed-format path line, or a structured invalid result — never a crash and
    no file on an invalid payload."""
    ok, reason = validate_verdict_payload(payload, expected_integrity_marker)
    if not ok:
        return {"status": "invalid", "reason": reason}
    report = build_report(payload)
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    report_path = run_dir / REPORT_FILENAME
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "status": "valid",
        "report_path": str(report_path),
        "report": report,
        "path_line": report_path_line(str(report_path)),
    }


def write_preflight_verdict_report(
    *,
    semantic_payload,
    expected_integrity_marker,
    target_adr_path,
    run_dir,
):
    """Expand, validate, and persist a HITL preflight semantic verdict."""
    expanded = expand_preflight_semantic_payload(
        semantic_payload,
        target_adr_path=target_adr_path,
    )
    if expanded["status"] != "valid":
        return expanded
    return write_verdict_report(
        payload=expanded["payload"],
        expected_integrity_marker=expected_integrity_marker,
        run_dir=run_dir,
    )


def report_path_line(report_path):
    """The single fixed-format line the reviewer emits so the main agent can
    mechanically locate the report file among any surrounding prose."""
    return f"{REPORT_PATH_LINE_PREFIX} {report_path}"


def extract_report_path(reviewer_output):
    """Mechanically extract the report file path from reviewer output that may
    carry extra prose. Returns the last path line's target, or None when no path
    line is present."""
    matches = _PATH_LINE_RE.findall(reviewer_output)
    if not matches:
        return None
    return matches[-1].strip()


def resolve_reviewer_output(reviewer_output, *, expected_integrity_marker=None, expected_review_mode=None):
    """Resolve reviewer output into a validated report. The round is invalid when
    no path line can be extracted, the file is missing or unreadable, or the file
    does not pass the report schema check.

    The two optional expectations close the dispatch loops the reviewer-side
    script run cannot (the reviewer supplies both sides there): given the
    assembler-issued marker, the persisted verdict payload next to the report
    must echo it; given the dispatched mode, the report must carry it."""
    report_path = extract_report_path(reviewer_output)
    if report_path is None:
        return {"status": "invalid", "reason": "no_report_path_line"}
    path = Path(report_path)
    if not path.exists():
        return {"status": "invalid", "reason": "report_file_not_found"}
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {"status": "invalid", "reason": "report_file_unreadable"}
    if not (isinstance(report, dict) and _REPORT_SCHEMA_KEYS <= set(report)):
        return {"status": "invalid", "reason": "invalid_report_file"}
    if expected_review_mode is not None and report["review_mode"] != expected_review_mode:
        return {"status": "invalid", "reason": "review_mode_mismatch"}
    if expected_integrity_marker is not None:
        payload_path = path.parent / VERDICT_PAYLOAD_FILENAME
        try:
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"status": "invalid", "reason": "verdict_payload_not_found"}
        except (ValueError, OSError):
            return {"status": "invalid", "reason": "verdict_payload_unreadable"}
        if not isinstance(payload, dict) or payload.get("integrity_marker") != expected_integrity_marker:
            return {"status": "invalid", "reason": "integrity_marker_mismatch"}
    return {"status": "valid", "report": report, "report_path": report_path}


def main(argv):
    """Reviewer-callable entry point: read a verdict payload file, validate and
    persist the report, and print the fixed-format path line (or an invalid-round
    marker). Preflight uses ``[preflight, semantic_payload_path,
    expected_integrity_marker, target_adr_path, run_dir]``; other modes retain
    ``[payload_path, expected_integrity_marker, run_dir]``."""
    preflight = argv[0] == "preflight"
    if preflight:
        _, payload_path, expected_integrity_marker, target_adr_path, run_dir = argv
    else:
        payload_path, expected_integrity_marker, run_dir = argv
    try:
        payload = json.loads(Path(payload_path).read_text(encoding="utf-8"))
    except (ValueError, OSError):
        print("INVALID_ROUND: payload_file_unreadable")
        return 1
    if preflight:
        result = write_preflight_verdict_report(
            semantic_payload=payload,
            expected_integrity_marker=expected_integrity_marker,
            target_adr_path=target_adr_path,
            run_dir=run_dir,
        )
    else:
        result = write_verdict_report(
            payload=payload,
            expected_integrity_marker=expected_integrity_marker,
            run_dir=run_dir,
        )
    if result["status"] == "valid":
        print(result["path_line"])
        return 0
    print(f"INVALID_ROUND: {result['reason']}")
    return 1


if __name__ == "__main__":  # pragma: no cover
    import sys

    raise SystemExit(main(sys.argv[1:]))
