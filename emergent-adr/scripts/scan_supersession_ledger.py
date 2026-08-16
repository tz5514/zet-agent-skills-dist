"""Validate a scanner ledger and format scan rows.

This helper validates structure against an Atomic-Decisions packet. It does not
inspect atom wording to repair semantics. Invalid structure is reported as an
issue for retry or review.
"""

import argparse
import json
import re
import sys
from pathlib import Path


STATUSES = {"MARKABLE", "NEEDS_REWRITE", "UNMAPPED"}
CONFIDENCES = {"high", "low"}
ATOMIC_DECISION_ID_RE = re.compile(r"^[A-Za-z]+$")


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def packet_indexes(packet):
    trigger_ids = {atom["id"] for atom in packet["trigger"]["atomic_decisions"]}
    candidates = {
        candidate["number"]: [atom["id"] for atom in candidate["atomic_decisions"]]
        for candidate in packet["candidates"]
    }
    return trigger_ids, candidates


def legal_atomic_decision_id(value):
    return isinstance(value, str) and bool(ATOMIC_DECISION_ID_RE.fullmatch(value))


def packet_id_issues(packet):
    issues = []
    for atom in packet["trigger"]["atomic_decisions"]:
        atom_id = atom.get("id")
        if not legal_atomic_decision_id(atom_id):
            issues.append(f"trigger.{atom_id}: invalid atomic decision id")
    for candidate in packet["candidates"]:
        candidate_id = candidate["number"]
        for atom in candidate["atomic_decisions"]:
            atom_id = atom.get("id")
            if not legal_atomic_decision_id(atom_id):
                issues.append(f"{candidate_id}.{atom_id}: invalid atomic decision id")
    return issues


def join_mapping(items, arrow):
    if not items:
        return "none"
    return ", ".join(f"{old_id}{arrow}{'+'.join(trigger_ids)}" for old_id, trigger_ids in items)


