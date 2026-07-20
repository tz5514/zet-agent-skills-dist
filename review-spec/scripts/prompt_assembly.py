"""Per-run reviewer prompt assembly for review-spec.

The blind reviewer's prompt is instantiated mechanically from the
single-authority template `GATE-PROMPT.md`: this module fills the run's
placeholders (spec path, allowed document set, run directory, report path,
validation script path), prepends a per-run random integrity marker, and
writes the result into the run directory. That written file is the sole
authority for the prompt at dispatch time — the dispatching agent does no
rewriting, adding, or reordering of its content.
"""

import argparse
import json
import re
import secrets
import sys
from pathlib import Path

from report_validation import GATE_IDS, REVIEW_MODES, SEVERITIES

GATE_PROMPT_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "GATE-PROMPT.md"
REPORT_VALIDATION_SCRIPT_PATH = Path(__file__).resolve().parent / "report_validation.py"

INTEGRITY_MARKER_PREFIX = "REVIEWER PROMPT INTEGRITY MARKER"

PROMPT_FILENAME = "review-prompt.md"
REPORT_FILENAME = "review-report.json"
PRIOR_DISPOSITION_FILENAME = "prior-round-disposition.json"

# Repairer-claimed dispositions in the caller-supplied prior-round input;
# the post-fix reviewer verifies each claim against the current text.
PRIOR_DISPOSITIONS = ("fixed", "not_fixed")

_PRIOR_ITEM_TEXT_FIELDS = ("evidence_location", "issue", "note")

_PLACEHOLDER_RE = re.compile(r"\{\{[A-Z_]+\}\}")

# Template regions between these markers exist only in post-fix prompts; in
# initial mode they are stripped whole, marker lines included.
_POST_FIX_BLOCK_RE = re.compile(
    r"<!-- BEGIN POST-FIX MODE ONLY -->\n(.*?)<!-- END POST-FIX MODE ONLY -->\n",
    re.DOTALL,
)


def generate_integrity_marker():
    return secrets.token_hex(8)


def render_allowed_docs(allowed_docs):
    return "\n".join(f"  - {doc}" for doc in allowed_docs)


def _is_nonempty_str(value):
    return isinstance(value, str) and value.strip() != ""


def normalize_prior_round(data):
    """Validate caller-supplied prior-round disposition data; assign item ids.

    Each returned item keeps exactly the canonical fields and gains a stable
    positional id (``P1``…``Pn``); caller-supplied ids and extra fields are
    dropped so the id space is always assembler-owned.
    """
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list) or not items:
        raise ValueError(
            "prior-round disposition must be an object with a non-empty items list"
        )
    normalized = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"prior-round item {index} is not an object")
        if item.get("gate") not in GATE_IDS:
            raise ValueError(f"prior-round item {index} has no canonical gate")
        if item.get("severity") not in SEVERITIES:
            raise ValueError(f"prior-round item {index} has no legal severity")
        if item.get("disposition") not in PRIOR_DISPOSITIONS:
            raise ValueError(f"prior-round item {index} has no legal disposition")
        for field in _PRIOR_ITEM_TEXT_FIELDS:
            if not _is_nonempty_str(item.get(field)):
                raise ValueError(f"prior-round item {index} is missing {field}")
        normalized.append(
            {
                "id": f"P{index + 1}",
                "gate": item["gate"],
                "severity": item["severity"],
                "evidence_location": item["evidence_location"],
                "issue": item["issue"],
                "disposition": item["disposition"],
                "note": item["note"],
            }
        )
    return normalized


def render_prior_disposition(items):
    payload = json.dumps({"items": items}, ensure_ascii=False, indent=2)
    return f"```json\n{payload}\n```"


