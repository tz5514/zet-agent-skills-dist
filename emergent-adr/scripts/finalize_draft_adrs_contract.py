"""Mechanical finalize-draft-adrs orchestration contract.

`finalize-draft-adrs` is the draft ADR finalization orchestrator: it accepts one
or more existing draft ADR paths plus the caller's declared disposition-scope
premise, runs entry ADR redundancy checking once per draft, applies authorized
auto-disposition, then continues eligible drafts through scan-free `revise` and
same-bounded-context exclusive finalization attempts. Sub-operations and the
parallel execution point are injected as callables; this module does not spawn
threads.

Parallel zone one delivers every draft's entry redundancy check and its
disposition (including authorized `write` / delete) in one batch through the
injected parallel map. Quality revise and scan-rewrite `write` also run as
parallel batches. Finalization attempts are scheduled in stable input order:
each wave takes the earliest remaining draft per bounded context so
same-context attempts never share a batch, while different contexts may.

A finalization attempt holds exclusivity only across a fresh supersession scan
and — when that scan leaves no non-promotion work — the immediate promote.
Leaving the exclusive zone permanently invalidates that scan's promotion
authority; the next entry always rescans. Accepted scan rewrites run outside
exclusivity via `write`, then re-enter for a fresh scan before any further
quality revise — rewrite must never be followed directly by quality review.
Re-entry is bounded by rewrite-acceptance (unaccepted → unresolved) and the
shared review-round budget, not by a separate attempt cap. Promotion semantics
stay with `promote-draft-to-active`; this layer only decides when to call it.

Shared quality-review round budget (one draft, one finalize run): every
scan-free `revise` call continues from `rounds_already_consumed` and reports
`rounds_consumed`; this layer advances the cumulative total and never resets it
on scan-evidence hand-back, supersession scan, leaving exclusivity, post-rewrite
re-entry, or a later finalization attempt. Exhaustion stops that draft as
unresolved in the final result — there is no path that re-calls `revise` to mint
a fresh quota. The numeric round cap stays with `revise` (`MAX_REVIEW_ROUNDS`);
finalize only accounts shared use. ADR polish does not change runtime code, so
extra revision rounds have declining marginal benefit: one shared budget keeps
acceptable ADR quality and acceptable user-perceived speed in bounded balance.

Best-effort isolation is per draft: when one draft cannot finish automatically,
this operation stops only that draft and releases any same-context exclusivity
slot it held; later drafts in the same context and in other contexts keep
running. That choice accepts a low-probability risk that a later draft's scan
may not see a still-unresolved peer's conflicts — continuing the batch is
intentional, not a defect.

Unresolved content is never silently discarded and never rolled back. The
invariant is temporal: an unresolved draft stays in `draft/` (not deleted);
once judged unresolved, this operation applies no further disposition to it;
writes already completed before that judgment — entry redundancy edits to
`## Atomic Decisions`, revise writer repair, and scan rewrites — remain as-is.
Two unresolved appearances both appear in the batch summary as `unresolved`
with `needs_user_ruling` and an end-to-end report path: stopped-at-entry
(file bit-identical) and mid-run (file already carries lawful edits). Raw
judgment or failure evidence lives only in the per-draft end-to-end report,
which distinguishes the appearance via entry disposition, revise/write/scan
history, and ruling_request — the batch summary does not carry those details.

Exclusivity covers one single finalize-draft-adrs call only. Callers must merge
same-bounded-context drafts that may run together into that one call; if they
split into separate calls, a later call may start only after the earlier one
finishes. This layer creates no cross-call persistent lock and no global lock;
overlapping independent calls on the same context are outside the exclusivity
guarantee.

Input validation failures (empty list, duplicate identity/path, any path not
under `docs/adr/draft/`) return a structured operation failure without writing
a batch summary or calling lower operations. Auto delete/modify require both
semantic authorization (named atomic decisions still present in the draft) and
recoverable authorization (caller premise is True); either missing leaves the
draft unresolved without skipping disposition into quality review.

The direct envelope's batch `final_status` is order-independent: any unresolved
draft makes it `unresolved`; a uniform batch keeps that shared per-draft
terminal; a fully completed mix of promoted and deleted drafts is `completed`.
Exact per-draft terminals remain authoritative in the batch summary.
"""

import json
import posixpath
import re
from pathlib import Path
from typing import Any, TypedDict

from adr_id import adr_id_from_filename
from context_derivation import derive_context_root
from live_atomic_decision_corpus import _atomic_decisions
from revise_contract import (
    FINAL_BLOCKED_AFTER_REVIEW_LIMIT,
    FINAL_FAILED,
    FINAL_NEEDS_SCAN_EVIDENCE,
    FINAL_NEEDS_USER_RULING,
    FINAL_PASSED,
    FROZEN_GLOSSARY_QUALITY_REVIEW,
    MAX_REVIEW_ROUNDS,
)
from scan_cycle_contract import (
    BUDGET_EXHAUSTED,
    CLOSE_REREVIEW_REQUIRED,
    STEP_FAILED,
    STEP_PENDING,
    STEP_REWRITE_REQUIRED,
    ScanCycle,
    read_draft_supersedes,
    resolve_owed_rereview,
)


