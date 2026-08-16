"""Best-effort conflict disposition.

Wraps the conflict outcome of `apply_mark_back` and turns it into a best-effort,
never-blocking disposition. Conflict detection itself is unchanged: this branch
reuses `apply_mark_back`'s three existing conflict reasons and never invents a
new one. It performs no LLM judgement; the outer operation layer decides whether
to call this after current-state verification. This module never raises or stops;
every conflict is dispositioned and reported instead of escalated.

Per-reason disposition:
  - target already archived              -> skip + clear the draft's `supersedes`
                                            entry (the supersession is now moot)
  - target atomic decision already       -> skip + clear the entry (same: moot)
    superseded by another draft
  - target no longer in `active/`        -> skip + KEEP the entry (a human may
                                            later re-point it)

All three conflict types are flagged for the after-report and need human review;
the applied (non-conflict) case is not reported.
"""

from supersession_mark_back import (
    apply_mark_back,
    OUTCOME_APPLIED,
    CONFLICT_ALREADY_ARCHIVED,
    CONFLICT_ATOMIC_DECISION_ALREADY_SUPERSEDED,
    CONFLICT_TARGET_MISSING,
)

DISPOSITION_APPLY = "apply"
DISPOSITION_SKIP_CLEAR_ENTRY = "skip_clear_entry"
DISPOSITION_SKIP_KEEP_ENTRY = "skip_keep_entry"

_CONFLICT_DISPOSITION = {
    CONFLICT_ALREADY_ARCHIVED: DISPOSITION_SKIP_CLEAR_ENTRY,
    CONFLICT_ATOMIC_DECISION_ALREADY_SUPERSEDED: DISPOSITION_SKIP_CLEAR_ENTRY,
    CONFLICT_TARGET_MISSING: DISPOSITION_SKIP_KEEP_ENTRY,
}


def dispose_mark(draft_adr, entry, target_state):
    result = apply_mark_back(draft_adr, entry, target_state)
    if result["outcome"] == OUTCOME_APPLIED:
        return {
            "disposition": DISPOSITION_APPLY,
            "new_entry": result["new_entry"],
            "new_status": result["new_status"],
            "archive": result["archive"],
            "report": False,
        }
    reason = result["reason"]
    return {
        "disposition": _CONFLICT_DISPOSITION[reason],
        "reason": reason,
        "report": True,
        "needs_human_review": True,
    }