def assemble_prompt(
    template_text,
    *,
    review_mode,
    spec_path,
    allowed_docs,
    run_dir,
    report_path,
    integrity_marker,
    prior_disposition=None,
    prior_disposition_path=None,
):
    """Return the full prompt text: marker head line + instantiated template.

    ``prior_disposition`` (normalized items) and ``prior_disposition_path``
    are required in post-fix mode and forbidden in initial mode.
    """
    if review_mode not in REVIEW_MODES:
        raise ValueError(f"unknown review mode: {review_mode}")
    if review_mode == "post-fix":
        if prior_disposition is None or prior_disposition_path is None:
            raise ValueError("post-fix mode requires the prior-round disposition")
    elif prior_disposition is not None or prior_disposition_path is not None:
        raise ValueError("initial mode takes no prior-round disposition")
    substitutions = {
        "{{REVIEW_MODE}}": review_mode,
        "{{SPEC_PATH}}": str(spec_path),
        "{{ALLOWED_DOCS}}": render_allowed_docs(allowed_docs),
        "{{RUN_DIR}}": str(run_dir),
        "{{REPORT_PATH}}": str(report_path),
        "{{VALIDATION_SCRIPT_PATH}}": str(REPORT_VALIDATION_SCRIPT_PATH),
        "{{SELF_CHECK_EXTRA_ARGS}}": "",
    }
    if review_mode == "post-fix":
        substitutions["{{SELF_CHECK_EXTRA_ARGS}}"] = (
            f" --prior-disposition {prior_disposition_path}"
        )
        substitutions["{{PRIOR_ROUND_DISPOSITION}}"] = render_prior_disposition(
            prior_disposition
        )
        substitutions["{{PRIOR_DISPOSITION_PATH}}"] = str(prior_disposition_path)
        text = _POST_FIX_BLOCK_RE.sub(lambda match: match.group(1), template_text)
    else:
        text = _POST_FIX_BLOCK_RE.sub("", template_text)
    for token, value in substitutions.items():
        text = text.replace(token, value)
    leftover = _PLACEHOLDER_RE.search(text)
    if leftover:
        raise ValueError(f"unresolved placeholder: {leftover.group(0)}")
    marker_line = f"[{INTEGRITY_MARKER_PREFIX}: {integrity_marker}]"
    return f"{marker_line}\n\n{text}"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Assemble the per-run blind reviewer prompt for review-spec."
    )
    parser.add_argument("--spec", required=True, help="path of the spec under review")
    parser.add_argument(
        "--run-dir", required=True, help="run directory the prompt and report live in"
    )
    parser.add_argument(
        "--allowed-doc",
        action="append",
        default=[],
        dest="allowed_docs",
        help="one allowed document (file or directory); repeatable",
    )
    parser.add_argument("--mode", default="initial", choices=REVIEW_MODES)
    parser.add_argument(
        "--prior-round",
        help="path of the prior-round disposition JSON (post-fix mode only): "
        'an {"items": [...]} list of the prior round\'s findings, each with '
        "the repair's claimed disposition",
    )
    args = parser.parse_args(argv)

    spec_path = Path(args.spec).resolve()
    if not spec_path.is_file():
        print(f"error: spec file not found: {spec_path}", file=sys.stderr)
        return 1
    allowed_docs = [Path(doc).resolve() for doc in args.allowed_docs]
    missing = [str(doc) for doc in allowed_docs if not doc.exists()]
    if missing:
        print(f"error: allowed doc not found: {'; '.join(missing)}", file=sys.stderr)
        return 1

    if args.mode == "post-fix" and args.prior_round is None:
        print("error: post-fix mode requires --prior-round", file=sys.stderr)
        return 1
    if args.mode != "post-fix" and args.prior_round is not None:
        print(
            "error: --prior-round is only valid with --mode post-fix",
            file=sys.stderr,
        )
        return 1
    prior_disposition = None
    if args.prior_round is not None:
        try:
            prior_round_data = json.loads(
                Path(args.prior_round).read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as error:
            print(
                f"error: prior-round disposition unreadable: {error}",
                file=sys.stderr,
            )
            return 1
        try:
            prior_disposition = normalize_prior_round(prior_round_data)
        except ValueError as error:
            print(f"error: {error}", file=sys.stderr)
            return 1

    run_dir = Path(args.run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    report_path = run_dir / REPORT_FILENAME
    prior_disposition_path = None
    if prior_disposition is not None:
        prior_disposition_path = run_dir / PRIOR_DISPOSITION_FILENAME
        prior_disposition_path.write_text(
            json.dumps({"items": prior_disposition}, ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
    integrity_marker = generate_integrity_marker()
    prompt_text = assemble_prompt(
        GATE_PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8"),
        review_mode=args.mode,
        spec_path=spec_path,
        allowed_docs=[str(doc) for doc in allowed_docs],
        run_dir=run_dir,
        report_path=report_path,
        integrity_marker=integrity_marker,
        prior_disposition=prior_disposition,
        prior_disposition_path=prior_disposition_path,
    )
    prompt_path = run_dir / PROMPT_FILENAME
    prompt_path.write_text(prompt_text, encoding="utf-8")
    metadata = {
        "prompt_path": str(prompt_path),
        "report_path": str(report_path),
        "integrity_marker": integrity_marker,
        "review_mode": args.mode,
        "spec_path": str(spec_path),
    }
    if prior_disposition_path is not None:
        metadata["prior_disposition_path"] = str(prior_disposition_path)
    print(json.dumps(metadata))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