OPERATION = "finalize-draft-adrs"
BATCH_SUMMARY_FILENAME = "finalize_draft_adrs_batch_summary.json"
END_TO_END_REPORT_FILENAME = "finalize_draft_adrs_end_to_end_report.json"
SCAN_RESULT_FILENAME_PREFIX = "finalize_scan_result"
PRE_DISPOSITION_BACKUP_FILENAME = "pre_disposition_backup.md"

FINAL_PROMOTED = "promoted"
FINAL_DELETED = "deleted"
FINAL_UNRESOLVED = "unresolved"
FINAL_COMPLETED = "completed"

SCAN_ROLE_FINALIZATION_ATTEMPT = "finalization_attempt"
PROMOTION_AUTHORITY_USED = "used_for_promotion"
PROMOTION_AUTHORITY_INVALIDATED = "invalidated_on_exit"

ENTRY_AFTER_QUALITY_PASS = "after_quality_pass"
ENTRY_NEEDS_SCAN_EVIDENCE = "needs_scan_evidence"
ENTRY_AFTER_SCAN_REWRITE = "after_scan_rewrite"

PHASE_READY_FOR_ATTEMPT = "ready_for_attempt"
PHASE_NEED_REWRITE = "need_rewrite"
PHASE_NEED_REVISE = "need_revise"

OUTCOME_PROMOTED = "promoted"
OUTCOME_UNRESOLVED = "unresolved"
OUTCOME_NEED_REWRITE = "need_rewrite"
OUTCOME_NEED_REVISE = "need_revise"

DISPOSITION_CONTINUE_WITHOUT_CHANGE = "continue_without_change"
DISPOSITION_DELETED = "deleted"
DISPOSITION_MODIFIED_THEN_CONTINUE = "modified_then_continue"
DISPOSITION_WITHHELD = "disposition_withheld"
DISPOSITION_UNRESOLVED_NO_CHANGE = "unresolved_no_change"
DISPOSITION_CHECK_FAILED = "check_failed"
DISPOSITION_WRITE_FAILED = "disposition_write_failed"

ADR_FULLY_RETAINED = "adr_fully_retained"
ADR_FULLY_REDUNDANT = "adr_fully_redundant"
ADR_PARTIALLY_REDUNDANT = "adr_partially_redundant"
ADR_UNRESOLVED = "adr_unresolved"

ATOMIC_FULLY_REDUNDANT = "atomic_decision_fully_redundant"
ATOMIC_PARTIALLY_REDUNDANT = "atomic_decision_partially_redundant"

ACTION_DELETE_DRAFT = "delete_draft"
ACTION_MODIFY_ATOMIC_DECISIONS = "modify_atomic_decisions"

_ADR_PATH_LIFECYCLE_RE = re.compile(
    r"^(?:.+/)?docs/adr/(?P<lifecycle>draft|active|archived)/.+$"
)
_REVISE_ENTER_EXCLUSIVE = {FINAL_PASSED, FINAL_NEEDS_SCAN_EVIDENCE}


class DraftFinalizationState(TypedDict, total=False):
    """Internal state carried between parallel zones and exclusive attempts."""

    draft_adr_path: str
    draft_run: Path
    disposed: dict[str, Any]
    revise_calls: list[dict[str, Any]]
    review_rounds_consumed_total: int
    write_results: list[dict[str, Any]]
    scans: list[dict[str, Any]]
    scan_state: dict[str, Any] | None
    pending_rewrite_scan_result: dict[str, Any] | None
    pending_rewrite_request: dict[str, Any] | None
    attempt_count: int
    phase: str
    entry_mode: str | None
    pass_round_supersedes: list[dict[str, Any]]
    terminal_report: dict[str, Any] | None
    promotion_report_path: str | None
    scan_rewrite_requests: list[dict[str, Any]]


def run_finalize_draft_adrs(
    *,
    draft_adr_paths,
    disposition_scope_git_recoverable_and_isolated,
    check_adr_redundancy_fn,
    revise_fn,
    write_fn,
    scan_fn,
    promote_fn,
    parallel_map_fn,
    run_dir,
    accept_rewrite_fn=None,
):
    """Single public entry point for draft ADR finalization orchestration.

    `disposition_scope_git_recoverable_and_isolated` is the caller's declared
    premise; this layer requires a bool or None (undeclared) and does not
    reverse-verify Git state. `parallel_map_fn(items, worker)` is the injected
    parallel execution point: the orchestrator groups work into batches and
    delivers each batch through it. Exclusive finalization attempts are
    scheduled so each batch holds at most one draft per bounded context;
    scan→promote stays contiguous inside the worker. That exclusivity covers
    one single finalize-draft-adrs call only — this layer creates no cross-call
    persistent lock and no global lock. `accept_rewrite_fn` is the caller's
    per-request rewrite acceptance judgment; omitting it leaves
    awaiting-rewrite scans pending and unresolved.
    """
    if not (
        disposition_scope_git_recoverable_and_isolated is None
        or isinstance(disposition_scope_git_recoverable_and_isolated, bool)
    ):
        raise TypeError(
            "disposition_scope_git_recoverable_and_isolated must be a bool "
            "premise or None when undeclared"
        )

    validation_error = _validate_draft_inputs(draft_adr_paths)
    if validation_error is not None:
        return {
            "ok": False,
            "operation": OPERATION,
            "failure_class": "invalid_input",
            "error": validation_error,
        }

    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    recoverable_authorized = disposition_scope_git_recoverable_and_isolated is True

    reports_by_path, eligible_for_quality = _run_entry_redundancy_zone(
        draft_adr_paths=draft_adr_paths,
        recoverable_authorized=recoverable_authorized,
        check_adr_redundancy_fn=check_adr_redundancy_fn,
        write_fn=write_fn,
        parallel_map_fn=parallel_map_fn,
        run_dir=run_dir,
    )
    reports_by_path.update(
        _run_quality_and_exclusive_finalization(
            eligible_for_quality=eligible_for_quality,
            revise_fn=revise_fn,
            write_fn=write_fn,
            scan_fn=scan_fn,
            promote_fn=promote_fn,
            parallel_map_fn=parallel_map_fn,
            accept_rewrite_fn=accept_rewrite_fn,
        )
    )
    draft_reports = [reports_by_path[path] for path in draft_adr_paths]
    return _finalize_batch(run_dir=run_dir, draft_reports=draft_reports)


