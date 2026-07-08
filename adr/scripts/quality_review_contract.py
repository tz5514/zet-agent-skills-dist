"""Mechanical ADR quality-review contract helpers.

This module keeps stable gate ids and cheap structural checks in one place so
prompt text, report examples, and tests can stay aligned without duplicating the
full writing rules.
"""

from pathlib import Path
import re

from context_derivation import derive_context_root
import review_prompt_assembly
from adr_id import is_adr_id
from supersession_pairs import (
    expand_atomic_decision_pairs,
    parse_inline_pair,
    supersession_pairs_are_valid,
)


VALID_STATUSES = {
    "not_implemented_yet",
    "fully_ground_truth",
    "partially_superseded",
    "fully_superseded",
}

QUALITY_REVIEW_MODE = "quality_review"
CONTEXT_GLOSSARY_APPROVAL_PREFLIGHT_MODE = "context_glossary_approval_preflight"
FROZEN_GLOSSARY_REVIEW_MODE = "frozen_glossary_review"

# The three named quality-review execution modes. Narrowing is carried by the
# mode name only — there is no caller-chosen gate set/order parameter.
REVIEW_MODES = [
    QUALITY_REVIEW_MODE,
    CONTEXT_GLOSSARY_APPROVAL_PREFLIGHT_MODE,
    FROZEN_GLOSSARY_REVIEW_MODE,
]

# The formal gate order is owned in one place — the `@gate:` marker order in
# QUALITY-REVIEW-PROMPT-BLOCKS.md, surfaced by the assembly helper. This list is
# derived from it so the mechanical gate-coverage bookkeeping and the reviewer
# prompt can never drift into two hand-copied sources.
GATE_COVERAGE_IDS = review_prompt_assembly.gate_ids()

STRUCTURAL_REVIEWABILITY_CHECK_IDS = [
    "target_path_exists",
    "bounded_context_derivable",
    "frontmatter_parseable",
    "required_frontmatter_fields",
    "legal_status_enum",
    "status_folder_consistency",
    "supersession_schema_shape",
    "required_body_headings_and_order",
    "parseable_atomic_decision_bullets",
    "legal_atomic_decision_ids",
    "unique_atomic_decision_ids",
    "markdown_damage_blocks_review",
]

def normalize_review_mode(mode):
    if mode is None or mode == "":
        return QUALITY_REVIEW_MODE
    if mode in set(REVIEW_MODES):
        return mode
    raise ValueError(f"unsupported quality-review mode: {mode}")


def glossary_approval_need_finding(
    *,
    target_wording,
    why_ordinary_prose_cannot_preserve_decision_meaning,
    context_change_kind,
    proposed_wording,
    required_user_action,
):
    return {
        "issue": f"CONTEXT.md glossary approval needed for {target_wording}",
        "gate_id": "context_glossary_approval_need_check",
        "evidence_location": target_wording,
        "why_it_matters": why_ordinary_prose_cannot_preserve_decision_meaning,
        "suggested_fix": required_user_action,
        "action_data": {
            "target_wording": target_wording,
            "why_ordinary_prose_cannot_preserve_decision_meaning": why_ordinary_prose_cannot_preserve_decision_meaning,
            "context_change_kind": context_change_kind,
            "proposed_wording": proposed_wording,
            "required_user_action": required_user_action,
            "full_quality_review_notice": "Full ADR quality review has not run.",
        },
    }


