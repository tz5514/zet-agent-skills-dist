"""Status calculator.

A pure function that derives an ADR's `status` from its implementation state
(draft or not) and which of its atomic decisions have been superseded. `status`
is never set by hand: every moment that can change it (new ADR, draft->active
migration, applying a supersession mark) calls this and writes the result back,
so `status` stays a consistent projection of (folder + atomic decisions) and
never drifts.
"""

NOT_IMPLEMENTED_YET = "not_implemented_yet"
FULLY_GROUND_TRUTH = "fully_ground_truth"
PARTIALLY_SUPERSEDED = "partially_superseded"
FULLY_SUPERSEDED = "fully_superseded"


def compute_status(is_draft, superseded_atomic_decision_ids, all_atomic_decision_ids):
    if is_draft:
        return NOT_IMPLEMENTED_YET
    superseded = set(superseded_atomic_decision_ids)
    if not superseded:
        return FULLY_GROUND_TRUTH
    if set(all_atomic_decision_ids) <= superseded:
        return FULLY_SUPERSEDED
    return PARTIALLY_SUPERSEDED
