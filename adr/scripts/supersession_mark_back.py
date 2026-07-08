"""Supersession-mark back-derivation.

The closed mechanical core of draft->active migration. Given ONE of a draft's
`supersedes` entries and the target active ADR's current state, it either APPLIES
the mark (produces the mirrored entry to add to the target's `superseded_by` and
recomputes the target's status / archival) or REPORTS a CONFLICT. It performs no
LLM judgement: deciding whether the supersession still holds, whether to call
this, and how to escalate a conflict to a human belongs to the outer
re-verification layer, not this module.

Closed input contract:
  - entry        = {adr: <target>, atomic_decisions: [{ours, theirs}, ...]}   (no
                   apply_status; ours = the draft's atomic decision, theirs = the
                   TARGET's atomic decision)
  - draft_adr    = the superseding draft's stable id/filename
  - target_state = {location, all_atomic_decision_ids, superseded_by}
       location  : one of "active" | "archived" | "missing" (mutually exclusive)
       superseded_by : the target's existing entries
                       [{adr, atomic_decisions:[{ours, theirs}]}]
                       (ours = the TARGET's atomic decision — its already-superseded
                       atomic decisions)

Comparison axis = the target's OWN atomic-decision id: this entry's `theirs` (a
target atomic decision) is compared against the target's existing `superseded_by`
`ours` (target atomic decisions already superseded). Never theirs-vs-theirs —
`theirs` on different files are different files' atomic decisions and their letters
collide across files.

Dependency-free apart from the sibling pure-logic helpers.
"""

from status_calculator import compute_status, FULLY_SUPERSEDED
from supersession_converter import convert_entry

OUTCOME_APPLIED = "applied"
OUTCOME_CONFLICT = "conflict"

CONFLICT_ALREADY_ARCHIVED = "target_already_archived"
CONFLICT_ATOMIC_DECISION_ALREADY_SUPERSEDED = "target_atomic_decision_already_superseded"
CONFLICT_TARGET_MISSING = "target_not_in_active"

LOCATION_ACTIVE = "active"
LOCATION_ARCHIVED = "archived"
LOCATION_MISSING = "missing"


def apply_mark_back(draft_adr, entry, target_state):
    location = target_state["location"]
    if location == LOCATION_ARCHIVED:
        return {"outcome": OUTCOME_CONFLICT, "reason": CONFLICT_ALREADY_ARCHIVED}
    if location == LOCATION_MISSING:
        return {"outcome": OUTCOME_CONFLICT, "reason": CONFLICT_TARGET_MISSING}

    # location == active: the target atomic decisions this entry would supersede
    # are its `theirs`.
    entry_target_atomic_decisions = {pair["theirs"] for pair in entry["atomic_decisions"]}
    already_superseded = {
        pair["ours"]
        for existing in target_state.get("superseded_by", [])
        for pair in existing["atomic_decisions"]
    }
    overlap = entry_target_atomic_decisions & already_superseded
    if overlap:
        return {
            "outcome": OUTCOME_CONFLICT,
            "reason": CONFLICT_ATOMIC_DECISION_ALREADY_SUPERSEDED,
        }

    new_entry = convert_entry(entry, draft_adr)
    new_superseded = already_superseded | entry_target_atomic_decisions
    new_status = compute_status(
        is_draft=False,
        superseded_atomic_decision_ids=new_superseded,
        all_atomic_decision_ids=target_state["all_atomic_decision_ids"],
    )
    return {
        "outcome": OUTCOME_APPLIED,
        "new_entry": new_entry,
        "new_status": new_status,
        "archive": new_status == FULLY_SUPERSEDED,
    }