def build_context_glossary_approval_preflight_report(target_adr_path, glossary_approval_findings=None):
    glossary_approval_findings = list(glossary_approval_findings or [])
    structural = check_structural_reviewability(target_adr_path)
    gate_coverage = {gate_id: "skipped" for gate_id in GATE_COVERAGE_IDS}
    skipped_gate_reasons = {}
    gate_coverage["adr_structural_reviewability_check"] = "evaluated"

    blocking = []
    preflight_status = "passed"
    review_status = "not_evaluated"
    terminal_result = None

    if structural["status"] == "blocked":
        blocking.extend(structural["findings"])
        preflight_status = "blocked"
        review_status = "fail"
        # the same named terminal the reviewer verdict channel uses for this stop
        terminal_result = "blocked_by_structural_unreadability"
        skipped_gate_reasons["context_glossary_approval_need_check"] = "blocked_by_structural_unreadability"
        for gate_id in GATE_COVERAGE_IDS[2:]:
            skipped_gate_reasons[gate_id] = "blocked_by_structural_unreadability"
    else:
        gate_coverage["context_glossary_approval_need_check"] = "evaluated"
        blocking.extend(glossary_approval_findings)
        if glossary_approval_findings:
            preflight_status = "failed"
            review_status = "fail"
        for gate_id in GATE_COVERAGE_IDS[2:]:
            skipped_gate_reasons[gate_id] = "context_glossary_approval_preflight_complete"

    return {
        "target_adr_path": target_adr_path,
        "review_mode": CONTEXT_GLOSSARY_APPROVAL_PREFLIGHT_MODE,
        "review_status": review_status,
        "terminal_result": terminal_result,
        "preflight_status": preflight_status,
        "full_quality_review_completed": False,
        "full_quality_review_notice": "Full ADR quality review has not run.",
        "support_data_status": "not_applicable",
        "source_decision_extract_status": "not_applicable",
        "live_atomic_decision_corpus_status": "not_applicable",
        "gate_coverage": gate_coverage,
        "skipped_gate_reasons": skipped_gate_reasons,
        "blocking": blocking,
        "non_blocking": [],
        "reference_closure": _not_evaluated_reference_closure(),
        "scope_limitations": ["Full ADR quality review has not run."],
        "reviewer_close_status": "completed",
    }


def evaluate_adr_necessity_candidate(
    *,
    hard_to_reverse,
    surprising_without_context,
    real_tradeoff,
    decision_context_value,
    evidence_location,
):
    blocking = []
    if not hard_to_reverse:
        blocking.append(_adr_necessity_finding("easy_to_reverse_decision", evidence_location))
    if not surprising_without_context:
        blocking.append(_adr_necessity_finding("unsurprising_decision", evidence_location))
    if not real_tradeoff:
        blocking.append(_adr_necessity_finding("no_real_tradeoff", evidence_location))
    if not decision_context_value:
        blocking.append(_adr_necessity_finding("insufficient_decision_context_value", evidence_location))
    return {
        "gate_id": "adr_necessity_of_existence_check",
        "status": "blocking" if blocking else "evaluated",
        "blocking": blocking,
    }


def build_adr_necessity_terminal_report(target_adr_path, necessity_finding):
    gate_coverage = {gate_id: "evaluated" for gate_id in GATE_COVERAGE_IDS[:5]}
    gate_coverage.update({gate_id: "skipped" for gate_id in GATE_COVERAGE_IDS[5:]})
    skipped_gate_reasons = {
        gate_id: "skipped_by_adr_necessity_failure"
        for gate_id in GATE_COVERAGE_IDS[5:]
    }
    return {
        "target_adr_path": target_adr_path,
        "review_mode": QUALITY_REVIEW_MODE,
        "review_status": "fail",
        "terminal_result": "not_an_adr_candidate",
        "preflight_status": "not_applicable",
        "full_quality_review_completed": False,
        "full_quality_review_notice": "Full ADR quality review stopped at ADR necessity.",
        "support_data_status": "not_applicable",
        "source_decision_extract_status": "not_applicable",
        "live_atomic_decision_corpus_status": "not_applicable",
        "gate_coverage": gate_coverage,
        "skipped_gate_reasons": skipped_gate_reasons,
        "blocking": [necessity_finding],
        "non_blocking": [],
        "reference_closure": _not_evaluated_reference_closure(),
        "scope_limitations": ["Later gates were not evaluated after ADR necessity failed."],
        "reviewer_close_status": "completed",
    }


def _not_evaluated_reference_closure():
    return {
        "status": "not_evaluated",
        "checked_references": [],
        "unresolved_references": [],
    }


