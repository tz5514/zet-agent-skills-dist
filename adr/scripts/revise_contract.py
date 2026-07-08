"""Mechanical revise orchestration contract helpers.

`revise` is the draft ADR delivery-completion operation: it owns the flow that
used to live inside `produce` after a successful write — the draft ADR acceptance
review/repair loop, the immediate stop on a full-mode CONTEXT.md glossary
approval finding, degraded support-data handling, the handoff into supersession
scanning, and the detailed structured report. Sub-operations (`write`,
`quality-review`, `scan-supersession`) are injected as callables so the
orchestration can be driven with test doubles, mirroring the produce-for-HITL
contract design. `revise` never builds a new draft; repairs use `write`'s modify
mode. Final-status values reuse the definitions owned by `produce`'s spec.
"""

import json
import re
from pathlib import Path

from adr_id import is_adr_id
from scan_rewrite_contract import (
    TAIL_EVIDENCE_REMOVED_OR_CHANGED,
    atomic_decisions_fingerprint,
    build_scan_rewrite_gate_state,
    build_scan_rewrite_loop_report,
    tail_scan_evidence_diff,
)
from supersession_pairs import expand_atomic_decision_pairs, parse_inline_pair


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
NOT_AN_ADR_CANDIDATE_TERMINAL = "not_an_adr_candidate"

FINAL_PASSED = "passed"
FINAL_NEEDS_USER_RULING = "needs_user_ruling"
FINAL_BLOCKED_AFTER_REVIEW_LIMIT = "blocked_after_review_limit"
FINAL_FAILED = "failed"

# Every blocking finding is dispatched to exactly one disposition class — the
# machine answer to "who resolves this finding, with what means". The classes
# are derived data owned by revise: the reviewer never sees or assigns them.
DISPOSITION_USER_RULING = "user_ruling"
DISPOSITION_WRITER_REPAIR = "writer_repair"
DISPOSITION_SCAN_EVIDENCE = "scan_evidence"
DISPOSITION_TERMINAL = "terminal"
DISPOSITION_CLASSES = {
    DISPOSITION_USER_RULING,
    DISPOSITION_WRITER_REPAIR,
    DISPOSITION_SCAN_EVIDENCE,
    DISPOSITION_TERMINAL,
}

DISPOSITION_RESULT_FIXED_BY_WRITE_MODIFY = "fixed_by_write_modify"
DISPOSITION_RESULT_BY_SCAN_SUPERSESSION = "dispositioned_by_scan_supersession"
DISPOSITION_RESULT_SCAN_AWAITING_REWRITE = "scan_returned_awaiting_rewrite"
DISPOSITION_RESULT_SCAN_AWAITING_REVIEW = "scan_returned_awaiting_review"
DISPOSITION_RESULT_NOT_DISPOSITIONED_DUE_TO_USER_RULING = "not_dispositioned_due_to_user_ruling"
DISPOSITION_RESULT_TERMINAL = "terminal"
DISPOSITION_RESULTS = {
    DISPOSITION_RESULT_FIXED_BY_WRITE_MODIFY,
    DISPOSITION_RESULT_BY_SCAN_SUPERSESSION,
    DISPOSITION_RESULT_SCAN_AWAITING_REWRITE,
    DISPOSITION_RESULT_SCAN_AWAITING_REVIEW,
    DISPOSITION_RESULT_NOT_DISPOSITIONED_DUE_TO_USER_RULING,
    DISPOSITION_RESULT_TERMINAL,
}


def classify_blocking_findings(blocking, terminal_result, scan_state=None, *, quality_review_mode):
    """Dispatch each blocking finding to its disposition class, mechanically,
    from the finding's gate id and the review report's terminal result. A
    `not_an_adr_candidate` terminal overrides every finding in that round. The
    glossary approval gate maps to a user ruling only under the full mode — the
    frozen review never runs that gate, so nothing routes to a user ruling
    there.

    `scan_state` is None unless a non-invalidated completed scan result exists
    for the current `## Atomic Decisions`; when it exists, a repeated-live
    finding no longer routes to a scan: either the scan found no supersession
    for the decision the finding points at (an accidental restatement the writer
    repairs) or it did (an authority clash between review and scan that only the
    user may settle)."""
    classified = []
    for finding in blocking:
        entry = {"finding": finding}
        if terminal_result == NOT_AN_ADR_CANDIDATE_TERMINAL:
            entry["disposition_class"] = DISPOSITION_TERMINAL
        elif finding.get("gate_id") == REPETITION_GATE:
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


