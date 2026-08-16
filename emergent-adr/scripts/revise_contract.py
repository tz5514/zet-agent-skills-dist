"""Mechanical revise orchestration contract helpers.

`revise` is the scan-free draft ADR quality operation: it owns the acceptance
review/repair loop, disposition dispatch, degraded support-data handling, and
the detailed structured report for quality work. It does not run supersession
scans, scan-rewrite loops, scan-result invalidation reruns, or promotion.
Findings that need supersession-scan evidence are classified here and returned
to the caller. Callers that own scanning pass the current scan state so the
existing repetition-finding reclassification rule still applies, and pass
already-consumed review rounds so one delivery budget continues across calls.
Sub-operations (`write`, `quality-review`) are injected as callables.
`revise` never builds a new draft; repairs use `write`'s modify mode.
Final-status values reuse the definitions owned by `produce`'s spec, plus the
`needs_scan_evidence` hand-back this operation surfaces.
"""

import json
from pathlib import Path

from adr_id import is_adr_id
from supersession_pairs import expand_atomic_decision_pairs


OPERATION = "revise"

# The draft ADR acceptance check review loop is bounded at seven rounds — enough
# convergence room while still stopping write oscillation and unbounded spend.
MAX_REVIEW_ROUNDS = 7

REPORT_FILENAME = "revise_report.json"

# revise names its modes at its own level and maps them to quality-review's named
# modes; the interview-time preflight is never usable for revise.
FULL_QUALITY_REVIEW = "full_quality_review"
FROZEN_GLOSSARY_QUALITY_REVIEW = "frozen_glossary_quality_review"
QUALITY_REVIEW_MODE_MAP = {
    FULL_QUALITY_REVIEW: "quality_review",
    FROZEN_GLOSSARY_QUALITY_REVIEW: "frozen_glossary_review",
}

GLOSSARY_APPROVAL_GATE = "context_glossary_approval_need_check"
REPETITION_GATE = "live_active_atomic_decision_repetition_check"
SOURCE_PRESERVATION_GATE = "source_decision_preservation_check"
_SUPPORT_DEPENDENT_GATES = {SOURCE_PRESERVATION_GATE, REPETITION_GATE}

FINAL_PASSED = "passed"
FINAL_NEEDS_SCAN_EVIDENCE = "needs_scan_evidence"
FINAL_NEEDS_USER_RULING = "needs_user_ruling"
FINAL_BLOCKED_AFTER_REVIEW_LIMIT = "blocked_after_review_limit"
FINAL_FAILED = "failed"

# Every blocking finding is dispatched to exactly one disposition class — the
# machine answer to "who resolves this finding, with what means". The classes
# are derived data owned by revise: the reviewer never sees or assigns them.
DISPOSITION_USER_RULING = "user_ruling"
DISPOSITION_WRITER_REPAIR = "writer_repair"
DISPOSITION_SCAN_EVIDENCE = "scan_evidence"
DISPOSITION_CLASSES = {
    DISPOSITION_USER_RULING,
    DISPOSITION_WRITER_REPAIR,
    DISPOSITION_SCAN_EVIDENCE,
}

DISPOSITION_RESULT_FIXED_BY_WRITE_MODIFY = "fixed_by_write_modify"
DISPOSITION_RESULT_RETURNED_FOR_SCAN_EVIDENCE = "returned_for_scan_evidence"
DISPOSITION_RESULT_NOT_DISPOSITIONED_DUE_TO_USER_RULING = "not_dispositioned_due_to_user_ruling"
DISPOSITION_RESULTS = {
    DISPOSITION_RESULT_FIXED_BY_WRITE_MODIFY,
    DISPOSITION_RESULT_RETURNED_FOR_SCAN_EVIDENCE,
    DISPOSITION_RESULT_NOT_DISPOSITIONED_DUE_TO_USER_RULING,
}


def classify_blocking_findings(blocking, scan_state=None, *, quality_review_mode):
    """Dispatch each blocking finding to its disposition class, mechanically,
    from the finding's gate id. The glossary approval gate maps to a user ruling
    only under the full mode — the frozen review never runs that gate, so
    nothing routes to a user ruling there.

    `scan_state` is None unless the caller supplies a non-invalidated completed
    scan result for the current `## Atomic Decisions`. When it exists, a
    repeated-live finding no longer routes to a scan: either the scan found no
    supersession for the decision the finding points at (an accidental
    restatement the writer repairs) or it did (an authority clash between
    review and scan that only the user may settle). When the caller omits
    scan state, scan-evidence findings stay classified as scan_evidence and
    are handed back — revise never invents a scan state."""
    classified = []
    for finding in blocking:
        entry = {"finding": finding}
        if finding.get("gate_id") == REPETITION_GATE:
            if scan_state is None:
                entry["disposition_class"] = DISPOSITION_SCAN_EVIDENCE
            elif _repetition_relationship_established(
                finding, scan_state.get("written_supersedes") or []
            ):
                entry["disposition_class"] = DISPOSITION_USER_RULING
                entry["scan_review_conflict"] = True
            else:
                entry["disposition_class"] = DISPOSITION_WRITER_REPAIR
                entry["reclassified_from_scan_evidence"] = True
        elif (
            finding.get("gate_id") == GLOSSARY_APPROVAL_GATE
            and quality_review_mode == FULL_QUALITY_REVIEW
        ):
            entry["disposition_class"] = DISPOSITION_USER_RULING
        else:
            entry["disposition_class"] = DISPOSITION_WRITER_REPAIR
        classified.append(entry)
    return classified