def _run_entry_redundancy_zone(
    *,
    draft_adr_paths,
    recoverable_authorized,
    check_adr_redundancy_fn,
    write_fn,
    parallel_map_fn,
    run_dir,
):
    """Parallel zone one: entry redundancy check + disposition per draft."""
    draft_runs = {
        path: run_dir / _draft_run_slug(path) for path in draft_adr_paths
    }
    for draft_run in draft_runs.values():
        draft_run.mkdir(parents=True, exist_ok=True)

    entry_items = [
        {"phase": "entry_redundancy", "draft_adr_path": path}
        for path in draft_adr_paths
    ]
    entry_results = parallel_map_fn(
        entry_items,
        lambda item: _entry_redundancy_and_disposition_worker(
            item,
            draft_run=draft_runs[item["draft_adr_path"]],
            recoverable_authorized=recoverable_authorized,
            check_adr_redundancy_fn=check_adr_redundancy_fn,
            write_fn=write_fn,
        ),
    )

    reports_by_path = {}
    eligible_for_quality: list[DraftFinalizationState] = []
    for item, result in zip(entry_items, entry_results):
        path = item["draft_adr_path"]
        draft_run = draft_runs[path]
        disposed = result["disposed"]
        if disposed["terminal"] is not None:
            reports_by_path[path] = _write_end_to_end_report(
                draft_run=draft_run,
                draft_adr_path=path,
                entry_redundancy=disposed["entry_redundancy"],
                revise_calls=[],
                review_rounds_consumed_total=0,
                scans=[],
                promotion_report_path=None,
                write_results=disposed["write_results"],
                final_status=disposed["terminal"],
                needs_user_ruling=disposed["needs_user_ruling"],
                ruling_request=disposed["ruling_request"],
            )
        else:
            eligible_for_quality.append({
                "draft_adr_path": path,
                "draft_run": draft_run,
                "disposed": disposed,
            })
    return reports_by_path, eligible_for_quality


def _entry_redundancy_and_disposition_worker(
    item,
    *,
    draft_run,
    recoverable_authorized,
    check_adr_redundancy_fn,
    write_fn,
):
    # Check and disposition stay in one worker so zone-one parallel work
    # includes authorized write/delete, not only the redundancy call.
    redundancy = check_adr_redundancy_fn({"adr_path": item["draft_adr_path"]})
    disposed = _apply_entry_redundancy_disposition(
        draft_adr_path=item["draft_adr_path"],
        redundancy=redundancy,
        recoverable_authorized=recoverable_authorized,
        write_fn=write_fn,
        draft_run=draft_run,
    )
    return {"disposed": disposed}


def _run_quality_and_exclusive_finalization(
    *,
    eligible_for_quality,
    revise_fn,
    write_fn,
    scan_fn,
    promote_fn,
    parallel_map_fn,
    accept_rewrite_fn,
):
    if not eligible_for_quality:
        return {}

    reports_by_path = {}
    ready_for_attempt: list[DraftFinalizationState] = []
    rewrite_q: list[DraftFinalizationState] = []
    revise_q: list[DraftFinalizationState] = []

    for state in _run_quality_revise_batch(
        drafts=eligible_for_quality,
        revise_fn=revise_fn,
        write_fn=write_fn,
        parallel_map_fn=parallel_map_fn,
    ):
        if state.get("terminal_report") is not None:
            reports_by_path[state["draft_adr_path"]] = state["terminal_report"]
        else:
            ready_for_attempt.append(state)

    while ready_for_attempt or rewrite_q or revise_q:
        if rewrite_q:
            for state in _run_scan_rewrite_batch(
                drafts=rewrite_q,
                write_fn=write_fn,
                parallel_map_fn=parallel_map_fn,
            ):
                if state.get("terminal_report") is not None:
                    reports_by_path[state["draft_adr_path"]] = state[
                        "terminal_report"
                    ]
                else:
                    ready_for_attempt.append(state)
            rewrite_q = []
        if revise_q:
            for state in _run_quality_revise_batch(
                drafts=revise_q,
                revise_fn=revise_fn,
                write_fn=write_fn,
                parallel_map_fn=parallel_map_fn,
            ):
                if state.get("terminal_report") is not None:
                    reports_by_path[state["draft_adr_path"]] = state["terminal_report"]
                else:
                    ready_for_attempt.append(state)
            revise_q = []
        if not ready_for_attempt:
            continue

        wave_items, wave_drafts, ready_for_attempt = _next_exclusivity_wave(
            ready_for_attempt
        )
        draft_by_path = {
            item["draft_adr_path"]: item for item in wave_drafts
        }
        attempt_results = parallel_map_fn(
            wave_items,
            lambda mapped: _run_finalization_attempt(
                draft=draft_by_path[mapped["draft_adr_path"]],
                scan_fn=scan_fn,
                promote_fn=promote_fn,
                accept_rewrite_fn=accept_rewrite_fn,
            ),
        )
        for item, attempt in zip(wave_drafts, attempt_results):
            merged = _merge_attempt_into_draft(item, attempt)
            outcome = attempt["outcome"]
            if outcome == OUTCOME_PROMOTED:
                reports_by_path[item["draft_adr_path"]] = _write_end_to_end_report(
                    **_report_kwargs_from_draft(merged, FINAL_PROMOTED)
                )
            elif outcome == OUTCOME_UNRESOLVED:
                reports_by_path[item["draft_adr_path"]] = _write_end_to_end_report(
                    **_report_kwargs_from_draft(
                        merged,
                        FINAL_UNRESOLVED,
                        needs_user_ruling=True,
                        ruling_request=attempt.get("ruling_request"),
                    )
                )
            elif outcome == OUTCOME_NEED_REWRITE:
                rewrite_q.append(merged)
            else:
                revise_q.append(merged)

    return reports_by_path


