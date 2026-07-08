"""Build scan-supersession structured returns and draft-side writes.

This helper consumes structurally valid row text. It can rewrite only the trigger
draft's `supersedes` frontmatter, and only when there are no rewrite-required or
review-blocking rows. It never touches active or archived ADRs.
"""

import argparse
import json
import re
import sys
from pathlib import Path

from adr_id import ADR_ID_RANDOM_ALPHABET
from context_derivation import derive_context_root
from supersession_pairs import (
    compress_atomic_decision_pairs,
    format_inline_pair,
    supersession_pairs_are_valid,
)


ADR_ROW_ID_PATTERN = rf"(?:\d{{4}}|\d{{8}}-[{ADR_ID_RANDOM_ALPHABET}]{{4}})"

ROW_RE = re.compile(
    rf"^(?P<id>{ADR_ROW_ID_PATTERN}): (?P<status>FULL|PARTIAL|NEEDS_REWRITE|MIXED); "
    r"markable: (?P<markable>.*?); rewrite-needed: (?P<rewrite>.*?); "
    r"confidence: (?P<confidence>high|low); basis: (?P<basis>.*)$"
)
ATOMIC_DECISION_ID_RE = re.compile(r"^[A-Za-z]+$")


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def candidate_by_id(packet):
    return {candidate["number"]: candidate for candidate in packet["candidates"]}


def split_mapping(value, arrow):
    value = value.strip()
    if value == "none":
        return []
    mappings = []
    for part in value.split(","):
        item = part.strip()
        if not item:
            continue
        if arrow not in item:
            raise ValueError(f"mapping lacks {arrow}: {item}")
        left, right = item.split(arrow, 1)
        targets = [target.strip() for target in right.split("+") if target.strip()]
        mappings.append({"old_atom_id": left.strip(), "trigger_atom_ids": targets})
    return mappings


def scan_mapping_validation_issues(packet, findings):
    trigger_ids = {atom["id"] for atom in packet["trigger"]["atomic_decisions"]}
    candidate_atoms = {
        candidate["number"]: {atom["id"] for atom in candidate["atomic_decisions"]}
        for candidate in packet["candidates"]
    }
    issues = []
    for finding in findings:
        candidate_id = finding["candidate"]["number"]
        old_ids = candidate_atoms.get(candidate_id, set())
        for mapping_kind, mappings in [
            ("MARKABLE", finding["markable_mappings"]),
            ("NEEDS_REWRITE", finding["rewrite_mappings"]),
        ]:
            for mapping in mappings:
                old_id = mapping["old_atom_id"]
                if not legal_atomic_decision_id(old_id):
                    issues.append(f"{candidate_id}.{old_id}: invalid old_atom_id")
                elif old_id not in old_ids:
                    issues.append(f"{candidate_id}.{old_id}: unknown old_atom_id")
                if not mapping["trigger_atom_ids"]:
                    issues.append(f"{candidate_id}.{old_id}: {mapping_kind} has no trigger ids")
                for trigger_id in mapping["trigger_atom_ids"]:
                    if not legal_atomic_decision_id(trigger_id):
                        issues.append(f"{candidate_id}.{old_id}: invalid trigger id {trigger_id}")
                    elif trigger_id not in trigger_ids:
                        issues.append(f"{candidate_id}.{old_id}: unknown trigger id {trigger_id}")
    return issues


