"""Mechanical layer for the `check-adr-redundancy` operation.

Validates a single draft/active `adr_path`, rejects archived and batch input,
and derives the still-live atomic decision set from supersession metadata.
Validates the reviewer's closed per-decision payload and mechanically derives
ADR-level summary fields. Owns OS-temp run/attempt layout with preassigned
paths, reviewer-prompt instantiation, evaluation-report write, fixed-prefix
path-line delivery, redispatch stop accounting, and deterministic bulleted
Markdown presentation of a validated evaluation report. Empty live sets and
invalid reviewer output fail closed — never by forging an evaluation report or
remapping to ``indeterminate``／``unresolved``.
"""

import json
import re
import secrets
import shlex
import sys
import tempfile
from pathlib import Path

import prompt_fragments
from live_atomic_decision_corpus import (
    _atomic_decisions,
    _superseded_own_ids,
)


OPERATION_NAME = "check-adr-redundancy"

REPORT_PATH_LINE_PREFIX = "CHECK_ADR_REDUNDANCY_REPORT_PATH:"
AUTHORITY_FAILURE_LINE_PREFIX = "CHECK_ADR_REDUNDANCY_AUTHORITY_INPUT_FAILURE:"
_REPORT_PATH_LINE_RE = re.compile(
    rf"(?m)^{re.escape(REPORT_PATH_LINE_PREFIX)}\s*(?P<path>\S.*)$"
)
_AUTHORITY_FAILURE_LINE_RE = re.compile(
    rf"(?m)^{re.escape(AUTHORITY_FAILURE_LINE_PREFIX)}\s*(?P<reason>\S.*)$"
)

# A missing or unreadable authority is an input failure the reviewer cannot
# repair; it never consumes the redispatch budget below.
AUTHORITY_INPUT_FAILURE_CLASS = "authority_input_failure"
# Total dispatches across distinct incidental failures: the initial dispatch
# plus at most two redispatches.
MAX_TOTAL_ATTEMPTS = 3

MANIFEST_FILENAME = "manifest.json"
_VERDICT_FILENAME = "verdict.json"
_EVALUATION_REPORT_FILENAME = "evaluation_report.json"
_PROMPT_FILENAME = "reviewer_prompt.md"

PROMPT_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent / "CHECK-ADR-REDUNDANCY-PROMPT.md"
)

_REPORT_KEYS = {
    "operation",
    "adr_path",
    "atomic_decision_redundancy_evaluation_results",
    "adr_redundancy_evaluation_result",
    "needs_user_ruling",
    "user_ruling_requests",
}

_ADR_PATH_RE = re.compile(
    r"^(?P<context>.+)/docs/adr/(?P<lifecycle>draft|active|archived)/(?P<file>[^/]+)$"
)

# Fixed human-report section order/labels; also the single source for the
# closed evaluation_result set. Empty groups are omitted rather than rendered
# as vacant headings.
_HUMAN_DECISION_GROUPS = (
    ("atomic_decision_fully_redundant", "Fully redundant"),
    ("atomic_decision_partially_redundant", "Partially redundant"),
    ("atomic_decision_fully_retained", "Fully retained"),
    ("atomic_decision_ground_truth_mismatch", "Ground-truth mismatch"),
    ("atomic_decision_indeterminate", "Indeterminate"),
)
_EVALUATION_RESULTS = {result for result, _heading in _HUMAN_DECISION_GROUPS}
_COMMON_DECISION_KEYS = {
    "atomic_decision_id",
    "evaluation_result",
    "evaluation_reasoning",
    "evidence",
}
_PARTIAL_EXTRA_KEYS = {"redundant_portion", "retained_portion"}
_INDETERMINATE_EXTRA_KEYS = {
    "missing_decisive_fact",
    "decision_impact",
    "resolution_path",
}
_UNRESOLVED_RESULTS = {
    "atomic_decision_ground_truth_mismatch",
    "atomic_decision_indeterminate",
}
_VERDICT_KEYS = {"atomic_decision_redundancy_evaluation_results"}