def _run_quality_revise_batch(
    *,
    drafts,
    revise_fn,
    write_fn,
    parallel_map_fn,
) -> list[DraftFinalizationState]:
    """Parallel quality-revise batch; classify each draft into exclusive entry or terminal."""
    draft_by_path = {item["draft_adr_path"]: item for item in drafts}
    revise_items = [
        {
            "phase": "quality_revise",
            "draft_adr_path": item["draft_adr_path"],
            "rounds_already_consumed": item.get("review_rounds_consumed_total", 0),
            "scan_state": item.get("scan_state"),
        }
        for item in drafts
    ]
    revise_results = parallel_map_fn(
        revise_items,
        lambda mapped: revise_fn(
            inputs={
                "draft_adr_path": mapped["draft_adr_path"],
                "quality_review_mode": FROZEN_GLOSSARY_QUALITY_REVIEW,
                "rounds_already_consumed": mapped["rounds_already_consumed"],
                "scan_state": mapped["scan_state"],
            },
            write_fn=write_fn,
            quality_review_fn=None,
            run_dir=draft_by_path[mapped["draft_adr_path"]]["draft_run"]
            / f"revise_{mapped['rounds_already_consumed']}",
        ),
    )
    next_states = []
    for item, revise_result in zip(drafts, revise_results):
        next_states.append(_apply_revise_result(item, revise_result))
    return next_states


def _apply_revise_result(
    item: DraftFinalizationState,
    revise_result: dict[str, Any],
) -> DraftFinalizationState:
    revise_report = revise_result["report"]
    status = revise_report["final_status"]
    rounds_consumed = int(revise_report.get("rounds_consumed") or 0)
    prior_rounds = int(item.get("review_rounds_consumed_total") or 0)
    revise_calls = list(item.get("revise_calls") or [])
    revise_calls.append({
        "order": len(revise_calls) + 1,
        "quality_review_mode": FROZEN_GLOSSARY_QUALITY_REVIEW,
        "final_status": status,
        "structured_report_path": revise_report.get("structured_report_path"),
        "rounds_consumed": rounds_consumed,
    })
    write_results = list(
        item.get("write_results")
        if item.get("write_results") is not None
        else item.get("disposed", {}).get("write_results")
        or []
    )
    scans = list(item.get("scans") or [])
    merged = {
        **item,
        "revise_calls": revise_calls,
        "review_rounds_consumed_total": prior_rounds + rounds_consumed,
        "write_results": write_results,
        "scans": scans,
        "scan_state": None,
        "pending_rewrite_scan_result": None,
        "attempt_count": int(item.get("attempt_count") or 0),
    }
    if status in _REVISE_ENTER_EXCLUSIVE:
        entry_mode = (
            ENTRY_AFTER_QUALITY_PASS
            if status == FINAL_PASSED
            else ENTRY_NEEDS_SCAN_EVIDENCE
        )
        return {
            **merged,
            "phase": PHASE_READY_FOR_ATTEMPT,
            "entry_mode": entry_mode,
            "pass_round_supersedes": (
                list(read_draft_supersedes(item["draft_adr_path"]))
                if status == FINAL_PASSED
                else item.get("pass_round_supersedes")
            ),
            "terminal_report": None,
        }

    ruling_request = revise_report.get("ruling_request")
    if ruling_request is None:
        ruling_request = {
            "origin": "quality_revise",
            "final_status": status,
            "errors": list(revise_report.get("errors") or []),
        }
    return {
        **merged,
        "terminal_report": _write_end_to_end_report(
            **_report_kwargs_from_draft(
                merged,
                FINAL_UNRESOLVED,
                needs_user_ruling=bool(
                    revise_report.get("needs_user_ruling")
                    or status in (
                        FINAL_NEEDS_USER_RULING,
                        FINAL_BLOCKED_AFTER_REVIEW_LIMIT,
                        FINAL_FAILED,
                    )
                ),
                ruling_request=ruling_request,
            )
        ),
    }


