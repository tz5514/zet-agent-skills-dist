"""Mechanical validation of a review-spec blind-review round.

A review round's output is only usable after two mechanical checks: the report
path is extracted from the reviewer's reply by a fixed rule (never by the main
agent's judgement), and the report file passes structural validation — the
integrity marker echoed from the prompt head matches the assembler-issued
marker, the review mode matches the dispatched mode, every finding carries its
required fields, every blocker carries a failure scenario, and every gate with
zero findings carries a verification conclusion. A post-fix round additionally
requires a prior-round fix checklist whose entries are complete and, when the
dispatcher passes the normalized disposition, cover exactly the dispatched
items. Any violation makes the round invalid; an invalid round's findings must
not be consumed.
"""

import argparse
import json
import re
from pathlib import Path

REVIEW_MODES = ("initial", "post-fix")

GATE_IDS = (
    "self_sufficiency",
    "internal_contradiction",
    "reality_conflict",
    "undecided_disguised_as_decided",
    "acceptance_undecidable",
    "boundary_gap",
    "dependency_unavailable",
)

SEVERITIES = ("blocker", "non_blocker")

# Reviewer-verified statuses in a post-fix report's prior-round fix checklist:
# `fixed` means fixed and holding in the current text (and therefore not
# re-reported in findings); anything else is `not_fixed`.
PRIOR_FIX_STATUSES = ("fixed", "not_fixed")

REVIEWER_CLOSE_STATUSES = ("completed", "tool_failed", "scope_limited")

# The one fixed-format line the reviewer's outward reply must carry.
_REPORT_PATH_LINE_RE = re.compile(r"^REVIEW_REPORT_PATH:\s*(.+?)\s*$", re.MULTILINE)

_FINDING_TEXT_FIELDS = ("evidence_location", "issue", "suggested_fix")


def _is_nonempty_str(value):
    return isinstance(value, str) and value.strip() != ""


def extract_report_path(reply_text):
    """Mechanically extract the report path from the reviewer's reply text.

    Returns the path from the last `REVIEW_REPORT_PATH:` line, or ``None`` when
    no such line exists (which makes the round invalid).
    """
    matches = _REPORT_PATH_LINE_RE.findall(reply_text)
    return matches[-1] if matches else None


def _validate_finding(index, finding, gate_counts):
    if not isinstance(finding, dict):
        return [f"finding_not_object:{index}"]
    errors = []
    gate = finding.get("gate")
    if gate in gate_counts:
        gate_counts[gate] += 1
    else:
        errors.append(f"finding_unknown_gate:{index}")
    severity = finding.get("severity")
    if severity not in SEVERITIES:
        errors.append(f"finding_severity_invalid:{index}")
    for field in _FINDING_TEXT_FIELDS:
        if not _is_nonempty_str(finding.get(field)):
            errors.append(f"finding_{field}_missing:{index}")
    if severity == "blocker" and not _is_nonempty_str(finding.get("failure_scenario")):
        errors.append(f"finding_failure_scenario_missing:{index}")
    return errors


def load_prior_item_ids(disposition_path):
    """Read a normalized prior-round disposition file and return its item ids.

    Raises ``ValueError`` (or the underlying ``OSError``/``JSONDecodeError``)
    when the file is not a normalized disposition; the dispatcher treats any
    of these as an unusable cross-check input, never as a passing round.
    """
    data = json.loads(Path(disposition_path).read_text(encoding="utf-8"))
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list) or not items:
        raise ValueError("prior-round disposition has no items list")
    ids = []
    for index, item in enumerate(items):
        if not isinstance(item, dict) or not _is_nonempty_str(item.get("id")):
            raise ValueError(f"prior-round disposition item {index} has no id")
        ids.append(item["id"])
    return ids


def _validate_prior_fix_checklist(checklist, expected_prior_item_ids):
    if not isinstance(checklist, list):
        return ["prior_fix_checklist_not_list"]
    errors = []
    seen_ids = []
    for index, entry in enumerate(checklist):
        if not isinstance(entry, dict):
            errors.append(f"prior_fix_entry_not_object:{index}")
            continue
        entry_id = entry.get("id")
        if not _is_nonempty_str(entry_id):
            errors.append(f"prior_fix_entry_id_missing:{index}")
        elif entry_id in seen_ids:
            errors.append(f"prior_fix_entry_duplicate_id:{entry_id}")
        else:
            seen_ids.append(entry_id)
        if entry.get("status") not in PRIOR_FIX_STATUSES:
            errors.append(f"prior_fix_entry_status_invalid:{index}")
        if not _is_nonempty_str(entry.get("verification")):
            errors.append(f"prior_fix_entry_verification_missing:{index}")
    if expected_prior_item_ids is not None:
        for item_id in expected_prior_item_ids:
            if item_id not in seen_ids:
                errors.append(f"prior_fix_item_missing:{item_id}")
        for item_id in seen_ids:
            if item_id not in expected_prior_item_ids:
                errors.append(f"prior_fix_item_unknown:{item_id}")
    return errors