def _repetition_relationship_established(finding, written_supersedes):
    """Whether the scan-established `supersedes` relationships cover the still-
    live active decision this repeated-live finding points at. The finding may
    carry a revise-side `repeated_live_decision` identity (attached by the
    orchestrating agent, never by the reviewer); without one, any established
    relationship is conservatively treated as covering — a wrong repair could
    delete content that legally restates a superseded decision, while a user
    hand-off is always safe."""
    identity = finding.get("repeated_live_decision")
    if identity is None:
        return bool(written_supersedes)
    for entry in written_supersedes:
        candidate = entry.get("candidate") or {}
        if not _candidate_matches_live(candidate.get("adr"), identity):
            continue
        for pair in expand_atomic_decision_pairs(entry.get("atomic_decisions") or [], block_key="supersedes"):
            if (
                pair.get("ours") == identity.get("target_atomic_decision_id")
                and pair.get("theirs") == identity.get("atomic_decision_id")
            ):
                return True
    return False


def _candidate_matches_live(adr_ref, identity):
    active_adr = identity.get("active_adr")
    if (
        isinstance(adr_ref, str) and adr_ref
        and isinstance(active_adr, str) and active_adr
        # the scan candidate reference is a bare filename while the identity may
        # carry a path: both resolve by basename
        and Path(adr_ref).name == Path(active_adr).name
    ):
        return True
    return bool(
        isinstance(adr_ref, str)
        and is_adr_id(adr_ref)
        and adr_ref == identity.get("active_adr_number")
    )


def has_scan_evidence_blocking_finding(classified):
    return any(item["disposition_class"] == DISPOSITION_SCAN_EVIDENCE for item in classified)


def has_writer_repair_blocking_finding(classified):
    return any(item["disposition_class"] == DISPOSITION_WRITER_REPAIR for item in classified)


def has_user_ruling_blocking_finding(classified):
    return any(item["disposition_class"] == DISPOSITION_USER_RULING for item in classified)


def _dispositions(classified, result_by_class):
    """Per-finding report rows: the classified entry (finding, class, and any
    reclassification/conflict marker) plus the class's disposition result for
    how this round ended (None while undispositioned)."""
    return [
        {**item, "disposition_result": result_by_class.get(item["disposition_class"])}
        for item in classified
    ]


def resolve_quality_review_mode(inputs):
    """Map the revise-level `quality_review_mode` to a quality-review named mode.
    Missing or unrecognised (including the preflight mode) aborts immediately."""
    mode = inputs.get("quality_review_mode")
    if mode not in QUALITY_REVIEW_MODE_MAP:
        raise ValueError(
            "revise requires quality_review_mode to be one of "
            f"{sorted(QUALITY_REVIEW_MODE_MAP)}; got {mode!r}"
        )
    return QUALITY_REVIEW_MODE_MAP[mode]