def parse_rows(row_text, packet):
    candidates = candidate_by_id(packet)
    findings = []
    rewrite_required = []
    low_confidence = []
    written_entries = []

    for line_no, line in enumerate(row_text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped == "SCAN: none":
            continue
        match = ROW_RE.match(stripped)
        if not match:
            raise ValueError(f"line {line_no}: malformed row")
        candidate_id = match.group("id")
        candidate = candidates.get(candidate_id)
        if candidate is None:
            raise ValueError(f"line {line_no}: unknown candidate {candidate_id}")

        markable = split_mapping(match.group("markable"), "→")
        rewrite = split_mapping(match.group("rewrite"), "↯")
        relation = {
            "FULL": "full",
            "PARTIAL": "partial",
            "NEEDS_REWRITE": "mixed",
            "MIXED": "mixed",
        }[match.group("status")]
        candidate_identity = {
            "adr": candidate["adr"],
            "path": candidate["path"],
            "number": candidate["number"],
        }
        disposition = "withheld_for_rewrite" if rewrite else "written"
        finding = {
            "issue": f"scan-supersession {candidate_id} result: {match.group('status')}",
            "evidence_location": candidate_identity["adr"],
            "why_it_matters": "Scan results control whether durable supersedes metadata can be written before downstream quality review.",
            "suggested_fix": (
                "Rewrite the draft atom as a complete replacement before writing supersedes metadata."
                if rewrite
                else "Use the validated scan mapping to write durable supersedes metadata."
            ),
            "candidate": candidate_identity,
            "relation": relation,
            "confidence": match.group("confidence"),
            "basis": match.group("basis"),
            "markable_mappings": [
                {**mapping, "writeable": not rewrite}
                for mapping in markable
            ],
            "rewrite_mappings": [
                {
                    **mapping,
                    "writeable": False,
                    "reason": "rewrite_draft_atom_as_complete_replacement",
                }
                for mapping in rewrite
            ],
            "disposition": disposition,
        }
        findings.append(finding)

        for mapping in rewrite:
            rewrite_required.append(
                {
                    "candidate": candidate_identity,
                    "old_atom_id": mapping["old_atom_id"],
                    "trigger_atom_ids": mapping["trigger_atom_ids"],
                    "reason": "the draft changes only part of the old atom or leaves old payload unresolved",
                    "required_action": "rewrite_draft_atom_as_complete_replacement",
                }
            )
        if match.group("confidence") == "low":
            for mapping in markable + rewrite:
                low_confidence.append(
                    {
                        "candidate": candidate_identity,
                        "old_atom_id": mapping["old_atom_id"],
                        "trigger_atom_ids": mapping["trigger_atom_ids"],
                        "basis": match.group("basis"),
                    }
                )
        if markable and not rewrite:
            written_entries.append(
                {
                    "candidate": candidate_identity,
                    "atomic_decisions": compress_atomic_decision_pairs(
                        [
                            {"ours": trigger_id, "theirs": mapping["old_atom_id"]}
                            for mapping in markable
                            for trigger_id in mapping["trigger_atom_ids"]
                        ],
                        block_key="supersedes",
                    ),
                }
            )

    return findings, rewrite_required, low_confidence, written_entries


def empty_operation_return(draft_path, candidate_count, scanner_dispatched, status):
    return {
        "operation": "scan-supersession",
        "status": status,
        "draft_adr_path": draft_path,
        "bounded_context_path": derive_context_root(draft_path),
        "candidate_count": candidate_count,
        "scanner_dispatched": scanner_dispatched,
        "description_filtering_used": False,
        "decision_authority": "## Atomic Decisions",
        "findings": [],
        "rewrite_required": [],
        "low_confidence": [],
        "written_supersedes": [],
        "frontmatter_write_status": "not_requested",
        "escalations": [],
        "diagnostics": {
            "active_candidate_source": "scan_candidates.py",
            "description_filtering_used": False,
            "structural_issue_count": 0,
        },
    }


def zero_active_return(draft_adr_path):
    return empty_operation_return(
        draft_path=draft_adr_path,
        candidate_count=0,
        scanner_dispatched=False,
        status="skipped_no_active",
    )


def awaiting_review_return(packet, issues, stage="structural_validation"):
    result = empty_operation_return(
        draft_path=packet["trigger"]["path"],
        candidate_count=len(packet["candidates"]),
        scanner_dispatched=bool(packet["candidates"]),
        status="awaiting_review",
    )
    result["escalations"] = [
        {
            "type": "structural_validation_failed",
            "stage": stage,
            "issues": issues,
            "required_action": "rerun_or_main_agent_review",
        }
    ]
    result["diagnostics"]["structural_issue_count"] = len(issues)
    return result


def structured_return(packet, row_text, write_enabled=False):
    findings, rewrite_required, low_confidence, writable_entries = parse_rows(row_text, packet)
    mapping_issues = scan_mapping_validation_issues(packet, findings)
    if mapping_issues:
        return awaiting_review_return(packet, mapping_issues, stage="scan_mapping_validation")
    status = "awaiting_rewrite" if rewrite_required else "completed"
    return {
        "operation": "scan-supersession",
        "status": status,
        "draft_adr_path": packet["trigger"]["path"],
        "bounded_context_path": derive_context_root(packet["trigger"]["path"]),
        "candidate_count": len(packet["candidates"]),
        "scanner_dispatched": bool(packet["candidates"]),
        "description_filtering_used": False,
        "decision_authority": "## Atomic Decisions",
        "findings": findings,
        "rewrite_required": rewrite_required,
        "low_confidence": low_confidence,
        "written_supersedes": writable_entries if write_enabled and not rewrite_required else [],
        "frontmatter_write_status": "not_requested",
        "escalations": [],
        "diagnostics": {
            "active_candidate_source": "scan_candidates.py",
            "description_filtering_used": False,
            "structural_issue_count": 0,
        },
    }


def remove_frontmatter_key(lines, key):
    output = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith(f"{key}:"):
            index += 1
            while index < len(lines):
                next_line = lines[index]
                if next_line and not next_line.startswith((" ", "-")) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*:", next_line):
                    break
                index += 1
            continue
        output.append(line)
        index += 1
    return output


def format_supersedes(entries):
    if not entries:
        return []
    lines = ["supersedes:"]
    for entry in entries:
        lines.append(f"  - adr: {entry['candidate']['adr']}")
        lines.append("    atomic_decisions:")
        for pair in compress_atomic_decision_pairs(entry["atomic_decisions"], block_key="supersedes"):
            lines.append(f"      {format_inline_pair(pair)}")
    return lines


def legal_atomic_decision_id(value):
    return isinstance(value, str) and bool(ATOMIC_DECISION_ID_RE.fullmatch(value))


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


def write_draft_supersedes(draft_path, entries):
    path = Path(draft_path)
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("draft has no frontmatter")
    end = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = index
            break
    if end is None:
        raise ValueError("draft frontmatter is not closed")

    frontmatter = remove_frontmatter_key(lines[1:end], "supersedes")
    supersedes_lines = format_supersedes(entries)
    new_lines = ["---", *frontmatter]
    if supersedes_lines:
        new_lines.extend(supersedes_lines)
    new_lines.extend(lines[end:])
    path.write_text("\n".join(new_lines) + ("\n" if text.endswith("\n") else ""), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet")
    parser.add_argument("--rows")
    parser.add_argument("--zero-active-draft")
    parser.add_argument("--review-report")
    parser.add_argument("--out", required=True)
    parser.add_argument("--write-draft-supersedes", action="store_true")
    parser.add_argument("--scanner-output-structural-validation-passed", action="store_true")
    parser.add_argument("--main-agent-scan-review-passed", action="store_true")
    args = parser.parse_args(argv)
    reviewed_scan_output = (
        args.scanner_output_structural_validation_passed
        and args.main_agent_scan_review_passed
    )

    if args.zero_active_draft:
        result = zero_active_return(args.zero_active_draft)
    elif args.review_report:
        if not args.packet:
            parser.error("--review-report requires --packet")
        packet = load_json(args.packet)
        report = load_json(args.review_report)
        result = awaiting_review_return(packet, report.get("issues", []))
    else:
        if not args.packet or not args.rows:
            parser.error("--packet and --rows are required unless --zero-active-draft or --review-report is used")
        packet = load_json(args.packet)
        row_text = Path(args.rows).read_text(encoding="utf-8")
        result = structured_return(packet, row_text, write_enabled=args.write_draft_supersedes and reviewed_scan_output)
    if args.write_draft_supersedes:
        result["diagnostics"]["scanner_output_structural_validation"] = args.scanner_output_structural_validation_passed
        result["diagnostics"]["main_agent_scan_review"] = args.main_agent_scan_review_passed
        scan_result_complete = result["status"] in {"completed", "skipped_no_active"}
        scan_ready_to_write = (
            reviewed_scan_output
            and scan_result_complete
            and not result["rewrite_required"]
            and not result["escalations"]
        )
        has_supersedes_to_write = bool(result["written_supersedes"])
        metadata_valid = supersedes_entries_are_valid(result["written_supersedes"])
        if scan_ready_to_write and not has_supersedes_to_write:
            write_draft_supersedes(result["draft_adr_path"], [])
            result["frontmatter_write_status"] = "cleared_supersedes"
        elif scan_ready_to_write and metadata_valid:
            write_draft_supersedes(result["draft_adr_path"], result["written_supersedes"])
            result["frontmatter_write_status"] = "wrote_supersedes"
        elif not reviewed_scan_output:
            result["frontmatter_write_status"] = "blocked_scan_output_not_reviewed"
            result["diagnostics"]["write_skipped"] = "scan_output_not_reviewed"
        elif not scan_result_complete or result["rewrite_required"] or result["escalations"]:
            result["frontmatter_write_status"] = "blocked_pending_rewrite_or_review"
            result["diagnostics"]["write_skipped"] = "pending_rewrite_or_review"
        else:
            result["frontmatter_write_status"] = "blocked_invalid_supersedes_metadata"
            result["diagnostics"]["write_skipped"] = "invalid_supersedes_metadata"
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