# Documents the bulleted shape; the renderer builds sections in code so empty
# groups can be omitted instead of leaving vacant filled placeholders.
HUMAN_REPORT_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent
    / "CHECK-ADR-REDUNDANCY-HUMAN-REPORT.md"
)


def prepare_check_adr_redundancy_target(adr_path):
    """Accept one draft/active ADR path and return its live atomic decisions.

    Failures are operation failures with ``evaluation_report_path: None`` —
    never vacuous ADR-level redundancy verdicts and never an evaluation report.
    """
    if isinstance(adr_path, (list, tuple)):
        return _failure(
            "invalid_input",
            "check-adr-redundancy accepts exactly one adr_path; path lists and "
            "other batch inputs are rejected",
        )
    if not isinstance(adr_path, str) or not adr_path.strip():
        return _failure(
            "invalid_input",
            "check-adr-redundancy requires a single adr_path string",
        )

    path = Path(adr_path)
    match = _ADR_PATH_RE.match(str(path))
    if match is None:
        return _failure(
            "invalid_input",
            "adr_path must be an ADR file under docs/adr/{draft|active|archived}/",
            adr_path=adr_path,
        )

    lifecycle = match.group("lifecycle")
    # Folder identity decides unsupported archived targets before any read, so
    # a missing archived path is still unsupported_target rather than "not found".
    if lifecycle == "archived":
        return _failure(
            "unsupported_target",
            "archived ADR targets are unsupported for check-adr-redundancy",
            adr_path=adr_path,
        )

    if not path.is_file():
        return _failure(
            "invalid_input",
            f"adr_path does not exist: {adr_path}",
            adr_path=adr_path,
        )

    text = path.read_text(encoding="utf-8")
    live = _live_atomic_decisions(text)
    if not live:
        return _failure(
            "unsupported_target",
            "no live atomic decision is available to evaluate",
            adr_path=adr_path,
        )

    return {
        "ok": True,
        "operation": OPERATION_NAME,
        "adr_path": adr_path,
        "live_atomic_decisions": live,
        "evaluation_report_path": None,
    }


def _failure(failure_class, error, *, adr_path=None):
    payload = {
        "ok": False,
        "operation": OPERATION_NAME,
        "failure_class": failure_class,
        "error": error,
        "evaluation_report_path": None,
    }
    if adr_path is not None:
        payload["adr_path"] = adr_path
    return payload


def _live_atomic_decisions(text):
    superseded_ids = _superseded_own_ids(text)
    live = []
    for decision in _atomic_decisions(text):
        if decision["atomic_decision_id"] in superseded_ids:
            continue
        live.append(decision)
    return live


# ---------------------------------------------------------------------------
# closed verdict validation
# ---------------------------------------------------------------------------


def validate_redundancy_verdict(verdict, *, live_atomic_decision_ids):
    """Validate the reviewer's closed per-decision redundancy payload.

    Returns ``(ok, reason)``. Coverage gaps, unknown keys, and missing
    result-specific fields are invalid reviewer output — never remapped to
    ``atomic_decision_indeterminate``.
    """
    if not isinstance(verdict, dict):
        return False, "verdict_not_a_mapping"
    if set(verdict) - _VERDICT_KEYS:
        return False, "verdict_key_unknown"
    if "atomic_decision_redundancy_evaluation_results" not in verdict:
        return False, "decision_results_missing"

    results = verdict["atomic_decision_redundancy_evaluation_results"]
    if not isinstance(results, list):
        return False, "decision_results_not_a_list"
    if not live_atomic_decision_ids:
        return False, "live_atomic_decision_set_empty"

    seen_ids = []
    for item in results:
        reason = _decision_result_reason(item)
        if reason is not None:
            return False, reason
        seen_ids.append(item["atomic_decision_id"])

    # Exact-once: same membership and same cardinality (rejects duplicates).
    if set(seen_ids) != set(live_atomic_decision_ids) or len(seen_ids) != len(
        live_atomic_decision_ids
    ):
        return False, "live_decision_coverage_invalid"
    return True, None