def run_revise(*, inputs, write_fn, quality_review_fn, run_dir):
    """Run scan-free quality review/repair. Optional `scan_state` lets the
    caller apply the established-relationship reclassification rule; omitting
    it means any scan-evidence finding is handed back without speculation.
    Optional `rounds_already_consumed` continues the shared review budget from
    that count instead of zero; this call reports how many rounds it consumed.
    """
    review_mode = resolve_quality_review_mode(inputs)
    quality_review_mode = inputs["quality_review_mode"]
    draft_adr_path = inputs["draft_adr_path"]
    scan_state = inputs.get("scan_state")
    rounds_already_consumed = int(inputs.get("rounds_already_consumed") or 0)
    if rounds_already_consumed < 0:
        raise ValueError("rounds_already_consumed must be >= 0")
    if rounds_already_consumed >= MAX_REVIEW_ROUNDS:
        state = _State(draft_adr_path=draft_adr_path, run_dir=run_dir)
        return state.finalize(
            final_status=FINAL_BLOCKED_AFTER_REVIEW_LIMIT,
            needs_user_ruling=False,
            rounds_consumed=0,
            unresolved_blocking_findings=[],
        )

    state = _State(draft_adr_path=draft_adr_path, run_dir=run_dir)
    start_round = rounds_already_consumed + 1

    for round_num in range(start_round, MAX_REVIEW_ROUNDS + 1):
        review = quality_review_fn(_review_request(draft_adr_path, review_mode, inputs))
        state.record_round(round_num, review)
        blocking = review["blocking"]
        if not blocking:
            return state.finalize(
                final_status=FINAL_PASSED,
                needs_user_ruling=False,
                rounds_consumed=round_num - rounds_already_consumed,
            )
        classified = classify_blocking_findings(
            blocking,
            scan_state,
            quality_review_mode=quality_review_mode,
        )
        if has_user_ruling_blocking_finding(classified):
            # user-ruling-only finding: stop immediately, do not count a repair round
            state.record_dispositions(
                _dispositions(
                    classified,
                    dict.fromkeys(
                        DISPOSITION_CLASSES,
                        DISPOSITION_RESULT_NOT_DISPOSITIONED_DUE_TO_USER_RULING,
                    ),
                )
            )
            glossary_findings = _glossary_findings(blocking)
            return state.finalize(
                final_status=FINAL_NEEDS_USER_RULING,
                needs_user_ruling=True,
                rounds_consumed=round_num - rounds_already_consumed,
                ruling_request={
                    "origin": "quality_review" if glossary_findings else "scan_review_conflict",
                    "glossary_approval_findings": glossary_findings,
                    "scan_review_conflicts": [
                        item["finding"] for item in classified if item.get("scan_review_conflict")
                    ],
                },
            )
        if round_num < MAX_REVIEW_ROUNDS:
            result_by_class = {}
            if has_writer_repair_blocking_finding(classified):
                write_result = write_fn(_repair_request(draft_adr_path, inputs, classified))
                if write_result.get("status") == "needs_context_ruling":
                    if quality_review_mode == FROZEN_GLOSSARY_QUALITY_REVIEW:
                        # frozen invariant breach: under the frozen glossary a repair
                        # write must not open a context ruling — a process error
                        state.record_dispositions(_dispositions(classified, {}))
                        return state.finalize(
                            final_status=FINAL_FAILED,
                            needs_user_ruling=False,
                            rounds_consumed=round_num - rounds_already_consumed,
                            unresolved_blocking_findings=blocking,
                            errors=[{
                                "stage": "repair_write",
                                "kind": "frozen_glossary_context_ruling",
                                "detail": write_result,
                            }],
                        )
                    # full mode: the glossary is not frozen, so a repair write that
                    # surfaces a CONTEXT.md ruling need is a user hand-off
                    state.record_dispositions(
                        _dispositions(
                            classified,
                            dict.fromkeys(
                                DISPOSITION_CLASSES,
                                DISPOSITION_RESULT_NOT_DISPOSITIONED_DUE_TO_USER_RULING,
                            ),
                        )
                    )
                    return state.finalize(
                        final_status=FINAL_NEEDS_USER_RULING,
                        needs_user_ruling=True,
                        rounds_consumed=round_num - rounds_already_consumed,
                        unresolved_blocking_findings=blocking,
                        ruling_request={
                            "origin": "repair_write",
                            "context_ruling": write_result.get("context_ruling"),
                        },
                    )
                result_by_class[DISPOSITION_WRITER_REPAIR] = DISPOSITION_RESULT_FIXED_BY_WRITE_MODIFY
            if has_scan_evidence_blocking_finding(classified):
                # scan ownership sits with the caller: hand back after any same-
                # round writer repair, never run or invent a scan here
                result_by_class[DISPOSITION_SCAN_EVIDENCE] = (
                    DISPOSITION_RESULT_RETURNED_FOR_SCAN_EVIDENCE
                )
                state.record_dispositions(_dispositions(classified, result_by_class))
                return state.finalize(
                    final_status=FINAL_NEEDS_SCAN_EVIDENCE,
                    needs_user_ruling=False,
                    rounds_consumed=round_num - rounds_already_consumed,
                    scan_evidence_findings=[
                        item["finding"]
                        for item in classified
                        if item["disposition_class"] == DISPOSITION_SCAN_EVIDENCE
                    ],
                    unresolved_blocking_findings=blocking,
                )
            state.record_dispositions(_dispositions(classified, result_by_class))
        else:
            # the limit round gets no repair write, so its findings end the run
            # classified but undispositioned
            state.record_dispositions(_dispositions(classified, {}))

    return state.finalize(
        final_status=FINAL_BLOCKED_AFTER_REVIEW_LIMIT,
        needs_user_ruling=False,
        rounds_consumed=MAX_REVIEW_ROUNDS - rounds_already_consumed,
        unresolved_blocking_findings=state.last_blocking(),
    )