def classify_repeated_live_supersedes_evidence(target_adr_path, target_atomic_decision_id, live_decision):
    live_adr_number = live_decision.get("active_adr_number")
    live_adr = live_decision.get("active_adr")
    live_atomic_decision_id = live_decision.get("atomic_decision_id")
    if not live_adr_number or not live_adr or not live_atomic_decision_id:
        return _repeated_live_evidence_result("unresolved_live_decision_identity", False)

    frontmatter, _ = _split_frontmatter(Path(target_adr_path).read_text(encoding="utf-8"))
    if frontmatter is None:
        frontmatter = []

    supersedes_block = _frontmatter_key_block(frontmatter, "supersedes")
    if supersedes_block is None:
        return _repeated_live_evidence_result("no_supersedes", False)
    if not supersedes_block.strip():
        return _repeated_live_evidence_result("empty_supersedes", False)
    if not _supersession_schema_is_valid(frontmatter):
        return _repeated_live_evidence_result("malformed_supersedes", False)

    unresolved_reference = False
    for pair in _supersedes_pairs(supersedes_block):
        if (
            pair["ours"] == target_atomic_decision_id
            and pair["theirs"] == live_atomic_decision_id
        ):
            if _adr_reference_matches_live(pair["adr"], live_adr, live_adr_number):
                return _repeated_live_evidence_result("exact_match", True)
            unresolved_reference = True
    if unresolved_reference:
        return _repeated_live_evidence_result("unresolved_supersedes_reference", False)
    return _repeated_live_evidence_result("missing_matching_supersedes", False)


def check_structural_reviewability(target_adr_path):
    checks = {check_id: "passed" for check_id in STRUCTURAL_REVIEWABILITY_CHECK_IDS}
    findings = []
    path = Path(target_adr_path)

    def fail(check_id, evidence, suggested_fix):
        checks[check_id] = "failed"
        findings.append(
            {
                "issue": check_id,
                "check_id": check_id,
                "evidence_location": evidence,
                "why_it_matters": "The target cannot be reliably reviewed by later ADR quality-review gates.",
                "suggested_fix": suggested_fix,
            }
        )

    if not path.exists():
        fail("target_path_exists", str(path), "Provide an existing ADR file path.")
        return _structural_result(checks, findings)

    try:
        derive_context_root(str(path))
    except Exception as exc:  # pragma: no cover - exact exception depends on path shape
        fail("bounded_context_derivable", str(path), f"Place the ADR under a bounded context docs/adr folder: {exc}")

    text = path.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(text)
    if frontmatter is None:
        fail("frontmatter_parseable", str(path), "Start the file with a closed YAML frontmatter block.")
        frontmatter = []
        body = text
    elif not _frontmatter_mapping_is_parseable(frontmatter):
        fail("frontmatter_parseable", "frontmatter YAML", "Use parseable YAML mapping-shaped frontmatter.")

    frontmatter_values = _frontmatter_scalar_values(frontmatter)
    if "status" not in frontmatter_values or "description" not in frontmatter_values:
        fail("required_frontmatter_fields", str(path), "Include status and description frontmatter fields.")

    status = frontmatter_values.get("status")
    if status is not None and status not in VALID_STATUSES:
        fail("legal_status_enum", "frontmatter status", "Use one legal ADR lifecycle status value.")

    if status in VALID_STATUSES and not _status_matches_folder(status, path):
        fail("status_folder_consistency", "frontmatter status and folder", "Keep status consistent with draft, active, or archived folder.")

    if not _supersession_schema_is_valid(frontmatter):
        fail("supersession_schema_shape", "frontmatter supersession metadata", "Use valid { ours, theirs } pairs under atomic_decisions.")

    if _has_unclosed_fence(body):
        fail("markdown_damage_blocks_review", str(path), "Close fenced code blocks so section headings remain reviewable.")

    reviewable_body = _strip_closed_fenced_blocks(body)

    heading_result = _required_headings_in_order(reviewable_body)
    if not heading_result:
        fail("required_body_headings_and_order", "body headings", "Use ## Background, ## Atomic Decisions, then ## Rationale in order.")

    atomic_lines = _atomic_section_lines(reviewable_body)
    decisions = _parse_atomic_decisions(atomic_lines)
    if not decisions:
        fail("parseable_atomic_decision_bullets", "## Atomic Decisions", "Use bullets shaped like - **a.** Decision text.")
    elif any(item["malformed"] for item in decisions):
        fail("parseable_atomic_decision_bullets", "## Atomic Decisions", "Use bullets shaped like - **a.** Decision text.")

    ids = [item["id"] for item in decisions if item["id"] is not None]
    if any(not _legal_atomic_decision_id(item) for item in ids):
        fail("legal_atomic_decision_ids", "## Atomic Decisions", "Use stable alphabetic decision ids such as a, b, or aa.")
    if len(ids) != len(set(ids)):
        fail("unique_atomic_decision_ids", "## Atomic Decisions", "Use each atomic decision id only once in the file.")

    return _structural_result(checks, findings)