def _run_scan_rewrite_batch(
    *, drafts, write_fn, parallel_map_fn
) -> list[DraftFinalizationState]:
    """Apply accepted scan rewrites outside exclusivity, then re-queue for a fresh scan."""
    rewrite_items = [
        {
            "phase": "scan_rewrite",
            "draft_adr_path": item["draft_adr_path"],
            "write_request": dict(item["pending_rewrite_request"]),
        }
        for item in drafts
    ]
    write_results = parallel_map_fn(
        rewrite_items,
        lambda mapped: write_fn(mapped["write_request"]),
    )
    next_states = []
    for item, write_result, mapped in zip(drafts, write_results, rewrite_items):
        write_results_acc = list(item.get("write_results") or [])
        write_results_acc.append(write_result)
        scan_rewrite_requests = list(item.get("scan_rewrite_requests") or []) + [
            mapped
        ]
        if write_result.get("status") != "written":
            # Failed rewrite must not clear pending or re-enter exclusivity for
            # a fresh scan — mirror entry-redundancy write-failure disposition.
            failed = {
                **item,
                "write_results": write_results_acc,
                "scan_rewrite_requests": scan_rewrite_requests,
            }
            next_states.append({
                **failed,
                "terminal_report": _write_end_to_end_report(
                    **_report_kwargs_from_draft(
                        failed,
                        FINAL_UNRESOLVED,
                        needs_user_ruling=True,
                        ruling_request={
                            "origin": "scan_rewrite_write_failed",
                            "write_result": write_result,
                        },
                    )
                ),
            })
            continue
        # After a scan rewrite, re-enter exclusivity for a fresh scan before any
        # quality revise — rewrite must not be followed by review.
        next_states.append({
            **item,
            "write_results": write_results_acc,
            "phase": PHASE_READY_FOR_ATTEMPT,
            "entry_mode": ENTRY_AFTER_SCAN_REWRITE,
            "pending_rewrite_scan_result": None,
            "pending_rewrite_request": None,
            "scan_state": None,
            "scan_rewrite_requests": scan_rewrite_requests,
            "terminal_report": None,
        })
    return next_states


def _merge_attempt_into_draft(
    item: DraftFinalizationState,
    attempt: dict[str, Any],
) -> DraftFinalizationState:
    scans = list(item.get("scans") or []) + list(attempt.get("scans") or [])
    write_results = list(item.get("write_results") or [])
    merged = {
        **item,
        "scans": scans,
        "write_results": write_results,
        "promotion_report_path": attempt.get("promotion_report_path"),
        "pending_rewrite_scan_result": attempt.get("pending_rewrite_scan_result"),
        "pending_rewrite_request": attempt.get("pending_rewrite_request"),
        "scan_state": attempt.get("scan_state"),
        "attempt_count": int(item.get("attempt_count") or 0) + 1,
    }
    if attempt.get("outcome") == OUTCOME_NEED_REVISE:
        merged["phase"] = PHASE_NEED_REVISE
        merged["entry_mode"] = None
    elif attempt.get("outcome") == OUTCOME_NEED_REWRITE:
        merged["phase"] = PHASE_NEED_REWRITE
        merged["entry_mode"] = None
    return merged


def _report_kwargs_from_draft(
    draft: DraftFinalizationState,
    final_status,
    *,
    needs_user_ruling=False,
    ruling_request=None,
):
    return {
        "draft_run": draft["draft_run"],
        "draft_adr_path": draft["draft_adr_path"],
        "entry_redundancy": draft["disposed"]["entry_redundancy"],
        "revise_calls": list(draft.get("revise_calls") or []),
        "review_rounds_consumed_total": int(
            draft.get("review_rounds_consumed_total") or 0
        ),
        "scans": list(draft.get("scans") or []),
        "promotion_report_path": draft.get("promotion_report_path"),
        "write_results": list(
            draft.get("write_results")
            or draft["disposed"].get("write_results")
            or []
        ),
        "final_status": final_status,
        "needs_user_ruling": needs_user_ruling,
        "ruling_request": ruling_request,
    }


def _next_exclusivity_wave(
    remaining: list[DraftFinalizationState],
) -> tuple[
    list[dict[str, str]],
    list[DraftFinalizationState],
    list[DraftFinalizationState],
]:
    """Pick earliest remaining draft per context; defer same-context leftovers.

    Order is input order only — no importance or dependency ranking.
    """
    wave_items = []
    wave_drafts = []
    deferred = []
    used_contexts = set()
    for item in remaining:
        context_root = derive_context_root(item["draft_adr_path"])
        if context_root in used_contexts:
            deferred.append(item)
            continue
        used_contexts.add(context_root)
        wave_items.append({
            "phase": "finalization_attempt",
            "draft_adr_path": item["draft_adr_path"],
        })
        wave_drafts.append(item)
    return wave_items, wave_drafts, deferred