def validate_report(
    report,
    *,
    expected_integrity_marker=None,
    expected_review_mode=None,
    expected_prior_item_ids=None,
):
    """Return the list of violations; an empty list means the report is valid.

    ``expected_integrity_marker`` and ``expected_review_mode`` are compared when
    provided. The reviewer's self-check omits the marker (it cannot vouch for
    itself); the dispatching agent must always pass both. In post-fix mode the
    dispatcher additionally passes ``expected_prior_item_ids`` so the report's
    prior-round fix checklist provably covers every dispatched item.
    """
    if not isinstance(report, dict):
        return ["report_not_object"]
    errors = []
    if not _is_nonempty_str(report.get("spec_path")):
        errors.append("spec_path_missing")
    mode = report.get("review_mode")
    if mode not in REVIEW_MODES:
        errors.append("review_mode_invalid")
    elif expected_review_mode is not None and mode != expected_review_mode:
        errors.append("review_mode_mismatch")
    marker = report.get("integrity_marker")
    if not _is_nonempty_str(marker):
        errors.append("integrity_marker_missing")
    elif expected_integrity_marker is not None and marker != expected_integrity_marker:
        errors.append("integrity_marker_mismatch")
    allowed_docs = report.get("allowed_docs")
    if not isinstance(allowed_docs, list) or not all(
        _is_nonempty_str(doc) for doc in allowed_docs
    ):
        errors.append("allowed_docs_invalid")
    if report.get("reviewer_close_status") not in REVIEWER_CLOSE_STATUSES:
        errors.append("reviewer_close_status_invalid")

    # Post-fix bookkeeping: the prior-round fix checklist is mandatory in
    # post-fix mode and has no business in an initial report.
    if mode == "post-fix":
        errors.extend(
            _validate_prior_fix_checklist(
                report.get("prior_fix_checklist"), expected_prior_item_ids
            )
        )
    elif mode == "initial" and "prior_fix_checklist" in report:
        errors.append("prior_fix_checklist_unexpected")

    gate_counts = {gate: 0 for gate in GATE_IDS}
    findings = report.get("findings")
    if not isinstance(findings, list):
        errors.append("findings_not_list")
    else:
        for index, finding in enumerate(findings):
            errors.extend(_validate_finding(index, finding, gate_counts))

    conclusions = report.get("gate_conclusions")
    if not isinstance(conclusions, dict):
        errors.append("gate_conclusions_not_object")
        conclusions = {}
    for key in conclusions:
        if key not in GATE_IDS:
            errors.append(f"gate_conclusions_unknown_gate:{key}")
    # Silence is never a pass: every gate must surface either a finding or a
    # one-sentence verification conclusion.
    for gate in GATE_IDS:
        if gate_counts[gate] == 0 and not _is_nonempty_str(conclusions.get(gate)):
            errors.append(f"gate_conclusion_missing:{gate}")
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate a review-spec report file (optionally resolving "
        "its path from a saved reviewer reply first)."
    )
    parser.add_argument("report_path", nargs="?", help="path of the report JSON file")
    parser.add_argument(
        "--from-reply",
        help="path of a file holding the reviewer's reply/stdout; the report "
        "path is extracted from its REVIEW_REPORT_PATH line",
    )
    parser.add_argument(
        "--expected-marker",
        help="the assembler-issued integrity marker this round's report must echo",
    )
    parser.add_argument(
        "--expected-mode",
        choices=REVIEW_MODES,
        help="the review mode this round was dispatched with",
    )
    parser.add_argument(
        "--prior-disposition",
        help="path of the normalized prior-round disposition this post-fix "
        "round was dispatched with; the report's checklist must cover its items",
    )
    args = parser.parse_args(argv)
    if (args.report_path is None) == (args.from_reply is None):
        parser.error("pass exactly one of: report_path, --from-reply")

    report_path = args.report_path
    if report_path is None:
        try:
            reply_text = Path(args.from_reply).read_text(encoding="utf-8")
        except OSError as error:
            print(f"invalid: reply_unreadable ({error})")
            return 1
        report_path = extract_report_path(reply_text)
        if report_path is None:
            print("invalid: report_path_line_missing")
            return 1

    expected_prior_item_ids = None
    if args.prior_disposition is not None:
        try:
            expected_prior_item_ids = load_prior_item_ids(args.prior_disposition)
        except (OSError, json.JSONDecodeError, ValueError) as error:
            print(f"invalid: prior_disposition_unreadable ({error})")
            return 1

    try:
        report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"invalid: report_unreadable ({error})")
        return 1
    errors = validate_report(
        report,
        expected_integrity_marker=args.expected_marker,
        expected_review_mode=args.expected_mode,
        expected_prior_item_ids=expected_prior_item_ids,
    )
    if errors:
        print("invalid: " + "; ".join(errors))
        return 1
    print(f"valid {report_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    import sys

    raise SystemExit(main(sys.argv[1:]))
