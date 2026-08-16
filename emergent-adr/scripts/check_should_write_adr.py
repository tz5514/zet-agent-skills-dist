"""Mechanical layer for the `check-should-write-adr` operation.

The main agent supplies only semantic inputs — each candidate's description,
its mode, and a modify target when one exists. Everything mechanical lives
here: the conversation-evidence cutoff, the per-round run directory with
per-candidate slots and per-attempt isolation, the instantiated reviewer
prompt files, the closed verdict-JSON validation with evidence line-number
checks, the assembled final report with its fixed field boundary, the
fixed-prefix path-line delivery, and the redispatch stop accounting. The
reviewer hand-writes only the minimal semantic verdict; no path, pairing
datum, or derivable field is ever produced by an LLM.
"""

import json
import re
import secrets
import shlex
import sys
import tempfile
from pathlib import Path

import necessity_conditions_authority
import prompt_fragments


OPERATION_NAME = "check-should-write-adr"

PROMPT_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent / "CHECK-SHOULD-WRITE-ADR-PROMPT.md"
)
_AUTHORITY_READER_PATH = (
    Path(__file__).resolve().parent / "necessity_conditions_authority.py"
)

# Line-number citations may only land on the two conversation-facing
# categories; the session_basic_data header identifies the source session and
# never proves qualification.
ALLOWED_EVIDENCE_CATEGORIES = ("user_prompt", "user_visible_agent_output")
_LATEST_PROMPT_CATEGORY = "user_prompt"

REPORT_PATH_LINE_PREFIX = "CHECK_SHOULD_WRITE_ADR_REPORT_PATH:"
AUTHORITY_FAILURE_LINE_PREFIX = "CHECK_SHOULD_WRITE_ADR_AUTHORITY_INPUT_FAILURE:"
_REPORT_PATH_LINE_RE = re.compile(
    rf"(?m)^{re.escape(REPORT_PATH_LINE_PREFIX)}\s*(?P<path>\S.*)$"
)
_AUTHORITY_FAILURE_LINE_RE = re.compile(
    rf"(?m)^{re.escape(AUTHORITY_FAILURE_LINE_PREFIX)}\s*(?P<reason>\S.*)$"
)

# A missing, unreadable, or invalid authority is an input failure the reviewer
# cannot repair; it never consumes the redispatch budget below.
AUTHORITY_INPUT_FAILURE_CLASS = "authority_input_failure"
# Total dispatches per candidate across distinct incidental failures: the
# initial dispatch plus at most two redispatches.
MAX_TOTAL_ATTEMPTS = 3

MANIFEST_FILENAME = "manifest.json"
_EVIDENCE_RELATIVE_PATH = Path("evidence") / "transcript.jsonl"
_DESCRIPTION_FILENAME = "candidate_description.md"
_PROMPT_FILENAME = "reviewer_prompt.md"
_VERDICT_FILENAME = "verdict.json"
_REPORT_FILENAME = "report.json"

_MODES = ("create", "modify")
_CANDIDATE_KEYS = {"mode", "candidate_description", "modify_target_path"}


# ---------------------------------------------------------------------------
# conversation-evidence cutoff
# ---------------------------------------------------------------------------


