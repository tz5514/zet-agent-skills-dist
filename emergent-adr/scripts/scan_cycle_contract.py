"""Shared scan-cycle mechanical layer for draft ADR delivery.

Owns scan freshness (`## Atomic Decisions` content hash), the accepted-rewrite
write-then-immediate-rescan order, and the tail-scan evidence comparison —
including the named terminal when a re-review is owed but no review budget
remains. Orchestration drivers call this instead of reimplementing the cycle.
Reuses the existing scan-rewrite gate and tail-evidence pure helpers; does not
fork them into a second authority.
"""

import json
from pathlib import Path
import re

from scan_rewrite_contract import (
    TAIL_EVIDENCE_REMOVED_OR_CHANGED,
    atomic_decisions_fingerprint,
    build_scan_rewrite_gate_state,
    build_scan_rewrite_loop_report,
    tail_scan_evidence_diff,
)
from supersession_pairs import parse_inline_pair


SCAN_ROLE_PRE_ACCEPTANCE = "pre_acceptance_evidence_closure"
SCAN_ROLE_POST_ACCEPTANCE_TAIL = "post_acceptance_tail"

CLOSE_PASSED = "passed"
CLOSE_REREVIEW_REQUIRED = "rereview_required"
CLOSE_PENDING = "pending"
CLOSE_FAILED = "failed"

TAIL_EVIDENCE_REREVIEW_BUDGET_EXHAUSTED = "tail_evidence_rereview_budget_exhausted"

CONTINUE_REREVIEW = "continue_rereview"
BUDGET_EXHAUSTED = "budget_exhausted"

STEP_CLOSED = "closed"
STEP_REWRITE_REQUIRED = "rewrite_required"
STEP_PENDING = "pending"
STEP_FAILED = "failed"


def build_tail_evidence_rereview_budget_exhausted_error():
    """Named terminal when the pass landed on the last budgeted round and the
    tail scan pulled away evidence the pass relied on — the owed re-review
    cannot run. Drivers report this through their own finalize path; the kind
    string is the mechanical read for callers."""
    return {
        "stage": "tail_scan",
        "kind": TAIL_EVIDENCE_REREVIEW_BUDGET_EXHAUSTED,
        "detail": {"tail_evidence_diff": TAIL_EVIDENCE_REMOVED_OR_CHANGED},
    }


def resolve_owed_rereview(*, can_rereview):
    """When a tail close owes a re-review: either continue with another review
    round, or surface the named budget-exhausted terminal. Drivers own how they
    finalize; this layer owns the mechanical decision and error shape."""
    if can_rereview:
        return {"kind": CONTINUE_REREVIEW}
    return {
        "kind": BUDGET_EXHAUSTED,
        "error": build_tail_evidence_rereview_budget_exhausted_error(),
    }