def _run_finalization_attempt(
    *,
    draft: DraftFinalizationState,
    scan_fn,
    promote_fn,
    accept_rewrite_fn,
):
    """Hold exclusivity across one fresh scan and optional immediate promote.

    Scan and promote run inside the same parallel-map worker so no other draft
    work can be interleaved between them at this orchestration layer. Any exit
    without promote permanently invalidates this scan's promotion authority.
    """
    draft_adr_path = draft["draft_adr_path"]
    draft_run = Path(draft["draft_run"])
    attempt_index = int(draft.get("attempt_count") or 0) + 1
    entry_mode = draft["entry_mode"]
    persisted_result_path = (
        draft_run / f"{SCAN_RESULT_FILENAME_PREFIX}_{attempt_index}.json"
    )
    cycle = ScanCycle(
        draft_adr_path=draft_adr_path,
        scan_fn=scan_fn,
        write_fn=None,
        accept_rewrite_fn=accept_rewrite_fn,
    )
    step = cycle.run_step(
        SCAN_ROLE_FINALIZATION_ATTEMPT,
        persisted_result_path=persisted_result_path,
    )
    scan_result = step["scan_result"]
    shared_record = step["scan_record"]
    scan_record = {
        "role": SCAN_ROLE_FINALIZATION_ATTEMPT,
        "status": shared_record["scan_status"],
        "persisted_result_path": str(persisted_result_path),
        "entry_mode": entry_mode,
        "promotion_authority": PROMOTION_AUTHORITY_INVALIDATED,
        "scanner_output_structural_validation": shared_record[
            "scanner_output_structural_validation"
        ],
        "main_agent_scan_review": shared_record["main_agent_scan_review"],
        "atomic_decisions_fingerprint": shared_record[
            "atomic_decisions_fingerprint"
        ],
    }

    if step["kind"] == STEP_REWRITE_REQUIRED:
        return {
            "outcome": OUTCOME_NEED_REWRITE,
            "scans": [scan_record],
            "pending_rewrite_scan_result": scan_result,
            "pending_rewrite_request": step["rewrite_request"],
            "promotion_report_path": None,
            "scan_state": None,
        }

    if step["kind"] == STEP_PENDING:
        origin = (
            "scan_awaiting_rewrite_unaccepted"
            if scan_result["status"] == "awaiting_rewrite"
            else "scan_pending"
        )
        return {
            "outcome": OUTCOME_UNRESOLVED,
            "scans": [scan_record],
            "promotion_report_path": None,
            "ruling_request": {
                "origin": origin,
                "pending_scan_result": step["gate"]["pending_scan_result"],
            },
        }

    if step["kind"] == STEP_FAILED:
        return {
            "outcome": OUTCOME_UNRESOLVED,
            "scans": [scan_record],
            "promotion_report_path": None,
            "ruling_request": {
                "origin": "scan_failed",
                "stop_reason": step["gate"]["stop_reason"],
                "scan_result": scan_result,
            },
        }

    # Completed / skipped_no_active: decide promote vs release for more work.
    if entry_mode == ENTRY_AFTER_QUALITY_PASS:
        close = cycle.close_step_after_acceptance_pass(
            step,
            draft.get("pass_round_supersedes") or [],
        )
        if "tail_evidence_diff" in shared_record:
            scan_record["tail_evidence_diff"] = shared_record["tail_evidence_diff"]
        if close["kind"] == CLOSE_REREVIEW_REQUIRED:
            rounds_consumed = int(draft.get("review_rounds_consumed_total") or 0)
            decision = resolve_owed_rereview(
                can_rereview=rounds_consumed < MAX_REVIEW_ROUNDS,
            )
            if decision["kind"] == BUDGET_EXHAUSTED:
                return {
                    "outcome": OUTCOME_UNRESOLVED,
                    "scans": [scan_record],
                    "promotion_report_path": None,
                    "ruling_request": {
                        "origin": "tail_evidence_rereview_budget_exhausted",
                        "errors": [decision["error"]],
                    },
                }
            return {
                "outcome": OUTCOME_NEED_REVISE,
                "scans": [scan_record],
                "promotion_report_path": None,
                "scan_state": cycle.scan_state_from_step(step),
            }
        promote_result = promote_fn({"draft_adr_path": draft_adr_path})
        scan_record["promotion_authority"] = PROMOTION_AUTHORITY_USED
        return {
            "outcome": OUTCOME_PROMOTED,
            "scans": [scan_record],
            "promotion_report_path": promote_result["structured_report_path"],
            "scan_state": None,
        }

    # Evidence closed after needs_scan_evidence or post-rewrite: release for
    # revise when still needed; never promote on a scan that only closed rewrite
    # / scan-evidence work.
    return {
        "outcome": OUTCOME_NEED_REVISE,
        "scans": [scan_record],
        "promotion_report_path": None,
        "scan_state": cycle.scan_state_from_step(step),
    }


def _validate_draft_inputs(draft_adr_paths):
    if not isinstance(draft_adr_paths, (list, tuple)):
        return "draft_adr_paths must be a non-empty list"
    if len(draft_adr_paths) == 0:
        return "draft_adr_paths must be a non-empty list"

    seen_paths = set()
    seen_ids = set()
    for path in draft_adr_paths:
        if not isinstance(path, str) or not path.strip():
            return "each draft_adr_path must be a non-empty string"
        if path in seen_paths:
            return f"duplicate draft_adr_path: {path}"
        seen_paths.add(path)

        if not _is_under_draft_lifecycle(path):
            return (
                "every draft_adr_path must lie under docs/adr/draft/; "
                f"rejected: {path}"
            )

        identity = adr_id_from_filename(Path(path).name)
        if identity in seen_ids:
            return f"duplicate draft identity: {identity}"
        seen_ids.add(identity)
    return None


def _is_under_draft_lifecycle(path):
    # Normpath so draft/../active cannot sneak past a raw substring check.
    normalized = posixpath.normpath(str(path).replace("\\", "/"))
    match = _ADR_PATH_LIFECYCLE_RE.match(normalized)
    return match is not None and match.group("lifecycle") == "draft"