def _read_artifact_lines(artifact_path):
    path = Path(artifact_path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ValueError(f"extracted artifact is unreadable: {path}") from error
    lines = text.splitlines()
    records = []
    for number, line in enumerate(lines, start=1):
        try:
            records.append(json.loads(line))
        except ValueError as error:
            raise ValueError(
                f"extracted artifact is not valid JSONL at line {number}: {path}"
            ) from error
    return lines, records


def _cut_lines_at_latest_user_prompt(lines, records, artifact_path):
    latest_prompt_line = None
    for number, record in enumerate(records, start=1):
        if isinstance(record, dict) and record.get("type") == _LATEST_PROMPT_CATEGORY:
            latest_prompt_line = number
    if latest_prompt_line is None:
        raise ValueError(
            "cutoff boundary unachievable: no user_prompt record exists in "
            f"{artifact_path}, so no snapshot can include the latest ratified "
            "answer while excluding the current agent turn"
        )
    return lines[:latest_prompt_line], latest_prompt_line


def write_evidence_artifact(extracted_artifact_path, evidence_path):
    """Deliver the pre-write conversation evidence artifact: the extracted
    JSONL truncated right after its latest ``user_prompt`` record.

    Everything after the latest user prompt is the current agent turn, so the
    truncation both keeps the latest ratified answer and excludes the turn
    that is asking for this review. Raises when the boundary cannot be
    achieved; no artifact is delivered then. Kept lines are byte-identical to
    the source, so line numbers cited against the delivered file stay honest.
    """
    lines, records = _read_artifact_lines(extracted_artifact_path)
    kept, latest_prompt_line = _cut_lines_at_latest_user_prompt(
        lines, records, extracted_artifact_path
    )
    evidence_path = Path(evidence_path)
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text("".join(line + "\n" for line in kept), encoding="utf-8")
    return {
        "evidence_artifact_path": str(evidence_path),
        "line_count": len(kept),
        "latest_user_prompt_line": latest_prompt_line,
    }


# ---------------------------------------------------------------------------
# preparer: run directory, slots, attempts, reviewer prompts, manifest
# ---------------------------------------------------------------------------


def _validate_candidate(candidate):
    if not isinstance(candidate, dict):
        raise ValueError("candidate must be a mapping")
    unknown = set(candidate) - _CANDIDATE_KEYS
    if unknown:
        raise ValueError(f"unknown candidate keys: {sorted(unknown)}")
    mode = candidate.get("mode")
    if mode not in _MODES:
        raise ValueError(f"candidate mode must be one of {_MODES}; got {mode!r}")
    description = candidate.get("candidate_description")
    if not isinstance(description, str) or not description.strip():
        raise ValueError("candidate_description must be a non-empty string")
    target = candidate.get("modify_target_path")
    if mode == "create":
        if target is not None:
            raise ValueError("a create candidate takes no modify_target_path")
        return {"mode": mode, "candidate_description": description, "modify_target_path": None}
    if not isinstance(target, str) or not Path(target).is_file():
        raise ValueError(f"modify_target_path must name an existing file; got {target!r}")
    return {"mode": mode, "candidate_description": description, "modify_target_path": target}


def _template_fragments():
    return prompt_fragments.parse_fragment_file(PROMPT_TEMPLATE_PATH)


def _render_reviewer_prompt(*, slot, attempt_paths, evidence_artifact_path, run_dir):
    fragments = _template_fragments()
    mode_directive = fragments[f"mode:{slot['mode']}"]
    if slot["mode"] == "modify":
        mode_directive = mode_directive.replace(
            "{modify_target_path}", slot["modify_target_path"]
        )
    report_command = shlex.join(
        [
            "python3",
            str(Path(__file__).resolve()),
            "report",
            str(run_dir),
            str(slot["slot_number"]),
            str(attempt_paths["attempt_number"]),
        ]
    )
    authority_command = shlex.join(["python3", str(_AUTHORITY_READER_PATH)])
    allowed_categories = " or ".join(f"`{name}`" for name in ALLOWED_EVIDENCE_CATEGORIES)
    body = fragments["template"]
    for key, value in (
        ("mode_directive", mode_directive),
        ("evidence_artifact_path", evidence_artifact_path),
        ("candidate_description_path", slot["candidate_description_path"]),
        ("authority_command", authority_command),
        ("verdict_path", attempt_paths["verdict_path"]),
        ("report_command", report_command),
        ("allowed_evidence_categories", allowed_categories),
        ("report_path_line_prefix", REPORT_PATH_LINE_PREFIX),
        ("authority_failure_line_prefix", AUTHORITY_FAILURE_LINE_PREFIX),
    ):
        body = body.replace("{" + key + "}", value)
    return body


def _attempt_paths(slot_dir, attempt_number):
    attempt_dir = Path(slot_dir) / f"attempt-{attempt_number:02d}"
    prompt_path = attempt_dir / _PROMPT_FILENAME
    return {
        "attempt_number": attempt_number,
        "attempt_dir": str(attempt_dir),
        "reviewer_prompt_path": str(prompt_path),
        "verdict_path": str(attempt_dir / _VERDICT_FILENAME),
        "report_path": str(attempt_dir / _REPORT_FILENAME),
        # generated here so the dispatching agent sends it verbatim and never
        # hand-writes the prompt path into a dispatch message
        "dispatch_bootstrap": (
            f"Read the file {prompt_path} completely and execute the "
            "instructions in it."
        ),
    }


def _materialize_attempt(*, slot, attempt_paths, evidence_artifact_path, run_dir):
    Path(attempt_paths["attempt_dir"]).mkdir(parents=True, exist_ok=True)
    prompt = _render_reviewer_prompt(
        slot=slot,
        attempt_paths=attempt_paths,
        evidence_artifact_path=evidence_artifact_path,
        run_dir=run_dir,
    )
    Path(attempt_paths["reviewer_prompt_path"]).write_text(prompt, encoding="utf-8")


def _write_manifest(manifest):
    manifest_path = Path(manifest["run_dir"]) / MANIFEST_FILENAME
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def prepare_round(*, extracted_artifact_path, candidates, run_root=None):
    """Lay out one review round: a unique run directory holding the delivered
    evidence artifact, one slot per candidate, and each slot's first attempt
    with its instantiated reviewer prompt and preassigned verdict and report
    paths. Returns the manifest, which is also persisted into the run
    directory. Fails before creating any layout when the round is empty, a
    candidate is invalid, or the evidence cutoff boundary cannot be achieved.
    """
    if not candidates:
        raise ValueError("a round needs at least one candidate; no candidates given")
    validated = [_validate_candidate(candidate) for candidate in candidates]
    # Prove the cutoff boundary is achievable before any directory exists, so
    # a boundary failure leaves nothing that looks dispatchable.
    lines, records = _read_artifact_lines(extracted_artifact_path)
    _cut_lines_at_latest_user_prompt(lines, records, extracted_artifact_path)

    root = Path(run_root) if run_root is not None else Path(tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    run_dir = root / f"adr-{OPERATION_NAME}-{secrets.token_hex(8)}"
    run_dir.mkdir(parents=True, exist_ok=False)

    evidence = write_evidence_artifact(
        extracted_artifact_path, run_dir / _EVIDENCE_RELATIVE_PATH
    )
    evidence_path = Path(evidence["evidence_artifact_path"])

    slots = []
    for slot_number, candidate in enumerate(validated, start=1):
        slot_dir = run_dir / f"slot-{slot_number:02d}"
        slot_dir.mkdir(parents=True, exist_ok=False)
        description_path = slot_dir / _DESCRIPTION_FILENAME
        description_path.write_text(candidate["candidate_description"], encoding="utf-8")
        slot = {
            "slot_number": slot_number,
            "slot_dir": str(slot_dir),
            "mode": candidate["mode"],
            "modify_target_path": candidate["modify_target_path"],
            "candidate_description_path": str(description_path),
            "attempts": [],
        }
        attempt = _attempt_paths(slot_dir, 1)
        _materialize_attempt(
            slot=slot,
            attempt_paths=attempt,
            evidence_artifact_path=str(evidence_path),
            run_dir=str(run_dir),
        )
        slot["attempts"].append(attempt)
        slots.append(slot)

    manifest = {
        "operation": OPERATION_NAME,
        "run_dir": str(run_dir),
        "evidence_artifact_path": str(evidence_path),
        "evidence_line_count": evidence["line_count"],
        "latest_user_prompt_line": evidence["latest_user_prompt_line"],
        "slots": slots,
    }
    _write_manifest(manifest)
    return manifest


def _load_manifest(run_dir):
    manifest_path = Path(run_dir) / MANIFEST_FILENAME
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"run manifest is unreadable: {manifest_path}") from error


def _find_slot(manifest, slot_number):
    for slot in manifest["slots"]:
        if slot["slot_number"] == slot_number:
            return slot
    raise ValueError(f"no slot {slot_number} in run {manifest['run_dir']}")


def prepare_attempt(run_dir, slot_number):
    """Add one fresh, fully isolated attempt to a slot for a redispatched
    reviewer: a new attempt directory, prompt file, and preassigned verdict
    and report paths, over the same fixed review inputs. A late write from an
    earlier attempt can therefore never land on the paths the current attempt
    is awaited on. Updates and re-persists the manifest."""
    manifest = _load_manifest(run_dir)
    slot = _find_slot(manifest, slot_number)
    attempt = _attempt_paths(slot["slot_dir"], len(slot["attempts"]) + 1)
    _materialize_attempt(
        slot=slot,
        attempt_paths=attempt,
        evidence_artifact_path=manifest["evidence_artifact_path"],
        run_dir=manifest["run_dir"],
    )
    slot["attempts"].append(attempt)
    _write_manifest(manifest)
    return attempt


# ---------------------------------------------------------------------------
# closed verdict JSON validation
# ---------------------------------------------------------------------------

_VERDICT_KEYS = {
    "description_reviewability",
    "explicit_disclosure",
    "user_ratification",
    "adr_carrier_suitability",
    "necessity_conditions",
    "parts_analysis",
}
_RATIFICATION_CHECK_KEYS = ("explicit_disclosure", "user_ratification")
_JUDGMENT_KEYS = {"result", "evidence_lines", "reason"}
_JUDGMENT_RESULTS = {"pass", "fail"}
_REVIEWABILITY_RESULTS = {"reviewable", "not_reviewable"}

_NOT_EVALUATED = {"status": "not_evaluated"}


def _allowed_evidence_line_numbers(evidence_artifact_path):
    _, records = _read_artifact_lines(evidence_artifact_path)
    return {
        number
        for number, record in enumerate(records, start=1)
        if isinstance(record, dict)
        and record.get("type") in ALLOWED_EVIDENCE_CATEGORIES
    }, len(records)


def _judgment_shape_reason(judgment):
    if not isinstance(judgment, dict) or set(judgment) != _JUDGMENT_KEYS:
        return "judgment_invalid"
    if judgment["result"] not in _JUDGMENT_RESULTS:
        return "judgment_invalid"
    if not isinstance(judgment["reason"], str) or not judgment["reason"].strip():
        return "judgment_invalid"
    lines = judgment["evidence_lines"]
    if not isinstance(lines, list) or any(
        not isinstance(line, int) or isinstance(line, bool) for line in lines
    ):
        return "judgment_invalid"
    # a pass asserts positive evidence, so it must point at where that
    # evidence lives; a fail may legitimately have nothing to cite
    if judgment["result"] == "pass" and not lines:
        return "pass_without_evidence_lines"
    return None


def _judgment_lines_reason(judgment, allowed_lines, line_count):
    for line in judgment["evidence_lines"]:
        if line < 1 or line > line_count:
            return "evidence_line_out_of_range"
        if line not in allowed_lines:
            return "evidence_line_category_not_allowed"
    return None


def _iter_semantic_judgments(verdict):
    for key in _RATIFICATION_CHECK_KEYS:
        if key in verdict:
            yield verdict[key]
    if "adr_carrier_suitability" in verdict:
        yield verdict["adr_carrier_suitability"]
    for judgment in verdict.get("necessity_conditions", {}).values():
        yield judgment


def validate_verdict(verdict, *, evidence_artifact_path, condition_names):
    """Validate the reviewer's minimal closed verdict JSON. Returns
    ``(ok, reason)`` — a structured signal, never a crash.

    The schema is closed in both directions: unknown keys invalidate, and the
    fail-fast structure is enforced — later judgments may be omitted only when
    an earlier gate stopped the review, and once condition judgment was
    entered the verdict must carry exactly the loaded authority's full
    condition set. Every cited evidence line must exist in the delivered
    artifact and point at an allowed content category."""
    if not isinstance(verdict, dict):
        return False, "verdict_not_a_mapping"
    if set(verdict) - _VERDICT_KEYS:
        return False, "verdict_key_unknown"
    if "description_reviewability" not in verdict:
        return False, "description_reviewability_missing"
    reviewability = verdict["description_reviewability"]
    if not (
        isinstance(reviewability, dict)
        and set(reviewability) == {"result", "reason"}
        and reviewability["result"] in _REVIEWABILITY_RESULTS
        and isinstance(reviewability["reason"], str)
        and reviewability["reason"].strip()
    ):
        return False, "description_reviewability_invalid"

    semantic_keys = set(verdict) - {"description_reviewability", "parts_analysis"}
    if reviewability["result"] == "not_reviewable":
        if semantic_keys:
            return False, "judgments_present_after_fail_fast"
    else:
        if not all(key in verdict for key in _RATIFICATION_CHECK_KEYS):
            return False, "ratification_evidence_check_missing"

    if "parts_analysis" in verdict and (
        not isinstance(verdict["parts_analysis"], str)
        or not verdict["parts_analysis"].strip()
    ):
        return False, "parts_analysis_invalid"

    conditions = verdict.get("necessity_conditions")
    if conditions is not None and not isinstance(conditions, dict):
        return False, "necessity_conditions_not_a_mapping"

    for judgment in _iter_semantic_judgments(verdict):
        reason = _judgment_shape_reason(judgment)
        if reason is not None:
            return False, reason

    if reviewability["result"] == "reviewable":
        ratification_passed = all(
            verdict[key]["result"] == "pass" for key in _RATIFICATION_CHECK_KEYS
        )
        if not ratification_passed:
            if "adr_carrier_suitability" in verdict:
                return False, "carrier_suitability_present_after_fail_fast"
            if conditions is not None:
                return False, "conditions_present_after_fail_fast"
        elif "adr_carrier_suitability" not in verdict:
            return False, "adr_carrier_suitability_missing"
        elif verdict["adr_carrier_suitability"]["result"] == "fail":
            if conditions is not None:
                return False, "conditions_present_after_fail_fast"
        elif conditions is None:
            return False, "necessity_conditions_missing"
        if conditions is not None and set(conditions) != set(condition_names):
            return False, "condition_set_mismatch"

    try:
        allowed_lines, line_count = _allowed_evidence_line_numbers(evidence_artifact_path)
    except ValueError:
        return False, "evidence_artifact_unreadable"
    for judgment in _iter_semantic_judgments(verdict):
        reason = _judgment_lines_reason(judgment, allowed_lines, line_count)
        if reason is not None:
            return False, reason
    return True, None


# ---------------------------------------------------------------------------
# mechanical report assembly
# ---------------------------------------------------------------------------


def _derive_rejected_at(verdict):
    """The semantic stage that stopped a validated verdict's candidate, or
    None when every stage passed. The validated fail-fast structure guarantees
    each stage's judgment exists whenever every earlier stage passed, so this
    walk never meets a missing key."""
    if verdict["description_reviewability"]["result"] != "reviewable":
        return "description_reviewability"
    if any(verdict[key]["result"] == "fail" for key in _RATIFICATION_CHECK_KEYS):
        return "conversation_decision_ratification_evidence_check"
    if verdict["adr_carrier_suitability"]["result"] == "fail":
        return "adr_carrier_suitability"
    if any(
        judgment["result"] == "fail"
        for judgment in verdict["necessity_conditions"].values()
    ):
        return "necessity_conditions"
    return None


def build_report(verdict):
    """Assemble the final report from a validated verdict. The reviewer wrote
    only the semantic judgments; the overall result, the rejected_at stage
    marker, and the not-evaluated states of gates a fail-fast never reached
    are derived here. The report deliberately carries nothing the slot already
    pairs mechanically — no candidate data, mode, target, paths, hashes,
    timestamps, or any second status projection of the same judgments."""
    ratification = {
        key: verdict.get(key, dict(_NOT_EVALUATED)) for key in _RATIFICATION_CHECK_KEYS
    }
    rejected_at = _derive_rejected_at(verdict)
    return {
        "overall_result": "approved" if rejected_at is None else "rejected",
        "description_reviewability": verdict["description_reviewability"],
        "conversation_decision_ratification_evidence_check": ratification,
        "adr_carrier_suitability": verdict.get(
            "adr_carrier_suitability", dict(_NOT_EVALUATED)
        ),
        "necessity_conditions": verdict.get("necessity_conditions", dict(_NOT_EVALUATED)),
        "rejected_at": rejected_at,
        "parts_analysis": verdict.get("parts_analysis"),
    }


def write_check_report(*, verdict, evidence_artifact_path, condition_names, report_path):
    """Validate the verdict, assemble the report, and persist it to the
    preassigned report path. Returns a valid result carrying the report and
    its fixed-format path line, or a structured invalid result — never a
    crash, and no file is written on an invalid verdict."""
    ok, reason = validate_verdict(
        verdict,
        evidence_artifact_path=evidence_artifact_path,
        condition_names=condition_names,
    )
    if not ok:
        return {"status": "invalid", "reason": reason}
    report = build_report(verdict)
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return {
        "status": "valid",
        "report_path": str(report_path),
        "report": report,
        "path_line": report_path_line(str(report_path)),
    }


def report_path_line(report_path):
    """The single fixed-prefix line the reviewer's final reply must contain so
    the main agent can extract the report location amid any surrounding
    prose."""
    return f"{REPORT_PATH_LINE_PREFIX} {report_path}"


# ---------------------------------------------------------------------------
# reviewer reply resolution
# ---------------------------------------------------------------------------

_REPORT_KEYS = {
    "overall_result",
    "description_reviewability",
    "conversation_decision_ratification_evidence_check",
    "adr_carrier_suitability",
    "necessity_conditions",
    "rejected_at",
    "parts_analysis",
}


def extract_report_path(reviewer_reply):
    """Mechanically extract the delivered report path from a reply that may
    carry extra prose. The last path line wins (an earlier line may precede a
    fixed-and-rerun report command); returns None when no path line exists."""
    matches = _REPORT_PATH_LINE_RE.findall(reviewer_reply)
    if not matches:
        return None
    return matches[-1].strip()


def resolve_reviewer_reply(
    reviewer_reply,
    *,
    expected_report_path,
    verdict_path=None,
    evidence_artifact_path=None,
    condition_names=None,
):
    """Resolve a reviewer's final reply into a validated report, an authority
    input failure, or a structured invalid result.

    An authority-failure line outranks everything else in the reply — an
    ambiguous reply must fail closed, and an authority failure is repaired by
    fixing the input, never by trusting a report delivered around it. A valid
    resolution requires the extracted path to equal the preassigned path, so
    a reviewer can never redirect the main agent to a file the preparer did
    not assign.

    The three optional expectations close the loop the reviewer-side report
    command cannot (there the reviewer supplies both sides): given the slot's
    preassigned verdict path, the delivered evidence artifact, and the
    authority's condition names, the persisted verdict is revalidated and the
    report must equal its mechanical derivation — so a hand-written or
    tampered report file never resolves as a review result."""
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
        ok, _ = validate_verdict(
            verdict,
            evidence_artifact_path=evidence_artifact_path,
            condition_names=condition_names,
        )
        if not ok:
            return {"status": "invalid", "reason": "persisted_verdict_invalid"}
        if report != build_report(verdict):
            return {"status": "invalid", "reason": "report_not_mechanically_derived"}
    return {"status": "valid", "report": report, "report_path": report_path}


# ---------------------------------------------------------------------------
# redispatch stop accounting
# ---------------------------------------------------------------------------


def redispatch_decision(failure_classes):
    """Decide the next action after a slot's attempt failures, oldest first.

    Authority input failures never consume the attempt budget — a broken
    authority is not repaired by a fresh reviewer, so the only action is to
    fix the input. Reviewer-attempt failures stop on the earlier of: the same
    class twice in consecutive reviewer attempts (a systematic signal a fresh
    reviewer already failed to clear), or the total attempt budget."""
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
# CLI entry points
# ---------------------------------------------------------------------------


def _load_authority_condition_names():
    """The condition names the verdict must cover, read fresh from the skill's
    own authority file. Any read or structure failure propagates: an invalid
    authority fails the whole delivery closed instead of shrinking the
    required condition set."""
    loaded = necessity_conditions_authority.read_necessity_conditions()
    return loaded["structure_validation"]["condition_names"]


def _find_attempt(slot, attempt_number):
    for attempt in slot["attempts"]:
        if attempt["attempt_number"] == attempt_number:
            return attempt
    raise ValueError(
        f"no attempt {attempt_number} in slot {slot['slot_number']}"
    )


def _cli_prepare_round(input_json_path):
    round_input = json.loads(Path(input_json_path).read_text(encoding="utf-8"))
    manifest = prepare_round(
        extracted_artifact_path=round_input["extracted_artifact_path"],
        candidates=round_input["candidates"],
        run_root=round_input.get("run_root"),
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


def _cli_prepare_attempt(run_dir, slot_number):
    attempt = prepare_attempt(run_dir, int(slot_number))
    print(json.dumps(attempt, indent=2, ensure_ascii=False))
    return 0


def _cli_report(run_dir, slot_number, attempt_number):
    manifest = _load_manifest(run_dir)
    slot = _find_slot(manifest, int(slot_number))
    attempt = _find_attempt(slot, int(attempt_number))
    try:
        condition_names = _load_authority_condition_names()
    except Exception as error:  # noqa: BLE001 — every authority failure fails closed
        print(f"{AUTHORITY_FAILURE_LINE_PREFIX} {error}")
        return 1
    try:
        verdict = json.loads(Path(attempt["verdict_path"]).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print("INVALID_VERDICT: verdict_file_unreadable")
        return 1
    result = write_check_report(
        verdict=verdict,
        evidence_artifact_path=manifest["evidence_artifact_path"],
        condition_names=condition_names,
        report_path=attempt["report_path"],
    )
    if result["status"] == "valid":
        print(result["path_line"])
        return 0
    print(f"INVALID_VERDICT: {result['reason']}")
    return 1


def _cli_resolve_reply(run_dir, slot_number, attempt_number):
    manifest = _load_manifest(run_dir)
    slot = _find_slot(manifest, int(slot_number))
    attempt = _find_attempt(slot, int(attempt_number))
    try:
        condition_names = _load_authority_condition_names()
    except Exception as error:  # noqa: BLE001 — every authority failure fails closed
        resolution = {"status": "authority_input_failure", "reason": str(error)}
    else:
        resolution = resolve_reviewer_reply(
            sys.stdin.read(),
            expected_report_path=attempt["report_path"],
            verdict_path=attempt["verdict_path"],
            evidence_artifact_path=manifest["evidence_artifact_path"],
            condition_names=condition_names,
        )
    print(json.dumps(resolution, indent=2, ensure_ascii=False))
    return 0 if resolution["status"] == "valid" else 1


def main(argv):
    """CLI dispatcher. `prepare-round <input_json>` and `prepare-attempt
    <run_dir> <slot>` serve the orchestrating agent; `report <run_dir> <slot>
    <attempt>` is run by the reviewer to validate its verdict and obtain the
    one path line; `resolve-reply <run_dir> <slot> <attempt>` reads the
    reviewer's reply from stdin and resolves it against the preassigned
    report path."""
    if not argv:
        raise ValueError("missing subcommand")
    subcommand, *arguments = argv
    handlers = {
        "prepare-round": _cli_prepare_round,
        "prepare-attempt": _cli_prepare_attempt,
        "report": _cli_report,
        "resolve-reply": _cli_resolve_reply,
    }
    if subcommand not in handlers:
        raise ValueError(f"unknown subcommand: {subcommand}")
    return handlers[subcommand](*arguments)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