class ScanCycle:
    """Runs supersession scans for one draft delivery: drives the accepted-
    rewrite write-then-immediate-rescan loop, records every scan with its role
    and `## Atomic Decisions` fingerprint, answers whether a fresh completed
    scan result exists for the current content, and closes an accepted pass
    round with the tail-evidence comparison."""

    def __init__(
        self,
        *,
        draft_adr_path,
        scan_fn,
        write_fn,
        accept_rewrite_fn=None,
        atomic_decisions_fn=None,
        scan_rewrite_loops=None,
    ):
        self.draft_adr_path = draft_adr_path
        self.scan_fn = scan_fn
        self.write_fn = write_fn
        self.accept_rewrite_fn = accept_rewrite_fn
        self.atomic_decisions_fn = atomic_decisions_fn or read_atomic_decisions
        self.scan_rewrite_loops = list(scan_rewrite_loops or [])
        self.scans = []
        self.last_scan = None
        self.scan_invalidated = False

    def current_fingerprint(self):
        return atomic_decisions_fingerprint(self.atomic_decisions_fn(self.draft_adr_path))

    def fresh_completed_scan_state(self):
        last = self.last_scan
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

    def scan_state_from_step(self, step):
        """Return the completed scan state for immediate handoff by its driver.

        Unlike `fresh_completed_scan_state`, this does not rediscover a prior
        result from disk: `step` is the scan that just ran against the current
        draft inside the caller's still-active state transition.
        """
        if step["scan_result"].get("status") != "completed":
            return None
        return {
            "written_supersedes": list(
                step["scan_result"].get("written_supersedes") or []
            )
        }

    def run(self, role):
        pending_rewrite_write = None
        while True:
            step = self.run_step(role)
            scan_result = step["scan_result"]
            if pending_rewrite_write is not None:
                self.scan_rewrite_loops.append(
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
            if step["kind"] == STEP_REWRITE_REQUIRED:
                # accepted rewrite: apply it with `write`, then immediately
                # rescan — quality review may not run in between
                pending_rewrite_write = self.write_fn(step["rewrite_request"])
                continue
            return scan_result, step["gate"]

    def run_step(self, role, *, persisted_result_path=None):
        """Run and classify exactly one scan without applying an accepted rewrite.

        Drivers with scheduling constraints use this step interface: an accepted
        rewrite returns its canonical write request so the driver can leave its
        exclusive section, apply the write, and come back through a fresh step.
        The ordinary linear driver uses :meth:`run`, which consumes the same step
        result and applies write→immediate-rescan automatically.
        """
        request = _scan_request(self.draft_adr_path)
        if persisted_result_path is not None:
            request["persisted_result_path"] = str(persisted_result_path)
        scan_result = self.scan_fn(request)
        if persisted_result_path is not None:
            Path(persisted_result_path).write_text(
                json.dumps(scan_result, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        scan_record = self._record_scan(
            role,
            scan_result,
            self.current_fingerprint(),
        )
        if (
            scan_result["status"] == "awaiting_rewrite"
            and self.accept_rewrite_fn is not None
            and self.accept_rewrite_fn(scan_result)
        ):
            return {
                "kind": STEP_REWRITE_REQUIRED,
                "scan_result": scan_result,
                "scan_record": scan_record,
                "rewrite_request": _rewrite_request(self.draft_adr_path, scan_result),
                "gate": None,
            }

        gate = build_scan_rewrite_gate_state(
            scan_status=scan_result["status"],
            scan_result=scan_result,
            scanner_output_structural_validation=scan_result.get(
                "scanner_output_structural_validation", False
            ),
            main_agent_scan_review=scan_result.get("main_agent_scan_review", False),
            written_supersedes=scan_result.get("written_supersedes"),
        )
        return {
            "kind": _step_kind_from_gate(gate),
            "scan_result": scan_result,
            "scan_record": scan_record,
            "rewrite_request": None,
            "gate": gate,
        }

    def close_after_acceptance_pass(self, pass_round_supersedes):
        """Close delivery after an accepted pass round. Passed requires a
        non-invalidated scan result for the current `## Atomic Decisions`
        whose status is completed or skipped_no_active, and no pending scan.
        Returns a structured outcome the driver maps onto its own terminal."""
        if self.fresh_completed_scan_state() is not None:
            # the closure scan already covers the current `## Atomic Decisions`:
            # reuse it, never pay a second scan for the same content
            return {"kind": CLOSE_PASSED}
        scan_result, gate = self.run(SCAN_ROLE_POST_ACCEPTANCE_TAIL)
        return self.close_step_after_acceptance_pass(
            {
                "kind": _step_kind_from_gate(gate),
                "scan_result": scan_result,
                "scan_record": self.scans[-1],
                "rewrite_request": None,
                "gate": gate,
            },
            pass_round_supersedes,
        )

    def close_step_after_acceptance_pass(self, step, pass_round_supersedes):
        """Close an acceptance pass from a driver-owned one-scan step."""
        gate = step["gate"]
        scan_result = step["scan_result"]
        if step["kind"] == STEP_REWRITE_REQUIRED:
            return {
                "kind": CLOSE_PENDING,
                "pending_scan_result": scan_result,
            }
        if step["kind"] == STEP_PENDING:
            return {
                "kind": CLOSE_PENDING,
                "pending_scan_result": gate["pending_scan_result"],
            }
        if step["kind"] == STEP_FAILED:
            return {
                "kind": CLOSE_FAILED,
                "scan_result": scan_result,
                "stop_reason": gate["stop_reason"],
            }
        if scan_result["status"] == "completed":
            diff = tail_scan_evidence_diff(
                pass_round_supersedes, scan_result.get("written_supersedes")
            )
            step["scan_record"]["tail_evidence_diff"] = diff
            if diff == TAIL_EVIDENCE_REMOVED_OR_CHANGED:
                return {"kind": CLOSE_REREVIEW_REQUIRED}
        return {"kind": CLOSE_PASSED}

    def _record_scan(self, role, scan_result, fingerprint):
        if self.last_scan is not None and self.last_scan["fingerprint"] != fingerprint:
            # `## Atomic Decisions` changed after the previous scan: that result
            # is invalid and this scan replaces it
            self.scan_invalidated = True
        scan_record = {
            "role": role,
            "scan_status": scan_result["status"],
            "scanner_output_structural_validation": scan_result.get(
                "scanner_output_structural_validation", False
            ),
            "main_agent_scan_review": scan_result.get("main_agent_scan_review", False),
            "atomic_decisions_fingerprint": fingerprint,
        }
        self.scans.append(scan_record)
        self.last_scan = {"result": scan_result, "fingerprint": fingerprint}
        return scan_record


def _scan_request(draft_adr_path):
    return {"draft_adr_path": draft_adr_path}


def _step_kind_from_gate(gate):
    if gate["pending_scan_result"] is not None:
        return STEP_PENDING
    if gate["stop_reason"] is not None:
        return STEP_FAILED
    return STEP_CLOSED


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


def read_draft_supersedes(draft_adr_path):
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


def read_atomic_decisions(draft_adr_path):
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