def _apply_entry_redundancy_disposition(
    *,
    draft_adr_path,
    redundancy,
    recoverable_authorized,
    write_fn,
    draft_run,
):
    evaluation_report_path = redundancy.get("evaluation_report_path")
    write_results = []

    if redundancy.get("ok") is False:
        return {
            "terminal": FINAL_UNRESOLVED,
            "needs_user_ruling": True,
            "ruling_request": {
                "origin": "entry_redundancy_check_failure",
                "failure": {
                    "failure_class": redundancy.get("failure_class"),
                    "error": redundancy.get("error"),
                },
            },
            "write_results": write_results,
            "entry_redundancy": {
                "adr_redundancy_evaluation_result": None,
                "evaluation_report_path": evaluation_report_path,
                "disposition": DISPOSITION_CHECK_FAILED,
                "needs_user_ruling": True,
                "failure": {
                    "failure_class": redundancy.get("failure_class"),
                    "error": redundancy.get("error"),
                },
                "actions": [],
            },
        }

    adr_result = redundancy["adr_redundancy_evaluation_result"]
    decision_results = list(
        redundancy.get("atomic_decision_redundancy_evaluation_results") or []
    )
    base_entry = {
        "adr_redundancy_evaluation_result": adr_result,
        "evaluation_report_path": evaluation_report_path,
        "needs_user_ruling": bool(redundancy.get("needs_user_ruling")),
        "actions": [],
    }

    if adr_result == ADR_FULLY_RETAINED:
        return {
            "terminal": None,
            "needs_user_ruling": False,
            "ruling_request": None,
            "write_results": write_results,
            "entry_redundancy": {
                **base_entry,
                "disposition": DISPOSITION_CONTINUE_WITHOUT_CHANGE,
            },
        }

    if adr_result == ADR_UNRESOLVED:
        ruling_requests = list(redundancy.get("user_ruling_requests") or [])
        return {
            "terminal": FINAL_UNRESOLVED,
            "needs_user_ruling": True,
            "ruling_request": {
                "origin": "entry_redundancy_unresolved",
                "user_ruling_requests": ruling_requests,
            },
            "write_results": write_results,
            "entry_redundancy": {
                **base_entry,
                "disposition": DISPOSITION_UNRESOLVED_NO_CHANGE,
                "needs_user_ruling": True,
                "user_ruling_requests": ruling_requests,
            },
        }

    if adr_result not in (ADR_FULLY_REDUNDANT, ADR_PARTIALLY_REDUNDANT):
        # Closed ADR-level set is owned by check-adr-redundancy; an unexpected
        # value is treated as check failure evidence, never re-judged here.
        return {
            "terminal": FINAL_UNRESOLVED,
            "needs_user_ruling": True,
            "ruling_request": {
                "origin": "entry_redundancy_unexpected_result",
                "adr_redundancy_evaluation_result": adr_result,
            },
            "write_results": write_results,
            "entry_redundancy": {
                **base_entry,
                "disposition": DISPOSITION_CHECK_FAILED,
                "needs_user_ruling": True,
            },
        }

    semantic_authorized = _semantic_authorization_holds(
        draft_adr_path=draft_adr_path,
        decision_results=decision_results,
    )
    if not (semantic_authorized and recoverable_authorized):
        unexecuted = _planned_disposition(
            adr_result=adr_result,
            decision_results=decision_results,
        )
        return {
            "terminal": FINAL_UNRESOLVED,
            "needs_user_ruling": True,
            "ruling_request": {
                "origin": "entry_redundancy_disposition_unauthorized",
                "unexecuted_disposition": unexecuted,
                "authorization": {
                    "semantic": semantic_authorized,
                    "recoverable": recoverable_authorized,
                },
            },
            "write_results": write_results,
            "entry_redundancy": {
                **base_entry,
                "disposition": DISPOSITION_WITHHELD,
                "needs_user_ruling": True,
                "authorization": {
                    "semantic": semantic_authorized,
                    "recoverable": recoverable_authorized,
                },
                "unexecuted_disposition": unexecuted,
            },
        }

    if adr_result == ADR_FULLY_REDUNDANT:
        recovery_point = _backup_draft(draft_adr_path, draft_run)
        Path(draft_adr_path).unlink()
        action = {
            "evaluation_report_path": evaluation_report_path,
            "action": ACTION_DELETE_DRAFT,
            "recovery_point": recovery_point,
            "deleted_path": draft_adr_path,
        }
        return {
            "terminal": FINAL_DELETED,
            "needs_user_ruling": False,
            "ruling_request": None,
            "write_results": write_results,
            "entry_redundancy": {
                **base_entry,
                "disposition": DISPOSITION_DELETED,
                "actions": [action],
            },
        }

    planned = _planned_disposition(
        adr_result=adr_result,
        decision_results=decision_results,
    )
    recovery_point = _backup_draft(draft_adr_path, draft_run)
    write_request = {
        "mode": "modify",
        "target_adr_path": draft_adr_path,
        "purpose": "entry_redundancy_disposition",
        "remove_atomic_decision_ids": planned["remove_atomic_decision_ids"],
        "modify_atomic_decisions": planned["modify_atomic_decisions"],
        "evaluation_report_path": evaluation_report_path,
    }
    write_result = write_fn(write_request)
    write_results.append(write_result)
    action = {
        "evaluation_report_path": evaluation_report_path,
        "action": ACTION_MODIFY_ATOMIC_DECISIONS,
        "recovery_point": recovery_point,
        "remove_atomic_decision_ids": planned["remove_atomic_decision_ids"],
        "modify_atomic_decisions": planned["modify_atomic_decisions"],
    }
    if write_result.get("status") != "written":
        # Failed modify must not continue into quality review with redundant
        # content still eligible for promotion.
        return {
            "terminal": FINAL_UNRESOLVED,
            "needs_user_ruling": True,
            "ruling_request": {
                "origin": "entry_redundancy_disposition_write_failed",
                "write_result": write_result,
                "planned_disposition": planned,
            },
            "write_results": write_results,
            "entry_redundancy": {
                **base_entry,
                "disposition": DISPOSITION_WRITE_FAILED,
                "needs_user_ruling": True,
                "actions": [action],
                "write_result": write_result,
            },
        }
    return {
        "terminal": None,
        "needs_user_ruling": False,
        "ruling_request": None,
        "write_results": write_results,
        "entry_redundancy": {
            **base_entry,
            "disposition": DISPOSITION_MODIFIED_THEN_CONTINUE,
            "actions": [action],
        },
    }


