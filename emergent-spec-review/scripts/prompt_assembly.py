"""Per-run reviewer prompt assembly for emergent-spec-review.

Each reviewer's prompt is instantiated mechanically from its axis template and
the shared-fragment authority: this module expands the common rules, fills the
run's placeholders, and writes the result into the run directory. That written
file is the sole authority for the prompt at dispatch time — the dispatching
agent does no rewriting, adding, or reordering of its content.

The conversation decisions reviewer's prompt comes from
`CONVERSATION-DECISIONS-PROMPT.md`; assembling it also delivers the caller's
conversation artifact into the run directory whole, so the reviewer reads the
conversation evidence itself rather than anything the dispatching agent
selected from it. The implementation ready reviewer's prompt comes from
`IMPLEMENTATION-READY-PROMPT.md`, and its assembly accepts no conversation
input at all — the run directory holds only the Candidate and declared
document snapshots, their mechanical identity manifest, the prompt, and the
reviewer's own output. Nothing carries the conversation or author intent.
"""

import argparse
import json
import re
import shlex
import sys
from pathlib import Path
from urllib.parse import urlsplit

from report_validation import (
    CONVERSATION_DECISIONS_ROLE,
    IMPLEMENTATION_READY_ROLE,
    REVIEW_INPUTS_MANIFEST_FILENAME,
    candidate_digest,
    conversation_asset_path,
    image_reference_path,
    read_external_input,
    review_input_digest,
)

CONVERSATION_DECISIONS_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent / "CONVERSATION-DECISIONS-PROMPT.md"
)
IMPLEMENTATION_READY_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent / "IMPLEMENTATION-READY-PROMPT.md"
)
SHARED_REVIEW_FRAGMENTS_PATH = (
    Path(__file__).resolve().parent.parent / "SHARED-REVIEW-PROMPT-FRAGMENTS.md"
)
REPORT_VALIDATION_SCRIPT_PATH = Path(__file__).resolve().parent / "report_validation.py"

CONVERSATION_DECISIONS_PROMPT_FILENAME = "conversation-decisions-prompt.md"
CONVERSATION_DECISIONS_REPORT_FILENAME = "conversation-decisions-report.json"
DELIVERED_CONVERSATION_FILENAME = "conversation.jsonl"

IMPLEMENTATION_READY_PROMPT_FILENAME = "implementation-ready-prompt.md"
IMPLEMENTATION_READY_REPORT_FILENAME = "implementation-ready-report.json"

CANDIDATE_SNAPSHOT_FILENAME = "candidate.md"
DOCUMENT_INPUTS_DIRNAME = "document-inputs"

# Everything this module ever writes into a run directory. Finding any of them
# already there means the directory belongs to a review that has been run.
RUN_ARTIFACT_FILENAMES = (
    CONVERSATION_DECISIONS_PROMPT_FILENAME,
    CONVERSATION_DECISIONS_REPORT_FILENAME,
    DELIVERED_CONVERSATION_FILENAME,
    IMPLEMENTATION_READY_PROMPT_FILENAME,
    IMPLEMENTATION_READY_REPORT_FILENAME,
    CANDIDATE_SNAPSHOT_FILENAME,
    DOCUMENT_INPUTS_DIRNAME,
    REVIEW_INPUTS_MANIFEST_FILENAME,
)

_PLACEHOLDER_RE = re.compile(r"\{\{[A-Z_]+\}\}")
SHARED_REVIEW_FRAGMENT_NAMES = (
    "SHARED_AUTHORITY_LOAD_FAILURE",
    "SHARED_CANDIDATE_IDENTITY",
    "SHARED_NO_REPAIR_ADVICE",
    "SHARED_SELF_CHECK_AND_HAND_BACK",
)


def render_declared_docs(declared_docs, document_snapshots=None):
    if not declared_docs:
        return "  - (none declared by the Candidate)"
    document_snapshots = document_snapshots or {}
    rendered = []
    for doc in declared_docs:
        rendered.append(f"  - {doc}")
        if doc in document_snapshots:
            rendered.append(
                f"    round snapshot: {document_snapshots[doc]} "
                "(read this exact file)"
            )
    return "\n".join(rendered)