def validate_and_format(ledger, packet, expected_integrity_marker=None):
    issues = []
    rows = []
    issues.extend(packet_id_issues(packet))
    trigger_ids, candidate_atoms = packet_indexes(packet)

    if not isinstance(ledger, dict):
        return [], ["ledger root is not an object"]
    if (
        expected_integrity_marker is not None
        and ledger.get("integrity_marker") != expected_integrity_marker
    ):
        # the marker at the prompt file's head must be echoed here: a missing or
        # mismatched echo means the scanner never read the dispatched prompt
        # file, which fails structural validation like any other ledger defect
        issues.append("integrity_marker: missing or mismatched")
    ledger_rows = ledger.get("rows")
    if not isinstance(ledger_rows, list):
        return [], ["ledger root.rows is not a list"]

    seen_candidates = []
    for row_index, row in enumerate(ledger_rows):
        if not isinstance(row, dict):
            issues.append(f"row[{row_index}] is not an object")
            continue
        candidate_id = row.get("candidate_id")
        if not isinstance(candidate_id, str):
            issues.append(f"row[{row_index}].candidate_id is not a string")
            continue
        if candidate_id not in candidate_atoms:
            issues.append(f"{candidate_id}: unknown candidate_id")
            continue
        seen_candidates.append(candidate_id)

        ledger_entries = row.get("ledger")
        if not isinstance(ledger_entries, list):
            issues.append(f"{candidate_id}: ledger is not a list")
            continue
        entries_by_old = {}
        for entry_index, entry in enumerate(ledger_entries):
            if not isinstance(entry, dict):
                issues.append(f"{candidate_id}.ledger[{entry_index}] is not an object")
                continue
            old_id = entry.get("old_atom_id")
            if not isinstance(old_id, str):
                issues.append(f"{candidate_id}.ledger[{entry_index}].old_atom_id is not a string")
                continue
            if not legal_atomic_decision_id(old_id):
                issues.append(f"{candidate_id}.{old_id}: invalid old_atom_id")
                continue
            if old_id in entries_by_old:
                issues.append(f"{candidate_id}: duplicate old_atom_id {old_id}")
                continue
            entries_by_old[old_id] = entry

        source_old_ids = candidate_atoms[candidate_id]
        if list(entries_by_old) != source_old_ids:
            issues.append(
                f"{candidate_id}: old atom order/set mismatch: "
                f"expected {'+'.join(source_old_ids)} got {'+'.join(entries_by_old)}"
            )

        markable = []
        rewrite = []
        confidence = "high"
        for old_id in source_old_ids:
            entry = entries_by_old.get(old_id)
            if entry is None:
                continue
            status = entry.get("status")
            if status not in STATUSES:
                issues.append(f"{candidate_id}.{old_id}: invalid status {status!r}")
                continue
            entry_confidence = entry.get("confidence")
            if entry_confidence not in CONFIDENCES:
                issues.append(f"{candidate_id}.{old_id}: invalid confidence {entry_confidence!r}")
            elif entry_confidence == "low":
                confidence = "low"
            target_ids = entry.get("trigger_atom_ids")
            if not isinstance(target_ids, list) or not all(isinstance(item, str) for item in target_ids):
                issues.append(f"{candidate_id}.{old_id}: trigger_atom_ids is not a string list")
                target_ids = []
            illegal_targets = [target_id for target_id in target_ids if not legal_atomic_decision_id(target_id)]
            if illegal_targets:
                issues.append(f"{candidate_id}.{old_id}: invalid trigger ids {'+'.join(illegal_targets)}")
            unknown_targets = [target_id for target_id in target_ids if target_id not in trigger_ids]
            if unknown_targets:
                issues.append(f"{candidate_id}.{old_id}: unknown trigger ids {'+'.join(unknown_targets)}")

            if status == "UNMAPPED":
                if target_ids:
                    issues.append(f"{candidate_id}.{old_id}: UNMAPPED has trigger ids")
            elif status == "MARKABLE":
                if not target_ids:
                    issues.append(f"{candidate_id}.{old_id}: MARKABLE lacks trigger ids")
                markable.append((old_id, target_ids))
            else:
                if not target_ids:
                    issues.append(f"{candidate_id}.{old_id}: NEEDS_REWRITE lacks trigger ids")
                rewrite.append((old_id, target_ids))

        if not markable and not rewrite:
            continue
        if markable and rewrite:
            aggregate = "MIXED"
        elif rewrite:
            aggregate = "NEEDS_REWRITE"
        elif len(markable) == len(source_old_ids):
            aggregate = "FULL"
        else:
            aggregate = "PARTIAL"

        basis_parts = []
        for old_id, _target_ids in markable + rewrite:
            basis = entries_by_old.get(old_id, {}).get("basis")
            if isinstance(basis, str) and basis.strip():
                basis_parts.append(f"{old_id}: {basis.strip()}")
        basis = "; ".join(basis_parts) if basis_parts else "ledger classification"
        rows.append(
            f"{candidate_id}: {aggregate}; "
            f"markable: {join_mapping(markable, '→')}; "
            f"rewrite-needed: {join_mapping(rewrite, '↯')}; "
            f"confidence: {confidence}; "
            f"basis: old={'+'.join(source_old_ids)}; {basis}"
        )

    expected_candidate_order = list(candidate_atoms)
    if seen_candidates != expected_candidate_order:
        issues.append(
            "candidate row order/set mismatch: "
            f"expected {','.join(expected_candidate_order)} got {','.join(seen_candidates)}"
        )
    return rows, issues


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--packet", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--expected-integrity-marker")
    args = parser.parse_args(argv)

    ledger = load_json(args.ledger)
    packet = load_json(args.packet)
    rows, issues = validate_and_format(
        ledger, packet, expected_integrity_marker=args.expected_integrity_marker
    )
    row_text = "\n".join(rows) if rows else "SCAN: none"
    Path(args.out).write_text(row_text + "\n", encoding="utf-8")
    report = {
        "ledger": args.ledger,
        "packet": args.packet,
        "rows_out": len(rows),
        "issue_count": len(issues),
        "issues": issues,
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