def _structural_result(checks, findings):
    return {
        "gate_id": "adr_structural_reviewability_check",
        "status": "blocked" if findings else "evaluated",
        "checks": checks,
        "findings": findings,
    }


def _repeated_live_evidence_result(status, suppresses):
    finding = None
    if not suppresses:
        finding = {
            "issue": f"repeated-live supersedes evidence is not exact: {status}",
            "gate_id": "live_active_atomic_decision_repetition_check",
            "evidence_location": "frontmatter supersedes",
            "evidence_status": status,
            "why_it_matters": "Only exact durable supersedes evidence can suppress a repeated-live finding.",
            "suggested_fix": "Add a parseable supersedes mapping from this target decision to the exact still-live active decision.",
        }
    return {
        "gate_id": "live_active_atomic_decision_repetition_check",
        "status": status,
        "suppresses_repeated_live_finding": suppresses,
        "other_gates_still_apply": True,
        "finding": finding,
    }


def _adr_necessity_finding(reason, evidence_location):
    suggested_fix = {
        "easy_to_reverse_decision": "Do not create an ADR for an easy-to-reverse item.",
        "unsurprising_decision": "Do not create an ADR when the decision is obvious without extra context.",
        "no_real_tradeoff": "Do not create an ADR when no real alternative or trade-off was selected.",
        "insufficient_decision_context_value": "Do not create an ADR when the file would not preserve meaningful decision context.",
    }[reason]
    return {
        "issue": f"ADR is not justified: {reason}",
        "gate_id": "adr_necessity_of_existence_check",
        "reason": reason,
        "evidence_location": evidence_location,
        "why_it_matters": "A target that is not an ADR candidate cannot be accepted by later prose or formatting findings.",
        "suggested_fix": suggested_fix,
    }


def _split_frontmatter(text):
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, text
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return lines[1:index], "\n".join(lines[index + 1 :])
    return None, text


def _frontmatter_scalar_values(frontmatter):
    values = {}
    for line in frontmatter:
        if line.startswith(" ") or line.startswith("-") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def _frontmatter_mapping_is_parseable(frontmatter):
    current_block_key = None
    for line in frontmatter:
        stripped = line.strip()
        if not stripped:
            continue
        if line.startswith(" "):
            if current_block_key not in {"supersedes", "superseded_by"}:
                return False
            continue
        if line.startswith("-"):
            return False
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*):(.*)", line)
        if not match:
            return False
        value = match.group(2).strip()
        if not _frontmatter_scalar_value_is_parseable(value):
            return False
        current_block_key = match.group(1) if not value else None
    return True


def _frontmatter_scalar_value_is_parseable(value):
    if ": " in value and (not value or value[0] not in {"'", '"'}):
        return False
    if not value or value[0] not in {"'", '"'}:
        return True
    return len(value) >= 2 and value[-1] == value[0]


def _frontmatter_key_block(frontmatter, key):
    match = re.search(
        rf"(?ms)^{re.escape(key)}:(?:\n(?P<body>.*?))?(?=^[A-Za-z_][A-Za-z0-9_]*:|\Z)",
        "\n".join(frontmatter),
    )
    return "" if match and match.group("body") is None else match.group("body") if match else None


def _supersedes_pairs(block):
    pairs = []
    for entry_match in re.finditer(r"(?ms)^\s*-\s+adr:\s*(?P<adr>.+?)\n(?P<body>.*?)(?=^\s*-\s+adr:|\Z)", block):
        adr = entry_match.group("adr").strip()
        parsed_pairs = []
        for line in entry_match.group("body").splitlines():
            stripped = line.strip()
            if stripped.startswith("- {"):
                parsed_pairs.append(parse_inline_pair(stripped))
        for pair in expand_atomic_decision_pairs(parsed_pairs, block_key="supersedes"):
            pairs.append(
                {
                    "adr": adr,
                    "ours": pair["ours"],
                    "theirs": pair["theirs"],
                }
            )
    return pairs