def expand_shared_review_fragments(template_text):
    """Expand the common reviewer rules from their one authoring source."""
    source = SHARED_REVIEW_FRAGMENTS_PATH.read_text(encoding="utf-8")
    text = template_text
    for name in SHARED_REVIEW_FRAGMENT_NAMES:
        start = f"<!-- {name}:START -->"
        end = f"<!-- {name}:END -->"
        fragment = source.split(start, 1)[1].split(end, 1)[0].strip()
        text = text.replace(f"{{{{{name}}}}}", fragment)
    return text


def _instantiate(template_text, substitutions):
    text = expand_shared_review_fragments(template_text)
    for token, value in substitutions.items():
        text = text.replace(token, value)
    leftover = _PLACEHOLDER_RE.search(text)
    if leftover:
        raise ValueError(f"unresolved placeholder: {leftover.group(0)}")
    return text


def _self_check_command(
    reviewer_role,
    report_path,
    candidate_path,
    input_digest,
    *,
    conversation_artifact_path=None,
    authority_docs=(),
    allowed_docs=(),
):
    command = [
        "python3",
        str(REPORT_VALIDATION_SCRIPT_PATH),
        reviewer_role,
        str(report_path),
        "--expected-report",
        str(report_path),
        "--candidate",
        str(candidate_path),
        "--input-digest",
        input_digest,
    ]
    if conversation_artifact_path is not None:
        command += ["--conversation-artifact", str(conversation_artifact_path)]
    for authority in authority_docs:
        command += ["--authority", str(authority)]
    for allowed_doc in allowed_docs:
        command += ["--allowed-doc", str(allowed_doc)]
    return shlex.join(command)


def _read_candidate(candidate_arg):
    """Return the frozen Candidate's resolved path and its text."""
    candidate_path = Path(candidate_arg).resolve()
    if not candidate_path.is_file():
        raise ValueError(f"Candidate file not found: {candidate_path}")
    try:
        return candidate_path, candidate_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError(f"Candidate file unreadable: {error}") from error


def _spent_run_artifacts(run_dir):
    """Return every entry already present in ``run_dir``.

    A reviewer's run directory is the one place it may write, so it is a place
    it reads. Every round freezes its own Candidate and dispatches reviewers
    that must reach it clean. Prompts let reviewers make arbitrarily named
    scratch files, so a filename allowlist cannot prove that a directory is
    fresh. Each round therefore assembles into an empty directory.
    """
    if not run_dir.exists():
        return []
    if not run_dir.is_dir():
        return [str(run_dir)]
    return [
        str(path)
        for path in sorted(run_dir.iterdir(), key=lambda path: path.name)
    ]


def _reject_spent_run_dir(run_dir):
    """Print why ``run_dir`` cannot host a new round, or return False."""
    spent = _spent_run_artifacts(run_dir)
    if not spent:
        return False
    print(
        "error: run directory already holds an earlier review's artifacts, so "
        f"this round assembles into a new one: {'; '.join(spent)}",
        file=sys.stderr,
    )
    return True


def _resolve_declared_docs(doc_args, noun):
    """Return the local paths and external URLs the Candidate declares.

    ``noun`` names them the way the reviewer's own prompt does, so a missing
    local file is reported in the vocabulary of the round that asked for it.
    HTTP(S) references remain URLs for the reviewer to verify with its
    available read-only retrieval tools.
    """
    docs = []
    missing = []
    for doc in doc_args:
        parsed = urlsplit(doc)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            docs.append(doc)
            continue
        path = Path(doc).resolve()
        docs.append(path)
        if not path.exists():
            missing.append(str(path))
    if missing:
        raise ValueError(f"{noun} not found: {'; '.join(missing)}")
    return docs


def _write_bytes(destination, content):
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)