def run_revise(*, inputs, write_fn, quality_review_fn, scan_fn, run_dir,
               scan_rewrite_loops=None, accept_rewrite_fn=None, atomic_decisions_fn=None,
               supersedes_fn=None):
    """`scan_rewrite_loops` carries the per-loop bookkeeping of any scan-rewrite
    loops the caller orchestrated outside this helper (built with
    `scan_rewrite_contract.build_scan_rewrite_loop_report`). `accept_rewrite_fn`
    injects the main agent's accept judgement on an `awaiting_rewrite` scan
    return: accepted rewrites drive write-then-immediate-rescan here; without an
    acceptance the pending result stops the flow. `atomic_decisions_fn` reads
    the draft's current `## Atomic Decisions` text for scan freshness, and
    `supersedes_fn` the draft's current frontmatter `supersedes` entries for the
    tail-scan evidence diff baseline — both default to reading the draft file."""
    review_mode = resolve_quality_review_mode(inputs)
    quality_review_mode = inputs["quality_review_mode"]
    draft_adr_path = inputs["draft_adr_path"]
    supersedes_fn = supersedes_fn or _read_draft_supersedes

    state = _State(
        draft_adr_path=draft_adr_path,
        run_dir=run_dir,
        scan_rewrite_loops=scan_rewrite_loops,
    )
    scanner = _Scanner(
        state=state,
        draft_adr_path=draft_adr_path,
        scan_fn=scan_fn,
        write_fn=write_fn,
        accept_rewrite_fn=accept_rewrite_fn,
        atomic_decisions_fn=atomic_decisions_fn or _read_atomic_decisions,
    )

    for round_num in range(1, MAX_REVIEW_ROUNDS + 1):
        review = quality_review_fn(_review_request(draft_adr_path, review_mode, inputs))
        state.record_round(round_num, review)
        blocking = review["blocking"]
        if not blocking:
            outcome = _tail_scan_phase(state, scanner, supersedes_fn(draft_adr_path))
            if outcome is _REREVIEW_REQUIRED:
                if round_num == MAX_REVIEW_ROUNDS:
                    # the pass landed on the last budgeted round and the tail
                    # scan pulled away evidence it relied on: the owed re-review
                    # cannot run, so this never silently passes — and the report
                    # must say why it blocked, because the last round itself had
                    # no blocking findings for the caller to read
                    return state.finalize(
                        final_status=FINAL_BLOCKED_AFTER_REVIEW_LIMIT,
                        needs_user_ruling=False,
                        errors=[{
                            "stage": "tail_scan",
                            "kind": "tail_evidence_rereview_budget_exhausted",
                            "detail": {"tail_evidence_diff": TAIL_EVIDENCE_REMOVED_OR_CHANGED},
                        }],
                    )
                # the tail scan removed or changed evidence the pass round relied
                # on: re-judge acceptance with another round of the same budget
                continue
            return outcome
        terminal_result = review.get("terminal_result")
        classified = classify_blocking_findings(
            blocking,
            terminal_result,
            scanner.fresh_completed_scan_state(),
            quality_review_mode=quality_review_mode,
        )
        if terminal_result == NOT_AN_ADR_CANDIDATE_TERMINAL:
            # only the user can decide the fate of a target that should not be
            # an ADR: stop immediately — no repair, no scan, no new status value
            state.record_dispositions(
                _dispositions(classified, {DISPOSITION_TERMINAL: DISPOSITION_RESULT_TERMINAL})
            )
            return state.finalize(
                final_status=FINAL_NEEDS_USER_RULING,
                needs_user_ruling=True,
                ruling_request={
                    "origin": "quality_review_terminal",
                    "terminal_result": terminal_result,
                    "findings": blocking,
                },
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
                # the repair write precedes any closure scan in the same round —
                # a repair may change `## Atomic Decisions`, so scanning first
                # would immediately invalidate the scan result
                write_result = write_fn(_repair_request(draft_adr_path, inputs, classified))
                if write_result.get("status") == "needs_context_ruling":
                    if quality_review_mode == FROZEN_GLOSSARY_QUALITY_REVIEW:
                        # frozen invariant breach: under the frozen glossary a repair
                        # write must not open a context ruling — a process error
                        state.record_dispositions(_dispositions(classified, {}))
                        return state.finalize(
                            final_status=FINAL_FAILED,
                            needs_user_ruling=False,
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
                        unresolved_blocking_findings=blocking,
                        ruling_request={
                            "origin": "repair_write",
                            "context_ruling": write_result.get("context_ruling"),
                        },
                    )
                result_by_class[DISPOSITION_WRITER_REPAIR] = DISPOSITION_RESULT_FIXED_BY_WRITE_MODIFY
            if has_scan_evidence_blocking_finding(classified):
                # pre-acceptance evidence closure: the scan is this finding's
                # disposition, so it runs before the draft is accepted — only
                # here; rounds without a scan-evidence finding never scan early
                scan_result, gate = scanner.run(SCAN_ROLE_PRE_ACCEPTANCE)
                if gate["pending_scan_result"] is not None:
                    result_by_class[DISPOSITION_SCAN_EVIDENCE] = (
                        DISPOSITION_RESULT_SCAN_AWAITING_REWRITE
                        if scan_result["status"] == "awaiting_rewrite"
                        else DISPOSITION_RESULT_SCAN_AWAITING_REVIEW
                    )
                    state.record_dispositions(_dispositions(classified, result_by_class))
                    return state.finalize(
                        final_status=FINAL_NEEDS_USER_RULING,
                        needs_user_ruling=True,
                        pending_scan_result=gate["pending_scan_result"],
                    )
                if gate["stop_reason"] is not None:
                    state.record_dispositions(_dispositions(classified, result_by_class))
                    return state.finalize(
                        final_status=FINAL_FAILED,
                        needs_user_ruling=False,
                        errors=[{"stage": "scan", "kind": gate["stop_reason"], "detail": scan_result}],
                    )
                result_by_class[DISPOSITION_SCAN_EVIDENCE] = DISPOSITION_RESULT_BY_SCAN_SUPERSESSION
            state.record_dispositions(_dispositions(classified, result_by_class))
        else:
            # the limit round gets no repair write, so its findings end the run
            # classified but undispositioned
            state.record_dispositions(_dispositions(classified, {}))

    return state.finalize(
        final_status=FINAL_BLOCKED_AFTER_REVIEW_LIMIT,
        needs_user_ruling=False,
        unresolved_blocking_findings=state.last_blocking(),
    )


SCAN_ROLE_PRE_ACCEPTANCE = "pre_acceptance_evidence_closure"
SCAN_ROLE_POST_ACCEPTANCE_TAIL = "post_acceptance_tail"

# Sentinel returned by the tail phase when its evidence diff pulled away the
# basis of the pass: acceptance must be re-judged by another review round.
_REREVIEW_REQUIRED = object()


def _tail_scan_phase(state, scanner, pass_round_supersedes):
    """Close the delivery after an accepted pass round. Passed requires all of:
    the pass round itself (no blocking findings), a non-invalidated scan result
    for the current `## Atomic Decisions` whose status is completed or
    skipped_no_active, and no pending scan result."""
    if scanner.fresh_completed_scan_state() is not None:
        # the closure scan already covers the current `## Atomic Decisions`:
        # reuse it, never pay a second scan for the same content
        return state.finalize(final_status=FINAL_PASSED, needs_user_ruling=False)
    scan_result, gate = scanner.run(SCAN_ROLE_POST_ACCEPTANCE_TAIL)
    if gate["pending_scan_result"] is not None:
        return state.finalize(
            final_status=FINAL_NEEDS_USER_RULING,
            needs_user_ruling=True,
            pending_scan_result=gate["pending_scan_result"],
        )
    if gate["stop_reason"] is not None:
        return state.finalize(
            final_status=FINAL_FAILED,
            needs_user_ruling=False,
            errors=[{"stage": "scan", "kind": gate["stop_reason"], "detail": scan_result}],
        )
    if scan_result["status"] == "completed":
        diff = tail_scan_evidence_diff(
            pass_round_supersedes, scan_result.get("written_supersedes")
        )
        state.scans[-1]["tail_evidence_diff"] = diff
        if diff == TAIL_EVIDENCE_REMOVED_OR_CHANGED:
            return _REREVIEW_REQUIRED
    return state.finalize(final_status=FINAL_PASSED, needs_user_ruling=False)


class _Scanner:
    """Runs supersession scans for one revise execution: drives the accepted-
    rewrite write-then-immediate-rescan loop, records every scan with its role
    and `## Atomic Decisions` fingerprint, and answers whether a fresh completed
    scan result exists for the current content."""

    def __init__(self, *, state, draft_adr_path, scan_fn, write_fn, accept_rewrite_fn, atomic_decisions_fn):
        self.state = state
        self.draft_adr_path = draft_adr_path
        self.scan_fn = scan_fn
        self.write_fn = write_fn
        self.accept_rewrite_fn = accept_rewrite_fn
        self.atomic_decisions_fn = atomic_decisions_fn

    def current_fingerprint(self):
        return atomic_decisions_fingerprint(self.atomic_decisions_fn(self.draft_adr_path))

    def fresh_completed_scan_state(self):
        last = self.state.last_scan
        if last is None:
            return None
        if (
            last["fingerprint"] is None
            # without a readable `## Atomic Decisions` there is no freshness
            # key, so a scan result is never treated as reusable
            or last["result"]["status"] != "completed"
            or last["fingerprint"] != self.current_fingerprint()
        ):
            return None
        return {"written_supersedes": list(last["result"].get("written_supersedes") or [])}

    def run(self, role):
        pending_rewrite_write = None
        while True:
            scan_result = self.scan_fn(_scan_request(self.draft_adr_path))
            self.state.record_scan(role, scan_result, self.current_fingerprint())
            if pending_rewrite_write is not None:
                self.state.scan_rewrite_loops.append(
                    build_scan_rewrite_loop_report(
                        write_result=pending_rewrite_write,
                        rerun_scan_status=scan_result["status"],
                        rerun_scan_result=scan_result,
                        scanner_output_structural_validation=scan_result.get(
                            "scanner_output_structural_validation", False
                        ),
                        main_agent_scan_review=scan_result.get("main_agent_scan_review", False),
                        written_supersedes=scan_result.get("written_supersedes"),
                    )
                )
                pending_rewrite_write = None
            if (
                scan_result["status"] == "awaiting_rewrite"
                and self.accept_rewrite_fn is not None
                and self.accept_rewrite_fn(scan_result)
            ):
                # accepted rewrite: apply it with `write`, then immediately
                # rescan — quality review may not run in between
                pending_rewrite_write = self.write_fn(
                    _rewrite_request(self.draft_adr_path, scan_result)
                )
                continue
            gate = build_scan_rewrite_gate_state(
                scan_status=scan_result["status"],
                scan_result=scan_result,
                scanner_output_structural_validation=scan_result.get(
                    "scanner_output_structural_validation", False
                ),
                main_agent_scan_review=scan_result.get("main_agent_scan_review", False),
                written_supersedes=scan_result.get("written_supersedes"),
            )
            return scan_result, gate


class _State:
    def __init__(self, *, draft_adr_path, run_dir, scan_rewrite_loops=None):
        self.draft_adr_path = draft_adr_path
        self.run_dir = run_dir
        self.rounds = []
        self.degradation_notes = []
        self.evidence_status = "clean"
        self.scan_rewrite_loops = list(scan_rewrite_loops or [])
        self.scans = []
        self.last_scan = None
        self.scan_invalidated = False

    def record_round(self, round_num, review):
        self.rounds.append({
            "round": round_num,
            "review_status": review["review_status"],
            "blocking": review["blocking"],
            "non_blocking": review.get("non_blocking", []),
            "support_data_status": review.get("support_data_status"),
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
        if review.get("support_data_status") in {"missing", "degraded"}:
            self.evidence_status = "degraded_reviewer_evidence"

    def record_dispositions(self, dispositions):
        self.rounds[-1]["blocking_finding_dispositions"] = dispositions

    def record_scan(self, role, scan_result, fingerprint):
        if self.last_scan is not None and self.last_scan["fingerprint"] != fingerprint:
            # `## Atomic Decisions` changed after the previous scan: that result
            # is invalid and this scan replaces it
            self.scan_invalidated = True
        self.scans.append({
            "role": role,
            "scan_status": scan_result["status"],
            "scanner_output_structural_validation": scan_result.get(
                "scanner_output_structural_validation", False
            ),
            "main_agent_scan_review": scan_result.get("main_agent_scan_review", False),
            "atomic_decisions_fingerprint": fingerprint,
        })
        self.last_scan = {"result": scan_result, "fingerprint": fingerprint}

    def last_blocking(self):
        return self.rounds[-1]["blocking"]

    def finalize(
        self,
        *,
        final_status,
        needs_user_ruling,
        ruling_request=None,
        pending_scan_result=None,
        unresolved_blocking_findings=None,
        errors=None,
    ):
        last_result = self.last_scan["result"] if self.last_scan is not None else {}
        scan_status = last_result.get("status", "not_run")
        report = {
            "operation": OPERATION,
            "final_status": final_status,
            "draft_adr_path": self.draft_adr_path,
            "structured_report_path": None,
            "needs_user_ruling": needs_user_ruling,
            "ruling_request": ruling_request,
            "quality_review_rounds": self.rounds,
            "final_review_state": self.rounds[-1]["review_status"],
            "unresolved_blocking_findings": list(unresolved_blocking_findings or []),
            "refused_findings": [],
            "scan_status": scan_status,
            "final_scan_status": scan_status,
            "scan_rewrite_request_status": scan_status,
            "scan_rewrite_loops": list(self.scan_rewrite_loops),
            "scan_invalidated_by_atomic_decisions_change": self.scan_invalidated,
            "pending_scan_result": pending_scan_result,
            "scanner_output_structural_validation": last_result.get(
                "scanner_output_structural_validation", False
            ),
            "main_agent_scan_review": last_result.get("main_agent_scan_review", False),
            "scans": list(self.scans),
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
    # scan-evidence finding points at (those close through the scan)
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


def _scan_request(draft_adr_path):
    return {"draft_adr_path": draft_adr_path}


def _rewrite_request(draft_adr_path, scan_result):
    # a scan-rewrite write is not a repair write: it applies an accepted rewrite
    # request so the draft fully replaces the old decision before the rescan
    return {
        "mode": "modify",
        "origin": "scan_rewrite",
        "target_adr_path": draft_adr_path,
        "rewrite_required": scan_result.get("rewrite_required", []),
    }


_SUPERSEDES_ENTRY_RE = re.compile(r"(?ms)^\s*- adr:\s*(?P<adr>.+?)\n(?P<body>.*?)(?=^\s*- adr:|\Z)")


def _read_draft_supersedes(draft_adr_path):
    """Default pass-round baseline reader: the draft frontmatter's `supersedes`
    entries in the scan-result entry shape, [] when unreadable or absent. Only
    the frontmatter block is searched — body prose can never masquerade as
    supersedes evidence."""
    try:
        text = Path(draft_adr_path).read_text(encoding="utf-8")
    except OSError:
        return []
    frontmatter = re.match(r"(?s)\A---\n(?P<fm>.*?)\n---", text)
    if frontmatter is None:
        return []
    match = re.search(
        r"(?ms)^supersedes:\n(?P<block>.*?)(?=^[A-Za-z_][A-Za-z0-9_]*:|\Z)",
        frontmatter.group("fm"),
    )
    if match is None:
        return []
    entries = []
    for entry in _SUPERSEDES_ENTRY_RE.finditer(match.group("block")):
        pairs = []
        for line in entry.group("body").splitlines():
            stripped = line.strip()
            if stripped.startswith("- {"):
                pairs.append(parse_inline_pair(stripped))
        entries.append({
            "candidate": {"adr": entry.group("adr").strip()},
            "atomic_decisions": pairs,
        })
    return entries


def _read_atomic_decisions(draft_adr_path):
    """Default `## Atomic Decisions` reader for scan freshness: the section text
    from the draft file, or None when the file or section is unreadable."""
    try:
        text = Path(draft_adr_path).read_text(encoding="utf-8")
    except OSError:
        return None
    lines = []
    in_section = False
    for line in text.splitlines():
        if line.strip() == "## Atomic Decisions":
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if in_section:
            lines.append(line)
    if not in_section:
        return None
    return "\n".join(lines)


def _direct_output(report):
    return {
        "draft_adr_path": report["draft_adr_path"],
        "structured_report_path": report["structured_report_path"],
        "final_status": report["final_status"],
        "needs_user_ruling": report["needs_user_ruling"],
    }