def _adr_reference_matches_live(adr_ref, live_adr, live_adr_number):
    if adr_ref == live_adr:
        return True
    return bool(is_adr_id(adr_ref) and adr_ref == live_adr_number)


def _status_matches_folder(status, path):
    lifecycle_folder = _adr_lifecycle_folder(path)
    if lifecycle_folder == "draft":
        return status == "not_implemented_yet"
    if lifecycle_folder == "active":
        return status in {"fully_ground_truth", "partially_superseded"}
    if lifecycle_folder == "archived":
        return status == "fully_superseded"
    return False


def _adr_lifecycle_folder(path):
    parts = path.parts
    lifecycle_folder = None
    for index in range(len(parts) - 2):
        if parts[index] == "docs" and parts[index + 1] == "adr" and parts[index + 2] in {"draft", "active", "archived"}:
            lifecycle_folder = parts[index + 2]
    return lifecycle_folder


def _supersession_schema_is_valid(frontmatter):
    index = 0
    while index < len(frontmatter):
        line = frontmatter[index]
        stripped = line.strip()
        key_match = re.fullmatch(r"(supersedes|superseded_by):(.*)", stripped)
        if line.startswith((" ", "-")) or not key_match:
            index += 1
            continue
        block_key = key_match.group(1)
        if key_match.group(2).strip():
            return False
        index += 1
        saw_entry = False
        while index < len(frontmatter):
            current = frontmatter[index]
            current_stripped = current.strip()
            if current and not current.startswith((" ", "-")):
                break
            if current_stripped.startswith("- adr:"):
                if not current_stripped.split(":", 1)[1].strip():
                    return False
                saw_entry = True
                index += 1
                saw_atomic_decisions = False
                saw_pair = False
                while index < len(frontmatter):
                    entry_line = frontmatter[index]
                    entry_stripped = entry_line.strip()
                    if entry_line and not entry_line.startswith((" ", "-")):
                        break
                    if entry_stripped.startswith("- adr:"):
                        break
                    if entry_stripped == "atomic_decisions:":
                        saw_atomic_decisions = True
                    elif entry_stripped.startswith("- {"):
                        if not saw_atomic_decisions or not _inline_pair_is_valid(entry_stripped, block_key):
                            return False
                        saw_pair = True
                    elif entry_stripped:
                        return False
                    index += 1
                if not saw_atomic_decisions or not saw_pair:
                    return False
                continue
            if current_stripped:
                return False
            index += 1
        if not saw_entry:
            return False
    return True


def _inline_pair_is_valid(line, block_key):
    try:
        pair = parse_inline_pair(line)
    except ValueError:
        return False
    return supersession_pairs_are_valid([pair], block_key=block_key)


def _has_unclosed_fence(body):
    return sum(1 for line in body.splitlines() if line.strip().startswith("```")) % 2 == 1


def _strip_closed_fenced_blocks(body):
    output = []
    in_fence = False
    for line in body.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            output.append(line)
    return "\n".join(output)


def _required_headings_in_order(body):
    expected = ["## Background", "## Atomic Decisions", "## Rationale"]
    headings = [line.strip() for line in body.splitlines() if line.startswith("## ")]
    return headings == expected


def _atomic_section_lines(body):
    lines = body.splitlines()
    output = []
    in_section = False
    for line in lines:
        if line.strip() == "## Atomic Decisions":
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if in_section:
            output.append(line)
    return output


def _parse_atomic_decisions(lines):
    decisions = []
    bullet_seen = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if line.startswith("- "):
            bullet_seen = True
            match = re.match(r"^-\s+\*\*([^.*]+)\.\*\*\s+(.+)$", line)
            decisions.append(
                {
                    "id": match.group(1) if match else None,
                    "malformed": match is None,
                }
            )
    if bullet_seen:
        return decisions
    return []


def _legal_atomic_decision_id(value):
    return bool(re.match(r"^[A-Za-z]+$", value))
