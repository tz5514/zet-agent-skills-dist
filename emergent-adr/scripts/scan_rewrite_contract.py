"""Scan-rewrite gate and tail-evidence pure helpers.

Single authority for the gate state, loop report shape, atomic-decisions
fingerprint, and tail-scan evidence diff. The shared scan-cycle mechanical
layer and its drivers reuse these helpers; they are not forked per caller.
"""

import hashlib

from supersession_pairs import expand_atomic_decision_pairs, supersession_pairs_are_valid


PENDING_SCAN_STATUSES = {"awaiting_rewrite", "awaiting_review"}
NO_CANDIDATE_SCAN_STATUSES = {"skipped_no_active"}
def atomic_decisions_fingerprint(atomic_decisions_text):
    """A scan result is only valid for the `## Atomic Decisions` content it was
    produced against; this content hash is the mechanical freshness key. None in,
    None out — an unreadable section never masquerades as a stable fingerprint."""
    if atomic_decisions_text is None:
        return None
    return hashlib.sha256(atomic_decisions_text.strip().encode("utf-8")).hexdigest()


TAIL_EVIDENCE_ADDITIONS_OR_UNCHANGED = "additions_or_unchanged"
TAIL_EVIDENCE_REMOVED_OR_CHANGED = "removed_or_changed"


def supersedes_triples(entries):
    """Flatten supersedes entries into `(candidate adr, ours, theirs)` triples —
    the comparison unit for the tail-scan evidence diff."""
    triples = set()
    for entry in entries or []:
        adr = (entry.get("candidate") or {}).get("adr")
        for pair in expand_atomic_decision_pairs(entry.get("atomic_decisions") or [], block_key="supersedes"):
            triples.add((adr, pair.get("ours"), pair.get("theirs")))
    return triples


def tail_scan_evidence_diff(pass_round_entries, post_scan_entries):
    """Judge the tail scan's written result against the `supersedes` evidence
    the passing review round saw. Additions never supported the already-made
    pass, so they need no re-review; removing or changing an entry pulls away
    the basis of the pass and forces one."""
    if supersedes_triples(pass_round_entries) <= supersedes_triples(post_scan_entries):
        return TAIL_EVIDENCE_ADDITIONS_OR_UNCHANGED
    return TAIL_EVIDENCE_REMOVED_OR_CHANGED


def supersedes_entries_are_valid(entries):
    if not entries:
        return False
    for entry in entries:
        candidate = entry.get("candidate")
        candidate_adr = candidate.get("adr") if isinstance(candidate, dict) else None
        if not isinstance(candidate_adr, str) or not candidate_adr.strip():
            return False
        pairs = entry.get("atomic_decisions")
        if not isinstance(pairs, list) or not pairs:
            return False
        if not supersession_pairs_are_valid(pairs, block_key="supersedes"):
            return False
    return True


def build_scan_rewrite_gate_state(
    *,
    scan_status,
    scan_result=None,
    write_origin="scan_rewrite",
    atomic_decisions_changed_after_scan=False,
    scanner_output_structural_validation=False,
    main_agent_scan_review=False,
    written_supersedes=None,
    scan_rewrite_loops=None,
    quality_review_rounds=None,
    unresolved_blocking_findings=None,
):
    written_supersedes = list(written_supersedes or [])
    scan_rewrite_loops = list(scan_rewrite_loops or [])
    quality_review_rounds = list(quality_review_rounds or [])
    unresolved_blocking_findings = list(unresolved_blocking_findings or [])
    pending_scan_result = None
    quality_review_allowed = False
    stop_reason = None

    if atomic_decisions_changed_after_scan:
        stop_reason = "fresh_scan_required"
    elif write_origin == "non_scan":
        quality_review_allowed = True
    elif scan_status in PENDING_SCAN_STATUSES:
        if isinstance(scan_result, dict) and scan_result.get("status") not in {None, scan_status}:
            stop_reason = "pending_scan_status_mismatch"
        else:
            pending_scan_result = dict(scan_result) if isinstance(scan_result, dict) else {"status": scan_status}
            stop_reason = "pending_scan_result"
    elif scan_status in NO_CANDIDATE_SCAN_STATUSES:
        quality_review_allowed = True
    elif scan_status == "completed":
        if not scanner_output_structural_validation or not main_agent_scan_review:
            stop_reason = "scan_result_needs_review"
        elif written_supersedes and not supersedes_entries_are_valid(written_supersedes):
            stop_reason = "invalid_supersedes_metadata"
        else:
            quality_review_allowed = True
    else:
        stop_reason = "scan_not_completed"

    durable_metadata_write_allowed = (
        write_origin == "scan_rewrite"
        and scan_status == "completed"
        and stop_reason is None
        and not atomic_decisions_changed_after_scan
        and scanner_output_structural_validation
        and main_agent_scan_review
        and bool(written_supersedes)
        and supersedes_entries_are_valid(written_supersedes)
    )
    return {
        "write_origin": write_origin,
        "final_scan_status": scan_status,
        "scan_invalidated_by_atomic_decisions_change": atomic_decisions_changed_after_scan,
        "pending_scan_result": pending_scan_result,
        "scanner_output_structural_validation": scanner_output_structural_validation,
        "main_agent_scan_review": main_agent_scan_review,
        "scan_rewrite_loops": scan_rewrite_loops,
        "quality_review_rounds": quality_review_rounds,
        "unresolved_blocking_findings": unresolved_blocking_findings,
        "durable_metadata_write_allowed": durable_metadata_write_allowed,
        "promotion_metadata_allowed": durable_metadata_write_allowed,
        "quality_review_required": quality_review_allowed,
        "quality_review_allowed": quality_review_allowed,
        "stop_reason": stop_reason,
    }


def build_scan_rewrite_loop_report(
    *,
    write_result,
    rerun_scan_status,
    rerun_scan_result=None,
    atomic_decisions_changed_after_scan=False,
    scanner_output_structural_validation=False,
    main_agent_scan_review=False,
    written_supersedes=None,
):
    gate_state = build_scan_rewrite_gate_state(
        scan_status=rerun_scan_status,
        scan_result=rerun_scan_result,
        atomic_decisions_changed_after_scan=atomic_decisions_changed_after_scan,
        scanner_output_structural_validation=scanner_output_structural_validation,
        main_agent_scan_review=main_agent_scan_review,
        written_supersedes=written_supersedes,
    )
    return {
        "write_result": write_result,
        "rerun_scan_status": rerun_scan_status,
        "durable_supersedes_written": gate_state["durable_metadata_write_allowed"],
        "quality_review_allowed_afterward": gate_state["quality_review_allowed"],
        "pending_scan_result": gate_state["pending_scan_result"],
        "stop_reason": gate_state["stop_reason"],
    }