# ---------------------------------------------------------------------------
# mechanical ADR-level aggregation
# ---------------------------------------------------------------------------


def aggregate_adr_redundancy(decision_results):
    """Derive ADR-level fields from validated per-decision results.

    Priority is ordered and closed: unresolved beats partial/mixed; partial or
    mixed retained+redundant beats uniform fully_redundant / fully_retained.
    ``needs_user_ruling`` is true only for ``adr_unresolved`` and never grants
    disposition authority.
    """
    if not decision_results:
        raise ValueError("decision_results must be non-empty")
    kinds = {item["evaluation_result"] for item in decision_results}
    if kinds & _UNRESOLVED_RESULTS:
        adr_result = "adr_unresolved"
    elif (
        "atomic_decision_partially_redundant" in kinds
        or (
            "atomic_decision_fully_redundant" in kinds
            and "atomic_decision_fully_retained" in kinds
        )
    ):
        adr_result = "adr_partially_redundant"
    elif kinds == {"atomic_decision_fully_redundant"}:
        adr_result = "adr_fully_redundant"
    elif kinds == {"atomic_decision_fully_retained"}:
        adr_result = "adr_fully_retained"
    else:
        raise ValueError("decision_results must be validated before aggregation")

    needs_ruling = adr_result == "adr_unresolved"
    return {
        "adr_redundancy_evaluation_result": adr_result,
        "needs_user_ruling": needs_ruling,
        "user_ruling_requests": _user_ruling_requests(decision_results)
        if needs_ruling
        else [],
    }


def build_redundancy_evaluation(*, adr_path, live_atomic_decision_ids, verdict):
    """Validate reviewer output and mechanically assemble the evaluation payload.

    Does not write a report file. Invalid reviewer output fails closed without
    inventing ADR-level enums or ``needs_user_ruling``.
    """
    ok, reason = validate_redundancy_verdict(
        verdict, live_atomic_decision_ids=live_atomic_decision_ids
    )
    if not ok:
        return _failure(
            "invalid_reviewer_output",
            reason,
            adr_path=adr_path,
        )

    results = verdict["atomic_decision_redundancy_evaluation_results"]
    aggregated = aggregate_adr_redundancy(results)
    # Same return shape as target preflight: report path stays None until the
    # delivery layer writes a validated evaluation report.
    return {
        "ok": True,
        "operation": OPERATION_NAME,
        "adr_path": adr_path,
        "atomic_decision_redundancy_evaluation_results": results,
        **aggregated,
        "evaluation_report_path": None,
    }


def _non_empty_string(value):
    return isinstance(value, str) and bool(value.strip())


def _evidence_reason(evidence):
    if not isinstance(evidence, list) or not evidence:
        return "evidence_invalid"
    for item in evidence:
        # At least source+finding; additional keys are ignored, not rejected.
        if not isinstance(item, dict):
            return "evidence_invalid"
        if not _non_empty_string(item.get("source")) or not _non_empty_string(
            item.get("finding")
        ):
            return "evidence_invalid"
    return None


