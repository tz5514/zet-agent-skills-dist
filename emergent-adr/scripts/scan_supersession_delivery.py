"""Scanner output-file delivery contract helpers.

The scanner sub-agent writes its full ledger JSON into a run-directory output
file the main agent preassigned for that chunk, and its final reply need only
contain one fixed-format path line; every other sentence is ignored and is not a
contract violation — the contract is immune to extra prose instead of forbidding
it. The main agent extracts the path mechanically, reads the output file, and
validates it against the matching full packet, so the same ledger JSON is never
hand-transcribed a second time. Delivery failures (no extractable path line, no
readable file at the path, or a file that fails structural validation) all fold
into the existing malformed classification with its same-slot retry and
exhausted-retry awaiting_review semantics — no second error channel and no new
retry budget. The parser-failure terminal happens before the scanner has any
deliverable content, so it stays a fixed single-line inline reply and never goes
through the output file.
"""

import json
import re
import secrets
from pathlib import Path

from scan_supersession_ledger import validate_and_format
from scan_supersession_result import awaiting_review_return


SCAN_LEDGER_PATH_LINE_PREFIX = "SCAN_LEDGER_PATH:"
PARSER_FAILED_PREFIX = "PARSER_FAILED:"
_PATH_LINE_RE = re.compile(rf"(?m)^{re.escape(SCAN_LEDGER_PATH_LINE_PREFIX)}\s*(?P<path>\S.*)$")

# The scanner prompt's integrity marker: a per-dispatch random value at the
# prompt file's head that the scanner must echo in its ledger JSON. The
# scanner's mandatory first tool step only proves the tool ran; the marker echo
# proves the prompt file itself was read.
SCANNER_INTEGRITY_MARKER_PREFIX = "SCANNER PROMPT INTEGRITY MARKER"

_PROMPT_SPEC_PATH = Path(__file__).resolve().parent.parent / "SCAN-SUPERSESSION-PROMPT.md"
_TEMPLATE_RE = re.compile(r"(?ms)^```\n(?P<template>.*?)^```", re.MULTILINE)

# The `{...}` placeholders the render step instantiates — the only mutable parts
# of the verbatim template.
SCANNER_PROMPT_PLACEHOLDER_KEYS = (
    "decision packet builder",
    "trigger ADR",
    "candidate list",
    "output file",
)


def scanner_prompt_template():
    """The verbatim scanner prompt template: the single fenced block in
    SCAN-SUPERSESSION-PROMPT.md, shared by the inner scanner and the auxiliary
    complete ledger — one template, one delivery contract."""
    return _TEMPLATE_RE.search(_PROMPT_SPEC_PATH.read_text(encoding="utf-8")).group("template")


def generate_integrity_marker():
    return secrets.token_hex(8)


def render_scanner_prompt_file(*, placeholders, run_dir, chunk_index, integrity_marker=None):
    """Instantiate the verbatim template's placeholders and write one prompt
    file per chunk into the run directory, its head carrying the per-dispatch
    random integrity marker. The written file is the sole authority for the
    dispatched prompt content — the main agent never transcribes it."""
    if integrity_marker is None:
        integrity_marker = generate_integrity_marker()
    body = scanner_prompt_template()
    for key in SCANNER_PROMPT_PLACEHOLDER_KEYS:
        body = body.replace("{" + key + "}", placeholders[key])
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = run_dir / f"scanner_prompt_chunk_{chunk_index:02d}.md"
    marker_line = f"[{SCANNER_INTEGRITY_MARKER_PREFIX}: {integrity_marker}]"
    prompt_path.write_text(f"{marker_line}\n\n{body}", encoding="utf-8")
    return {"prompt_path": str(prompt_path), "integrity_marker": integrity_marker}


def scanner_bootstrap_line(prompt_path):
    """The one-line fixed bootstrap for LLM-channel dispatch. A runtime that can
    bring the prompt file content into the sub-agent through a non-LLM channel
    skips even this line and brings the content in directly."""
    return f"Read the scanner prompt file at {prompt_path} and execute exactly the instructions in it."


def ledger_path_line(ledger_path):
    """The single fixed-format line the scanner emits so the main agent can
    mechanically locate the ledger output file among any surrounding prose."""
    return f"{SCAN_LEDGER_PATH_LINE_PREFIX} {ledger_path}"


def extract_ledger_path(scanner_output):
    """Mechanically extract the ledger output-file path from a scanner reply
    that may carry extra prose. Returns the last path line's target, or None
    when no path line is present."""
    matches = _PATH_LINE_RE.findall(scanner_output)
    if not matches:
        return None
    return matches[-1].strip()


def is_parser_failed_reply(scanner_output):
    """The parser-failure terminal is a fixed single-line inline reply; the same
    text buried in prose is not the terminal."""
    stripped = scanner_output.strip()
    return stripped.startswith(PARSER_FAILED_PREFIX) and "\n" not in stripped


def preassign_chunk_ledger_paths(run_dir, chunk_count):
    """Non-overlapping run-directory output file paths, one per chunk, assigned
    by the main agent before dispatch: parallel scanners never collide, and a
    garbled path line still leaves a known place to look for the file."""
    run_dir = Path(run_dir)
    return [
        str(run_dir / f"scan_ledger_chunk_{index:02d}.json")
        for index in range(1, chunk_count + 1)
    ]


def resolve_scanner_delivery(scanner_output, *, packet, expected_integrity_marker=None):
    """Resolve one scanner reply into a validated ledger or a classified
    failure: `parser_failed` (fixed inline terminal), `malformed` (one of the
    three delivery failure states, retried within the same slot), or `valid`
    with the validated, formatted rows. With an expected integrity marker, a
    ledger that fails the marker echo fails structural validation."""
    if is_parser_failed_reply(scanner_output):
        return {"status": "parser_failed", "reply": scanner_output.strip()}
    ledger_path = extract_ledger_path(scanner_output)
    if ledger_path is None:
        return {"status": "malformed", "reason": "no_ledger_path_line"}
    path = Path(ledger_path)
    if not path.exists():
        return {
            "status": "malformed",
            "reason": "ledger_file_not_found",
            "ledger_path": ledger_path,
        }
    try:
        ledger = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {
            "status": "malformed",
            "reason": "ledger_file_unreadable",
            "ledger_path": ledger_path,
        }
    rows, issues = validate_and_format(
        ledger, packet, expected_integrity_marker=expected_integrity_marker
    )
    if issues:
        return {
            "status": "malformed",
            "reason": "ledger_structural_validation_failed",
            "ledger_path": ledger_path,
            "issues": issues,
        }
    return {"status": "valid", "ledger_path": ledger_path, "ledger": ledger, "rows": rows}


def exhausted_retry_return(packet, malformed_reasons):
    """Same-slot retries exhausted: the slot returns awaiting_review through the
    existing result helper — never a guessed semantic repair, no new budget."""
    return awaiting_review_return(packet, list(malformed_reasons), stage="scanner_delivery")