class _State:
    def __init__(self, *, draft_adr_path, run_dir):
        self.draft_adr_path = draft_adr_path
        self.run_dir = run_dir
        self.rounds = []
        self.degradation_notes = []
        self.evidence_status = "clean"

    def record_round(self, round_num, review):
        self.rounds.append({
            "round": round_num,
            "review_status": review["review_status"],
            "blocking": review["blocking"],
            "non_blocking": review.get("non_blocking", []),
            "support_data_status": review.get("support_data_status"),
            "source_decision_extract_status": review.get("source_decision_extract_status"),
            "live_atomic_decision_corpus_status": review.get(
                "live_atomic_decision_corpus_status"
            ),
            "gate_coverage": review.get("gate_coverage"),
            "report_path": review.get("report_path"),
            # per-round provenance, supplied by the orchestrating caller when
            # available: which artifacts this round actually reviewed, and
            # whether the reviewed artifact still matches the final one
            "reviewer_close_status": review.get("reviewer_close_status"),
            "target_adr_path": review.get("target_adr_path"),
            "source_decision_extract_path": review.get("source_decision_extract_path"),
            "live_atomic_decision_corpus_path": review.get("live_atomic_decision_corpus_path"),
            "reviewed_artifact_matches_final": review.get("reviewed_artifact_matches_final"),
            "blocking_finding_dispositions": [],
        })
        self.degradation_notes.extend(review.get("scope_limitations", []))
        if _reviewer_evidence_is_degraded(review):
            self.evidence_status = "degraded_reviewer_evidence"

    def record_dispositions(self, dispositions):
        self.rounds[-1]["blocking_finding_dispositions"] = dispositions

    def last_blocking(self):
        return self.rounds[-1]["blocking"] if self.rounds else []

    def finalize(
        self,
        *,
        final_status,
        needs_user_ruling,
        rounds_consumed,
        ruling_request=None,
        scan_evidence_findings=None,
        unresolved_blocking_findings=None,
        errors=None,
    ):
        report = {
            "operation": OPERATION,
            "final_status": final_status,
            "draft_adr_path": self.draft_adr_path,
            "structured_report_path": None,
            "needs_user_ruling": needs_user_ruling,
            "ruling_request": ruling_request,
            "rounds_consumed": rounds_consumed,
            "scan_evidence_findings": list(scan_evidence_findings or []),
            "quality_review_rounds": self.rounds,
            "final_review_state": (
                self.rounds[-1]["review_status"] if self.rounds else None
            ),
            "unresolved_blocking_findings": list(unresolved_blocking_findings or []),
            "refused_findings": [],
            "degradation_notes": list(self.degradation_notes),
            "child_report_paths": [r["report_path"] for r in self.rounds if r.get("report_path")],
            "skipped_steps": [],
            "evidence_status": self.evidence_status,
            "errors": list(errors or []),
        }
        run_dir = Path(self.run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        report_path = run_dir / REPORT_FILENAME
        report["structured_report_path"] = str(report_path)
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"direct_output": _direct_output(report), "report": report}


def _reviewer_evidence_is_degraded(review):
    if any(
        review.get(status_key) != "provided"
        for status_key in (
            "support_data_status",
            "source_decision_extract_status",
            "live_atomic_decision_corpus_status",
        )
    ):
        return True
    gate_coverage = review.get("gate_coverage")
    return not isinstance(gate_coverage, dict) or any(
        gate_coverage.get(gate_id) != "evaluated"
        for gate_id in _SUPPORT_DEPENDENT_GATES
    )


def _glossary_findings(blocking):
    return [f for f in blocking if f.get("gate_id") == GLOSSARY_APPROVAL_GATE]


def _review_request(draft_adr_path, review_mode, inputs):
    return {
        "target_adr_path": draft_adr_path,
        "review_mode": review_mode,
        "source_decision_extract_path": inputs.get("source_decision_extract_path"),
    }


def _repair_request(draft_adr_path, inputs, classified):
    # a repair write resolves only this round's writer-repair findings; it may
    # not hand-write `supersedes` and may not touch the atomic decisions a
    # scan-evidence finding points at (those close through the caller's scan)
    return {
        "mode": "modify",
        "target_adr_path": draft_adr_path,
        "source_material": inputs.get("source_material"),
        "repair_findings": [
            item["finding"]
            for item in classified
            if item["disposition_class"] == DISPOSITION_WRITER_REPAIR
        ],
        "must_not_write_supersedes": True,
        "protected_scan_evidence_findings": [
            item["finding"]
            for item in classified
            if item["disposition_class"] == DISPOSITION_SCAN_EVIDENCE
        ],
    }


def _direct_output(report):
    return {
        "draft_adr_path": report["draft_adr_path"],
        "structured_report_path": report["structured_report_path"],
        "final_status": report["final_status"],
        "needs_user_ruling": report["needs_user_ruling"],
        "rounds_consumed": report["rounds_consumed"],
    }