def _semantic_authorization_holds(*, draft_adr_path, decision_results):
    path = Path(draft_adr_path)
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    present_ids = {item["atomic_decision_id"] for item in _atomic_decisions(text)}
    named_ids = {
        item["atomic_decision_id"]
        for item in decision_results
        if isinstance(item, dict) and item.get("atomic_decision_id")
    }
    if not named_ids:
        return False
    return named_ids <= present_ids


def _planned_disposition(*, adr_result, decision_results):
    if adr_result == ADR_FULLY_REDUNDANT:
        return {
            "kind": ACTION_DELETE_DRAFT,
            "remove_atomic_decision_ids": [
                item["atomic_decision_id"] for item in decision_results
            ],
            "modify_atomic_decisions": [],
        }
    remove_ids = [
        item["atomic_decision_id"]
        for item in decision_results
        if item.get("evaluation_result") == ATOMIC_FULLY_REDUNDANT
    ]
    modify = [
        {
            "atomic_decision_id": item["atomic_decision_id"],
            "redundant_portion": item["redundant_portion"],
            "retained_portion": item["retained_portion"],
        }
        for item in decision_results
        if item.get("evaluation_result") == ATOMIC_PARTIALLY_REDUNDANT
    ]
    return {
        "kind": ACTION_MODIFY_ATOMIC_DECISIONS,
        "remove_atomic_decision_ids": remove_ids,
        "modify_atomic_decisions": modify,
    }


def _backup_draft(draft_adr_path, draft_run):
    backup_path = Path(draft_run) / PRE_DISPOSITION_BACKUP_FILENAME
    backup_path.write_text(
        Path(draft_adr_path).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return str(backup_path)


def _finalize_batch(*, run_dir, draft_reports):
    drafts = [
        {
            "draft_adr_path": report["draft_adr_path"],
            "final_status": report["final_status"],
            "needs_user_ruling": report["needs_user_ruling"],
            "end_to_end_report_path": report["structured_report_path"],
        }
        for report in draft_reports
    ]
    needs_user_ruling = any(row["needs_user_ruling"] for row in drafts)
    terminal_set = {row["final_status"] for row in drafts}
    if FINAL_UNRESOLVED in terminal_set:
        final_status = FINAL_UNRESOLVED
    elif len(terminal_set) == 1:
        final_status = next(iter(terminal_set))
    else:
        # A promoted+deleted batch is fully complete, but has no honest single
        # per-draft terminal. Keep the envelope order-independent and leave the
        # exact terminals in the batch summary.
        final_status = FINAL_COMPLETED

    summary = {
        "operation": OPERATION,
        "structured_report_path": None,
        "drafts": drafts,
    }
    summary_path = run_dir / BATCH_SUMMARY_FILENAME
    summary["structured_report_path"] = str(summary_path)
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return {
        "ok": True,
        "direct_output": {
            "batch_summary_path": str(summary_path),
            "structured_report_path": str(summary_path),
            "final_status": final_status,
            "needs_user_ruling": needs_user_ruling,
        },
        "report": summary,
    }


def _write_end_to_end_report(
    *,
    draft_run,
    draft_adr_path,
    entry_redundancy,
    revise_calls,
    review_rounds_consumed_total,
    scans,
    promotion_report_path,
    write_results,
    final_status,
    needs_user_ruling,
    ruling_request,
):
    report = {
        "operation": OPERATION,
        "draft_adr_path": draft_adr_path,
        "structured_report_path": None,
        "entry_redundancy": entry_redundancy,
        "revise_calls": revise_calls,
        "review_rounds_consumed_total": review_rounds_consumed_total,
        "scans": scans,
        "promotion_report_path": promotion_report_path,
        "write_results": write_results,
        "final_status": final_status,
        "needs_user_ruling": needs_user_ruling,
        "ruling_request": ruling_request,
    }
    report_path = draft_run / END_TO_END_REPORT_FILENAME
    report["structured_report_path"] = str(report_path)
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return report


def _draft_run_slug(draft_adr_path):
    return Path(draft_adr_path).stem