def _decision_result_reason(item):
    if not isinstance(item, dict):
        return "decision_result_invalid"
    evaluation_result = item.get("evaluation_result")
    if evaluation_result not in _EVALUATION_RESULTS:
        return "evaluation_result_invalid"

    allowed = set(_COMMON_DECISION_KEYS)
    if evaluation_result == "atomic_decision_partially_redundant":
        allowed |= _PARTIAL_EXTRA_KEYS
    elif evaluation_result == "atomic_decision_indeterminate":
        allowed |= _INDETERMINATE_EXTRA_KEYS
    if set(item) - allowed:
        return "decision_result_key_unknown"
    if not allowed <= set(item):
        if evaluation_result == "atomic_decision_partially_redundant":
            return "partially_redundant_fields_invalid"
        if evaluation_result == "atomic_decision_indeterminate":
            return "indeterminate_fields_invalid"
        return "decision_result_invalid"

    if not _non_empty_string(item.get("atomic_decision_id")):
        return "decision_result_invalid"
    if not _non_empty_string(item.get("evaluation_reasoning")):
        return "evaluation_reasoning_invalid"
    evidence_reason = _evidence_reason(item.get("evidence"))
    if evidence_reason is not None:
        return evidence_reason

    if evaluation_result == "atomic_decision_partially_redundant":
        if not _non_empty_string(item.get("redundant_portion")) or not _non_empty_string(
            item.get("retained_portion")
        ):
            return "partially_redundant_fields_invalid"
    elif evaluation_result == "atomic_decision_indeterminate":
        impact = item.get("decision_impact")
        if not (
            _non_empty_string(item.get("missing_decisive_fact"))
            and _non_empty_string(item.get("resolution_path"))
            and isinstance(impact, dict)
            and set(impact) == {"retained_if", "redundant_if"}
            and _non_empty_string(impact.get("retained_if"))
            and _non_empty_string(impact.get("redundant_if"))
        ):
            return "indeterminate_fields_invalid"
    return None


def _user_ruling_requests(decision_results):
    requests = []
    for item in decision_results:
        if item["evaluation_result"] not in _UNRESOLVED_RESULTS:
            continue
        request = {
            "atomic_decision_id": item["atomic_decision_id"],
            "evaluation_result": item["evaluation_result"],
            "evaluation_reasoning": item["evaluation_reasoning"],
            "evidence": item["evidence"],
        }
        if item["evaluation_result"] == "atomic_decision_indeterminate":
            request["missing_decisive_fact"] = item["missing_decisive_fact"]
            request["decision_impact"] = item["decision_impact"]
            request["resolution_path"] = item["resolution_path"]
        requests.append(request)
    return requests


# ---------------------------------------------------------------------------
# run / attempt layout
# ---------------------------------------------------------------------------


def _attempt_paths(run_dir, attempt_number):
    attempt_dir = Path(run_dir) / f"attempt-{attempt_number:02d}"
    prompt_path = attempt_dir / _PROMPT_FILENAME
    return {
        "attempt_number": attempt_number,
        "attempt_dir": str(attempt_dir),
        "reviewer_prompt_path": str(prompt_path),
        "verdict_path": str(attempt_dir / _VERDICT_FILENAME),
        "evaluation_report_path": str(attempt_dir / _EVALUATION_REPORT_FILENAME),
        # generated here so the dispatching agent sends it verbatim and never
        # hand-writes the prompt path into a dispatch message
        "dispatch_bootstrap": (
            f"Read the file {prompt_path} completely and execute the "
            "instructions in it."
        ),
    }


def _write_manifest(manifest):
    manifest_path = Path(manifest["run_dir"]) / MANIFEST_FILENAME
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _load_manifest(run_dir):
    manifest_path = Path(run_dir) / MANIFEST_FILENAME
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"run manifest is unreadable: {manifest_path}") from error


def _template_fragments():
    return prompt_fragments.parse_fragment_file(PROMPT_TEMPLATE_PATH)


def _format_live_ids(live_atomic_decision_ids):
    return ", ".join(f"`{decision_id}`" for decision_id in live_atomic_decision_ids)


def _render_reviewer_prompt(*, adr_path, live_atomic_decision_ids, attempt_paths, run_dir):
    fragments = _template_fragments()
    report_command = shlex.join(
        [
            "python3",
            str(Path(__file__).resolve()),
            "report",
            str(run_dir),
            str(attempt_paths["attempt_number"]),
        ]
    )
    body = fragments["template"]
    for key, value in (
        ("adr_path", adr_path),
        ("live_atomic_decision_ids", _format_live_ids(live_atomic_decision_ids)),
        ("verdict_path", attempt_paths["verdict_path"]),
        ("report_command", report_command),
        ("report_path_line_prefix", REPORT_PATH_LINE_PREFIX),
        ("authority_failure_line_prefix", AUTHORITY_FAILURE_LINE_PREFIX),
    ):
        body = body.replace("{" + key + "}", value)
    return body