def _write_new_bytes(destination, content):
    """Write to a path no run file occupies yet, letting the destination
    filesystem judge equivalence: a name that aliases an existing file there
    (case folding, Unicode normalization) fails with ``FileExistsError``
    instead of overwriting round evidence."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with open(destination, "xb") as stream:
        stream.write(content)


def _snapshot_declared_docs(declared_docs, run_dir):
    """Materialize the exact declared-document bytes a reviewer reads."""
    snapshots = {}
    for index, doc in enumerate(dict.fromkeys(declared_docs), start=1):
        parsed = urlsplit(doc)
        snapshot_root = run_dir / DOCUMENT_INPUTS_DIRNAME
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            content = read_external_input(doc)
            suffix = Path(parsed.path).suffix.lower()
            if not re.fullmatch(r"\.[a-z0-9]{1,10}", suffix):
                suffix = ".bin"
            snapshot = snapshot_root / f"{index:04d}{suffix}"
            _write_bytes(snapshot, content)
        else:
            source = Path(doc).resolve()
            if source.is_file():
                suffix = source.suffix.lower()
                if not re.fullmatch(r"\.[a-z0-9]{1,10}", suffix):
                    suffix = ".bin"
                snapshot = snapshot_root / f"{index:04d}{suffix}"
                try:
                    _write_bytes(snapshot, source.read_bytes())
                except OSError as error:
                    raise ValueError(
                        f"declared review input is unreadable: {source}"
                    ) from error
            elif source.is_dir():
                snapshot = snapshot_root / f"{index:04d}"
                snapshot.mkdir(parents=True, exist_ok=True)
                try:
                    children = sorted(item for item in source.rglob("*") if item.is_file())
                    for child in children:
                        _write_bytes(
                            snapshot / child.relative_to(source), child.read_bytes()
                        )
                except OSError as error:
                    raise ValueError(
                        f"declared review input is unreadable: {source}"
                    ) from error
            else:
                raise ValueError(f"declared review input is unreadable: {source}")
        snapshots[doc] = str(snapshot)
    return snapshots


def _write_review_inputs_manifest(
    run_dir,
    *,
    candidate_path,
    candidate_snapshot_path,
    conversation_artifact_path,
    delivered_images=(),
    declared_docs,
    document_snapshots,
    input_digest,
):
    manifest_path = run_dir / REVIEW_INPUTS_MANIFEST_FILENAME
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "candidate": {
                    "reference": str(candidate_path),
                    "snapshot": str(candidate_snapshot_path),
                },
                "conversation_artifact": (
                    str(Path(conversation_artifact_path).resolve())
                    if conversation_artifact_path is not None
                    else None
                ),
                "delivered_images": list(delivered_images),
                "documents": [
                    {
                        "reference": doc,
                        "snapshot": document_snapshots[doc],
                    }
                    for doc in declared_docs
                ],
                "input_digest": input_digest,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return manifest_path


# ---------------------------------------------------------------------------
# conversation decisions reviewer prompt
# ---------------------------------------------------------------------------


def deliver_conversation(conversation_artifact_path, delivered_path):
    """Deliver the caller's conversation artifact into the run directory.

    The caller owns the conversation: what the artifact contains, which
    record types appear, and where the evidence ends are its selection, made
    before this call. Delivery therefore hands the reviewer the artifact
    whole — every record, in the caller's order, byte-identical so the line
    numbers a reviewer cites stay honest — and never filters by record type,
    looks for an endpoint, or checks who produced the file. What it does
    check is that the primary input can be delivered at all: a file that is
    missing, unreadable, or not JSONL record objects fails here, before
    dispatch, as an undeliverable input rather than a judgment about the
    conversation itself.

    Image assets referenced by the records are best-effort evidence, not a
    delivery precondition. A reference that names a normalized relative
    path, stays inside the artifact's directory, does not collide with a run
    artifact, and reads successfully is copied beneath the delivered
    artifact at the same relative path, so the reviewer finds it from the
    record alone. Any other reference is skipped and reported in the
    returned ``skipped_images``: an unavailable image narrows the evidence,
    never the round.
    """
    source = Path(conversation_artifact_path)
    try:
        artifact_bytes = source.read_bytes()
        text = artifact_bytes.decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError(f"conversation artifact is unreadable: {source}") from error
    records = []
    for number, line in enumerate(text.splitlines(), start=1):
        try:
            record = json.loads(line)
        except ValueError as error:
            raise ValueError(
                f"conversation artifact is not valid JSONL at line {number}: {source}"
            ) from error
        if not isinstance(record, dict):
            raise ValueError(
                f"conversation artifact line {number} is not a record object: {source}"
            )
        records.append(record)
    delivered = Path(delivered_path)
    delivered_assets = []
    delivered_images = []
    skipped_images = []
    seen_references = set()
    source_root = source.parent.resolve()
    delivered_root = delivered.parent.resolve()
    for record in records:
        images = record.get("images", [])
        if not isinstance(images, list):
            skipped_images.append({"path": None, "reason": "images is not a list"})
            continue
        for image in images:
            raw_reference = image.get("path") if isinstance(image, dict) else None
            reference = raw_reference if isinstance(raw_reference, str) else None
            relative_path = image_reference_path(reference)
            if relative_path is None:
                skipped_images.append(
                    {
                        "path": reference,
                        "reason": "not a normalized relative image reference",
                    }
                )
                continue
            # Deduplicate by the normalized path, so two spellings of one
            # reference cannot deliver the same asset twice or bind it twice.
            if relative_path in seen_references:
                continue
            seen_references.add(relative_path)
            # A normalized path could still name a file this module writes
            # (the delivered conversation, the prompt, the report, ...), and
            # copying it there would replace round evidence with image bytes.
            if relative_path.parts[0] in RUN_ARTIFACT_FILENAMES:
                skipped_images.append(
                    {"path": reference, "reason": "collides with a run artifact"}
                )
                continue
            source_asset = conversation_asset_path(source_root, relative_path)
            if source_asset is None:
                skipped_images.append(
                    {
                        "path": reference,
                        "reason": "escapes the conversation artifact directory",
                    }
                )
                continue
            try:
                asset_bytes = source_asset.read_bytes()
            except OSError:
                skipped_images.append(
                    {"path": reference, "reason": "missing or unreadable"}
                )
                continue
            delivered_assets.append(
                (reference, asset_bytes, delivered_root / relative_path)
            )
    delivered.parent.mkdir(parents=True, exist_ok=True)
    delivered.write_bytes(artifact_bytes)
    for reference, asset_bytes, delivered_asset in delivered_assets:
        # The string check above cannot see filesystem aliases (a
        # case-insensitive volume maps `Conversation.jsonl` onto the
        # delivered conversation), so the write itself must refuse to
        # replace any file already in the run directory.
        try:
            _write_new_bytes(delivered_asset, asset_bytes)
        except FileExistsError:
            skipped_images.append(
                {"path": reference, "reason": "collides with a run artifact"}
            )
            continue
        delivered_images.append(reference)
    return {
        "conversation_artifact_path": str(delivered),
        "line_count": len(records),
        "delivered_images": delivered_images,
        "skipped_images": skipped_images,
    }


def assemble_conversation_decisions_prompt(
    template_text,
    *,
    candidate_path,
    candidate_snapshot_path=None,
    digest,
    input_digest,
    conversation_artifact_path,
    authority_docs,
    document_snapshots=None,
    run_dir,
    report_path,
):
    """Return the instantiated conversation decisions reviewer prompt.

    No per-run token is prepended: this round's identity is the Candidate
    digest, which is derived from the reviewed text itself and therefore
    cannot be carried over to a different one.
    """
    return _instantiate(
        template_text,
        {
            "{{CANDIDATE_PATH}}": str(candidate_path),
            "{{CANDIDATE_SNAPSHOT_PATH}}": str(
                candidate_snapshot_path or candidate_path
            ),
            "{{CANDIDATE_DIGEST}}": digest,
            "{{INPUT_DIGEST}}": input_digest,
            "{{CONVERSATION_ARTIFACT_PATH}}": str(conversation_artifact_path),
            "{{AUTHORITY_DOCS}}": render_declared_docs(
                authority_docs, document_snapshots
            ),
            "{{RUN_DIR}}": str(run_dir),
            "{{REPORT_PATH}}": str(report_path),
            "{{SELF_CHECK_COMMAND}}": _self_check_command(
                CONVERSATION_DECISIONS_ROLE,
                report_path,
                candidate_path,
                input_digest,
                conversation_artifact_path=conversation_artifact_path,
                authority_docs=authority_docs,
            ),
        },
    )


def _assemble_conversation_decisions_round(argv):
    parser = argparse.ArgumentParser(
        prog=f"prompt_assembly.py {CONVERSATION_DECISIONS_ROLE}",
        description="Assemble the conversation decisions reviewer prompt and "
        "deliver its conversation for one frozen Candidate.",
    )
    parser.add_argument(
        "--candidate", required=True, help="path of the frozen Candidate under review"
    )
    parser.add_argument(
        "--run-dir",
        required=True,
        help="run directory the prompt, delivered conversation, and report live in",
    )
    parser.add_argument(
        "--conversation",
        required=True,
        help="path of the caller-prepared JSONL artifact holding this "
        "round's complete conversation evidence",
    )
    parser.add_argument(
        "--authority",
        action="append",
        default=[],
        dest="authority_docs",
        help="one authority the Candidate declares (local path or HTTP(S) URL); "
        "repeatable",
    )
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir).resolve()
    if _reject_spent_run_dir(run_dir):
        return 1
    try:
        candidate_path, candidate_text = _read_candidate(args.candidate)
        authority_docs = _resolve_declared_docs(
            args.authority_docs, "authority document"
        )
        delivery = deliver_conversation(
            args.conversation, run_dir / DELIVERED_CONVERSATION_FILENAME
        )
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    for skipped_image in delivery["skipped_images"]:
        print(
            "note: conversation image skipped "
            f"({skipped_image['reason']}): {skipped_image['path']}",
            file=sys.stderr,
        )
    digest = candidate_digest(candidate_text)
    candidate_snapshot_path = run_dir / CANDIDATE_SNAPSHOT_FILENAME
    _write_bytes(candidate_snapshot_path, candidate_text.encode("utf-8"))
    authority_doc_strings = [str(doc) for doc in authority_docs]
    try:
        document_snapshots = _snapshot_declared_docs(
            authority_doc_strings, run_dir
        )
        input_digest = review_input_digest(
            digest,
            conversation_artifact_path=delivery["conversation_artifact_path"],
            delivered_images=delivery["delivered_images"],
            declared_docs=authority_doc_strings,
            document_snapshots=document_snapshots,
        )
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    report_path = run_dir / CONVERSATION_DECISIONS_REPORT_FILENAME
    prompt_path = run_dir / CONVERSATION_DECISIONS_PROMPT_FILENAME
    input_manifest_path = _write_review_inputs_manifest(
        run_dir,
        candidate_path=candidate_path,
        candidate_snapshot_path=candidate_snapshot_path,
        conversation_artifact_path=delivery["conversation_artifact_path"],
        delivered_images=delivery["delivered_images"],
        declared_docs=authority_doc_strings,
        document_snapshots=document_snapshots,
        input_digest=input_digest,
    )
    prompt_path.write_text(
        assemble_conversation_decisions_prompt(
            CONVERSATION_DECISIONS_TEMPLATE_PATH.read_text(encoding="utf-8"),
            candidate_path=candidate_path,
            candidate_snapshot_path=candidate_snapshot_path,
            digest=digest,
            input_digest=input_digest,
            conversation_artifact_path=delivery["conversation_artifact_path"],
            authority_docs=authority_doc_strings,
            document_snapshots=document_snapshots,
            run_dir=run_dir,
            report_path=report_path,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "reviewer_role": CONVERSATION_DECISIONS_ROLE,
                "prompt_path": str(prompt_path),
                "report_path": str(report_path),
                "candidate_path": str(candidate_path),
                "candidate_snapshot_path": str(candidate_snapshot_path),
                "candidate_digest": digest,
                "input_digest": input_digest,
                "conversation_artifact_path": delivery["conversation_artifact_path"],
                "conversation_line_count": delivery["line_count"],
                "delivered_images": delivery["delivered_images"],
                "skipped_images": delivery["skipped_images"],
                "authority_docs": authority_doc_strings,
                "document_snapshots": document_snapshots,
                "input_manifest_path": str(input_manifest_path),
            }
        )
    )
    return 0


# ---------------------------------------------------------------------------
# implementation ready reviewer prompt
# ---------------------------------------------------------------------------


def assemble_implementation_ready_prompt(
    template_text,
    *,
    candidate_path,
    candidate_snapshot_path=None,
    digest,
    input_digest,
    allowed_docs,
    document_snapshots=None,
    run_dir,
    report_path,
):
    """Return the instantiated implementation ready reviewer prompt.

    Like the conversation decisions prompt, the round's identity is the
    Candidate digest rather than a per-run token. The substitutions are the
    whole of what this reviewer is told: the Candidate, the documents it
    declares an implementer may rely on, and where to write.
    """
    return _instantiate(
        template_text,
        {
            "{{CANDIDATE_PATH}}": str(candidate_path),
            "{{CANDIDATE_SNAPSHOT_PATH}}": str(
                candidate_snapshot_path or candidate_path
            ),
            "{{CANDIDATE_DIGEST}}": digest,
            "{{INPUT_DIGEST}}": input_digest,
            "{{ALLOWED_DOCS}}": render_declared_docs(
                allowed_docs, document_snapshots
            ),
            "{{RUN_DIR}}": str(run_dir),
            "{{REPORT_PATH}}": str(report_path),
            "{{SELF_CHECK_COMMAND}}": _self_check_command(
                IMPLEMENTATION_READY_ROLE,
                report_path,
                candidate_path,
                input_digest,
                allowed_docs=allowed_docs,
            ),
        },
    )


def _assemble_implementation_ready_round(argv):
    parser = argparse.ArgumentParser(
        prog=f"prompt_assembly.py {IMPLEMENTATION_READY_ROLE}",
        description="Assemble the implementation ready reviewer prompt for one "
        "frozen Candidate.",
    )
    parser.add_argument(
        "--candidate", required=True, help="path of the frozen Candidate under review"
    )
    parser.add_argument(
        "--run-dir",
        required=True,
        help="run directory the prompt and report live in",
    )
    parser.add_argument(
        "--allowed-doc",
        action="append",
        default=[],
        dest="allowed_docs",
        help="one document the Candidate declares an implementer may rely on "
        "(local path or HTTP(S) URL); repeatable",
    )
    args = parser.parse_args(argv)

    try:
        candidate_path, candidate_text = _read_candidate(args.candidate)
        allowed_docs = _resolve_declared_docs(args.allowed_docs, "allowed document")
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    run_dir = Path(args.run_dir).resolve()
    # A conversation delivered into this directory is named on its own, ahead
    # of the general freshness check: whoever it was delivered for, this
    # reviewer must never be able to read one, and the directory is the one
    # place it may write and therefore reads.
    delivered_conversation = run_dir / DELIVERED_CONVERSATION_FILENAME
    if delivered_conversation.exists():
        print(
            "error: run directory already holds a delivered conversation, which "
            f"this reviewer must not be able to read: {delivered_conversation}",
            file=sys.stderr,
        )
        return 1
    if _reject_spent_run_dir(run_dir):
        return 1
    run_dir.mkdir(parents=True, exist_ok=True)
    digest = candidate_digest(candidate_text)
    candidate_snapshot_path = run_dir / CANDIDATE_SNAPSHOT_FILENAME
    _write_bytes(candidate_snapshot_path, candidate_text.encode("utf-8"))
    allowed_doc_strings = [str(doc) for doc in allowed_docs]
    try:
        document_snapshots = _snapshot_declared_docs(
            allowed_doc_strings, run_dir
        )
        input_digest = review_input_digest(
            digest,
            declared_docs=allowed_doc_strings,
            document_snapshots=document_snapshots,
        )
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    report_path = run_dir / IMPLEMENTATION_READY_REPORT_FILENAME
    prompt_path = run_dir / IMPLEMENTATION_READY_PROMPT_FILENAME
    input_manifest_path = _write_review_inputs_manifest(
        run_dir,
        candidate_path=candidate_path,
        candidate_snapshot_path=candidate_snapshot_path,
        conversation_artifact_path=None,
        declared_docs=allowed_doc_strings,
        document_snapshots=document_snapshots,
        input_digest=input_digest,
    )
    prompt_path.write_text(
        assemble_implementation_ready_prompt(
            IMPLEMENTATION_READY_TEMPLATE_PATH.read_text(encoding="utf-8"),
            candidate_path=candidate_path,
            candidate_snapshot_path=candidate_snapshot_path,
            digest=digest,
            input_digest=input_digest,
            allowed_docs=allowed_doc_strings,
            document_snapshots=document_snapshots,
            run_dir=run_dir,
            report_path=report_path,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "reviewer_role": IMPLEMENTATION_READY_ROLE,
                "prompt_path": str(prompt_path),
                "report_path": str(report_path),
                "candidate_path": str(candidate_path),
                "candidate_snapshot_path": str(candidate_snapshot_path),
                "candidate_digest": digest,
                "input_digest": input_digest,
                "allowed_docs": allowed_doc_strings,
                "document_snapshots": document_snapshots,
                "input_manifest_path": str(input_manifest_path),
            }
        )
    )
    return 0


def main(argv):
    """Assemble one reviewer prompt; the leading role token selects which."""
    if argv[:1] == [CONVERSATION_DECISIONS_ROLE]:
        return _assemble_conversation_decisions_round(argv[1:])
    if argv[:1] == [IMPLEMENTATION_READY_ROLE]:
        return _assemble_implementation_ready_round(argv[1:])
    print(
        f"error: expected {CONVERSATION_DECISIONS_ROLE} or "
        f"{IMPLEMENTATION_READY_ROLE} as the first argument",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