def _materialize_attempt(*, manifest, attempt_paths):
    Path(attempt_paths["attempt_dir"]).mkdir(parents=True, exist_ok=True)
    prompt = _render_reviewer_prompt(
        adr_path=manifest["adr_path"],
        live_atomic_decision_ids=manifest["live_atomic_decision_ids"],
        attempt_paths=attempt_paths,
        run_dir=manifest["run_dir"],
    )
    Path(attempt_paths["reviewer_prompt_path"]).write_text(prompt, encoding="utf-8")


def prepare_check_adr_redundancy_run(
    *, adr_path, live_atomic_decision_ids, run_root=None
):
    """Lay out one invocation: a unique OS-temp run directory holding the first
    attempt with its instantiated reviewer prompt and preassigned verdict and
    evaluation-report paths.

    Paths are chosen by this preparer, never by an LLM. The evaluation report
    file is not created yet — only a validated write may create it. An empty
    live decision set returns the same ``unsupported_target`` operation-failure
    envelope as ``prepare_check_adr_redundancy_target``, before any layout.
    """
    if not live_atomic_decision_ids:
        # Same unsupported_target envelope as prepare_check_adr_redundancy_target
        # for an empty live set — never a raw ValueError that contradicts that
        # operation-failure contract.
        return _failure(
            "unsupported_target",
            "no live atomic decision is available to evaluate",
            adr_path=adr_path if isinstance(adr_path, str) else None,
        )
    if not isinstance(adr_path, str) or not adr_path.strip():
        raise ValueError("adr_path must be a non-empty string")

    root = Path(run_root) if run_root is not None else Path(tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    run_dir = root / f"adr-{OPERATION_NAME}-{secrets.token_hex(8)}"
    run_dir.mkdir(parents=True, exist_ok=False)

    attempt = _attempt_paths(run_dir, 1)
    manifest = {
        "operation": OPERATION_NAME,
        "run_dir": str(run_dir),
        "adr_path": adr_path,
        "live_atomic_decision_ids": list(live_atomic_decision_ids),
        "attempts": [attempt],
    }
    _materialize_attempt(manifest=manifest, attempt_paths=attempt)
    _write_manifest(manifest)
    return manifest


def prepare_check_adr_redundancy_attempt(run_dir):
    """Add one fresh, fully isolated attempt for a redispatched reviewer.

    A late write from an earlier attempt can never land on the paths the
    current attempt is awaited on. Fixed inputs (adr_path, live ids) stay
    unchanged across attempts.
    """
    manifest = _load_manifest(run_dir)
    attempt = _attempt_paths(manifest["run_dir"], len(manifest["attempts"]) + 1)
    _materialize_attempt(manifest=manifest, attempt_paths=attempt)
    manifest["attempts"].append(attempt)
    _write_manifest(manifest)
    return attempt


# ---------------------------------------------------------------------------
# evaluation report write
# ---------------------------------------------------------------------------


def _evaluation_report_body(built):
    return {
        "operation": built["operation"],
        "adr_path": built["adr_path"],
        "atomic_decision_redundancy_evaluation_results": built[
            "atomic_decision_redundancy_evaluation_results"
        ],
        "adr_redundancy_evaluation_result": built["adr_redundancy_evaluation_result"],
        "needs_user_ruling": built["needs_user_ruling"],
        "user_ruling_requests": built["user_ruling_requests"],
    }


def write_redundancy_evaluation_report(
    *, adr_path, live_atomic_decision_ids, verdict, report_path
):
    """Validate the verdict, assemble the evaluation report, and persist it to
    the preassigned path. Invalid reviewer output returns an operation failure
    with ``evaluation_report_path: None`` and writes nothing — never a forged
    evaluation enum or ``needs_user_ruling``.
    """
    built = build_redundancy_evaluation(
        adr_path=adr_path,
        live_atomic_decision_ids=live_atomic_decision_ids,
        verdict=verdict,
    )
    if not built["ok"]:
        return built

    report = _evaluation_report_body(built)
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return {
        **built,
        "evaluation_report_path": str(report_path),
        "report": report,
        "path_line": report_path_line(str(report_path)),
    }


def report_path_line(report_path):
    """The single fixed-prefix line the reviewer's final reply must contain so
    the main agent can extract the report location amid any surrounding prose.
    """
    return f"{REPORT_PATH_LINE_PREFIX} {report_path}"


# ---------------------------------------------------------------------------
# reviewer reply resolution
# ---------------------------------------------------------------------------


def extract_report_path(reviewer_reply):
    """Mechanically extract the delivered report path from a reply that may
    carry extra prose. The last path line wins; returns None when absent.
    """
    matches = _REPORT_PATH_LINE_RE.findall(reviewer_reply)
    if not matches:
        return None
    return matches[-1].strip()


def resolve_reviewer_reply(
    reviewer_reply,
    *,
    expected_report_path,
    verdict_path=None,
    adr_path=None,
    live_atomic_decision_ids=None,
):
    """Resolve a reviewer's final reply into a validated report, an authority
    input failure, or a structured invalid result.

    An authority-failure line outranks everything else — authority failures
    are repaired by fixing the input, never by trusting a report delivered
    around them. A valid resolution requires the extracted path to equal the
    preassigned path. When ``verdict_path`` is supplied, the persisted report
    must equal the mechanical derivation from that verdict.
    """
    failure_matches = _AUTHORITY_FAILURE_LINE_RE.findall(reviewer_reply)
    if failure_matches:
        return {
            "status": "authority_input_failure",
            "reason": failure_matches[-1].strip(),
        }
    report_path = extract_report_path(reviewer_reply)
    if report_path is None:
        return {"status": "invalid", "reason": "no_report_path_line"}
    if Path(report_path) != Path(expected_report_path):
        return {"status": "invalid", "reason": "report_path_mismatch"}
    path = Path(report_path)
    if not path.exists():
        return {"status": "invalid", "reason": "report_file_not_found"}
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {"status": "invalid", "reason": "report_file_unreadable"}
    if not (isinstance(report, dict) and set(report) == _REPORT_KEYS):
        return {"status": "invalid", "reason": "invalid_report_file"}
    if verdict_path is not None:
        try:
            verdict = json.loads(Path(verdict_path).read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {"status": "invalid", "reason": "verdict_file_unreadable"}
        built = build_redundancy_evaluation(
            adr_path=adr_path,
            live_atomic_decision_ids=live_atomic_decision_ids,
            verdict=verdict,
        )
        if not built["ok"]:
            return {"status": "invalid", "reason": "persisted_verdict_invalid"}
        if report != _evaluation_report_body(built):
            return {"status": "invalid", "reason": "report_not_mechanically_derived"}
    return {"status": "valid", "report": report, "report_path": report_path}


# ---------------------------------------------------------------------------
# redispatch stop accounting
# ---------------------------------------------------------------------------


def redispatch_decision(failure_classes):
    """Decide the next action after attempt failures, oldest first.

    Authority input failures never consume the attempt budget — a broken
    authority is not repaired by a fresh reviewer. Reviewer-attempt failures
    stop on the earlier of: the same class twice in consecutive reviewer
    attempts, or the total attempt budget.
    """
    if not failure_classes:
        raise ValueError("no failure recorded; nothing to decide")
    if any(
        not isinstance(failure_class, str) or not failure_class.strip()
        for failure_class in failure_classes
    ):
        raise ValueError("every failure class must be a non-empty string")
    if failure_classes[-1] == AUTHORITY_INPUT_FAILURE_CLASS:
        return {
            "action": "fix_authority_input",
            "reason": "authority_input_failure_is_not_a_reviewer_error",
        }
    attempts = [
        failure_class
        for failure_class in failure_classes
        if failure_class != AUTHORITY_INPUT_FAILURE_CLASS
    ]
    if len(attempts) >= 2 and attempts[-1] == attempts[-2]:
        return {"action": "stop", "reason": "same_error_class_twice_consecutively"}
    if len(attempts) >= MAX_TOTAL_ATTEMPTS:
        return {"action": "stop", "reason": "attempt_budget_exhausted"}
    return {"action": "redispatch_fresh_reviewer", "reason": "attempt_budget_remaining"}


# ---------------------------------------------------------------------------
# deterministic human bulleted Markdown presentation
# ---------------------------------------------------------------------------


def render_redundancy_human_report(report, *, report_path):
    """Translate a validated evaluation report into fixed bulleted Markdown.

    Presentation only: field values are copied as written. This helper never
    accepts, rejects, or rewrites ``evaluation_result``,
    ``adr_redundancy_evaluation_result``, or ``needs_user_ruling``. It presents
    ruling context but never authors the user-facing ruling question.
    """
    if not isinstance(report_path, str) or not report_path.strip():
        raise ValueError("report_path must be a non-empty string")
    if not isinstance(report, dict) or set(report) != _REPORT_KEYS:
        raise ValueError("report must be a validated evaluation report mapping")

    lines = [
        "# check-adr-redundancy report",
        "",
        "## ADR conclusion",
        "",
        f"- **ADR path:** `{report['adr_path']}`",
        f"- **ADR evaluation result:** `{report['adr_redundancy_evaluation_result']}`",
        f"- **Needs user ruling:** {str(report['needs_user_ruling']).lower()}",
    ]

    results = report["atomic_decision_redundancy_evaluation_results"]
    by_result = {}
    for item in results:
        by_result.setdefault(item["evaluation_result"], []).append(item)

    for evaluation_result, heading in _HUMAN_DECISION_GROUPS:
        group = by_result.get(evaluation_result)
        if not group:
            continue
        lines.extend(["", f"## {heading}", ""])
        for item in group:
            lines.extend(_human_decision_bullets(item))

    # These bullets expose already-validated ruling context. The main agent,
    # not this renderer, turns that context into a user-facing question.
    if report["needs_user_ruling"] and report["user_ruling_requests"]:
        lines.extend(["", "## User ruling requests", ""])
        for request in report["user_ruling_requests"]:
            lines.extend(_human_ruling_bullets(request))

    lines.extend(
        [
            "",
            "## JSON report",
            "",
            f"- `{report_path}`",
            "",
        ]
    )
    return "\n".join(lines)


def _human_evidence_lines(evidence, *, indent):
    lines = [f"{indent}- **Evidence:**"]
    for item in evidence:
        lines.append(f"{indent}  - `{item['source']}`: {item['finding']}")
    return lines


def _human_decision_bullets(item):
    lines = [
        f"- **Decision `{item['atomic_decision_id']}`**",
        f"  - **Result:** `{item['evaluation_result']}`",
        f"  - **Reason:** {item['evaluation_reasoning']}",
    ]
    if item["evaluation_result"] == "atomic_decision_partially_redundant":
        lines.append(f"  - **Redundant portion:** {item['redundant_portion']}")
        lines.append(f"  - **Retained portion:** {item['retained_portion']}")
    lines.extend(_human_evidence_lines(item["evidence"], indent="  "))
    return lines


def _human_ruling_bullets(request):
    lines = [
        f"- **Decision `{request['atomic_decision_id']}`** "
        f"(`{request['evaluation_result']}`)",
        f"  - **Reason:** {request['evaluation_reasoning']}",
    ]
    if request["evaluation_result"] == "atomic_decision_indeterminate":
        impact = request["decision_impact"]
        lines.extend(
            [
                f"  - **Missing decisive fact:** {request['missing_decisive_fact']}",
                "  - **Decision impact:**",
                f"    - **Retained if:** {impact['retained_if']}",
                f"    - **Redundant if:** {impact['redundant_if']}",
                f"  - **Resolution path:** {request['resolution_path']}",
            ]
        )
    lines.extend(_human_evidence_lines(request["evidence"], indent="  "))
    return lines


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _find_attempt(manifest, attempt_number):
    for attempt in manifest["attempts"]:
        if attempt["attempt_number"] == attempt_number:
            return attempt
    raise ValueError(f"unknown attempt number: {attempt_number}")


def _cli_prepare_target(adr_path):
    result = prepare_check_adr_redundancy_target(adr_path)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


def _cli_prepare_run(input_json_path):
    payload = json.loads(Path(input_json_path).read_text(encoding="utf-8"))
    result = prepare_check_adr_redundancy_run(
        adr_path=payload["adr_path"],
        live_atomic_decision_ids=payload["live_atomic_decision_ids"],
        run_root=payload.get("run_root"),
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("ok", True) else 1


def _cli_prepare_attempt(run_dir):
    attempt = prepare_check_adr_redundancy_attempt(run_dir)
    print(json.dumps(attempt, indent=2, ensure_ascii=False))
    return 0


def _cli_report(run_dir, attempt_number):
    manifest = _load_manifest(run_dir)
    attempt = _find_attempt(manifest, int(attempt_number))
    try:
        verdict = json.loads(Path(attempt["verdict_path"]).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print("INVALID_VERDICT: verdict_file_unreadable")
        return 1
    result = write_redundancy_evaluation_report(
        adr_path=manifest["adr_path"],
        live_atomic_decision_ids=manifest["live_atomic_decision_ids"],
        verdict=verdict,
        report_path=attempt["evaluation_report_path"],
    )
    if result["ok"]:
        print(result["path_line"])
        return 0
    print(f"INVALID_VERDICT: {result['error']}")
    return 1


def _cli_resolve_reply(run_dir, attempt_number):
    manifest = _load_manifest(run_dir)
    attempt = _find_attempt(manifest, int(attempt_number))
    resolution = resolve_reviewer_reply(
        sys.stdin.read(),
        expected_report_path=attempt["evaluation_report_path"],
        verdict_path=attempt["verdict_path"],
        adr_path=manifest["adr_path"],
        live_atomic_decision_ids=manifest["live_atomic_decision_ids"],
    )
    print(json.dumps(resolution, indent=2, ensure_ascii=False))
    return 0 if resolution["status"] == "valid" else 1


def _cli_render_human(report_path):
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    print(render_redundancy_human_report(report, report_path=report_path), end="")
    return 0


def main(argv):
    """CLI dispatcher for the orchestrating agent and the reviewer.

    `prepare-target <adr_path>` validates the target and returns live ids.
    `prepare-run <input.json>` lays out a run with an instantiated prompt.
    `prepare-attempt <run_dir>` adds an isolated redispatch attempt.
    `report <run_dir> <attempt>` validates the verdict and prints the path line.
    `resolve-reply <run_dir> <attempt>` reads the reviewer reply from stdin.
    `render-human <evaluation_report.json>` prints deterministic presentation.
    """
    if not argv:
        raise ValueError("missing subcommand")
    subcommand, *arguments = argv
    handlers = {
        "prepare-target": _cli_prepare_target,
        "prepare-run": _cli_prepare_run,
        "prepare-attempt": _cli_prepare_attempt,
        "report": _cli_report,
        "resolve-reply": _cli_resolve_reply,
        "render-human": _cli_render_human,
    }
    if subcommand not in handlers:
        raise ValueError(f"unknown subcommand: {subcommand}")
    return handlers[subcommand](*arguments)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
