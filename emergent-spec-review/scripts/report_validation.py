"""Mechanical validation of an emergent-spec-review review round.

A review round's output is only usable after two mechanical checks: the report
path is extracted from the reviewer's reply by a fixed rule (never by the main
agent's judgement), and the report file passes structural validation. Any
violation makes the round invalid; an invalid round's findings must not be
consumed, and a round without a valid report is never read as zero findings.

Both reviewers report into one shared envelope, validated here: it names the
reviewer role that produced it, the exact Candidate text it reviewed, and the
inputs that reviewer was given. Because the envelope is closed, an input one
reviewer holds and the other must not has no slot in the other's report.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


REVIEW_INPUTS_MANIFEST_FILENAME = "review-inputs.json"
REVIEW_INPUTS_MANIFEST_FIELDS = {
    "schema_version",
    "candidate",
    "conversation_artifact",
    "delivered_images",
    "documents",
    "input_digest",
}


def _is_nonempty_str(value):
    return isinstance(value, str) and value.strip() != ""


def image_reference_path(reference):
    """Return the normalized relative path an image reference names, or None.

    A reference that is not a string, is empty, is absolute, or climbs with
    ``..`` cannot name an asset beneath the conversation artifact, so it
    resolves to nothing here rather than raising — one image's deliverability
    is never allowed to fail anything larger than that image.
    """
    if not isinstance(reference, str):
        return None
    relative_path = Path(reference)
    if (
        not relative_path.parts
        or relative_path.is_absolute()
        or ".." in relative_path.parts
    ):
        return None
    return relative_path


def conversation_asset_path(root, relative_path):
    """Return the asset path under ``root``, or None when it escapes.

    The containment check runs on the resolved path, so a symlink that leaves
    ``root`` yields None — and the target is never read.
    """
    resolved_root = Path(root).resolve()
    asset_path = (resolved_root / relative_path).resolve()
    try:
        asset_path.relative_to(resolved_root)
    except ValueError:
        return None
    return asset_path


# The one fixed-format line the reviewer's outward reply must carry.
REPORT_PATH_LINE_PREFIX = "REVIEW_REPORT_PATH:"
_REPORT_PATH_LINE_RE = re.compile(
    rf"^{re.escape(REPORT_PATH_LINE_PREFIX)}\s*(.+?)\s*$", re.MULTILINE
)


def extract_report_path(reply_text):
    """Mechanically extract the report path from the reviewer's reply text.

    Returns the path from the last `REVIEW_REPORT_PATH:` line, or ``None`` when
    no such line exists (which makes the round invalid).
    """
    matches = _REPORT_PATH_LINE_RE.findall(reply_text)
    return matches[-1] if matches else None


# ---------------------------------------------------------------------------
# the blocker-only reviewer envelope
# ---------------------------------------------------------------------------

COMPLETED_CLOSE_STATUS = "completed"
BLOCKER_ONLY_CLOSE_STATUSES = (COMPLETED_CLOSE_STATUS, "tool_failed")

# A reviewer's whole reply when it could not load the philosophy authority: no
# report exists then, so the round fails closed instead of passing on a review
# made from memory.
AUTHORITY_LOAD_FAILURE_LINE_PREFIX = "REVIEW_AUTHORITY_LOAD_FAILURE:"
_AUTHORITY_LOAD_FAILURE_LINE_RE = re.compile(
    rf"^{re.escape(AUTHORITY_LOAD_FAILURE_LINE_PREFIX)}\s*(.+?)\s*$", re.MULTILINE
)

# The report and its findings are closed shapes: a key outside these sets is a
# violation, so a graded severity or reviewer-authored repair advice has no
# legal slot to arrive in and no consumer can grow a branch that reads one.
# Each reviewer widens the report set by the inputs it was given, and by those
# alone — which is what leaves another reviewer's inputs nowhere to land.
_BLOCKER_ONLY_REPORT_FIELDS = (
    "reviewer_role",
    "candidate_path",
    "candidate_digest",
    "input_digest",
    "findings",
    "check_conclusions",
    "reviewer_close_status",
)
_BLOCKER_FINDING_TEXT_FIELDS = ("candidate_location", "issue", "failure_scenario")
_BLOCKER_FINDING_FIELDS = ("check", *_BLOCKER_FINDING_TEXT_FIELDS, "evidence")


def candidate_digest(candidate_text):
    """Return the Candidate's identity, derived from its own text.

    Deriving identity from content rather than issuing a per-round token is
    what makes a report self-invalidating: a report written against different
    Candidate bytes cannot match, so no report survives an edit to the text it
    reviewed. It is also what proves the two axes reviewed one version — equal
    digests could not have come from different texts.
    """
    return hashlib.sha256(candidate_text.encode("utf-8")).hexdigest()


def _read_file_digest(path):
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise ValueError(f"review input is unreadable: {path}") from error


def read_external_input(reference):
    """Fetch one declared HTTP(S) input using the review identity client."""
    request = Request(
        reference,
        headers={"User-Agent": "zet-agent-skills/emergent-spec-review-input-identity"},
    )
    chunks = []
    try:
        with urlopen(request, timeout=30) as response:
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                chunks.append(chunk)
    except (OSError, ValueError) as error:
        raise ValueError(
            f"external review input is unreadable: {reference}"
        ) from error
    return b"".join(chunks)


def _directory_identity(path):
    files = []
    for child in sorted(item for item in path.rglob("*") if item.is_file()):
        files.append(
            {
                "path": child.relative_to(path).as_posix(),
                "sha256": _read_file_digest(child),
            }
        )
    return files


def _document_identity(
    reference, external_content_digests, document_snapshots
):
    parsed = urlsplit(reference)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        snapshot = document_snapshots.get(reference)
        if snapshot is not None:
            snapshot_path = Path(snapshot).resolve()
            if not snapshot_path.is_file():
                raise ValueError(f"review input is unreadable: {snapshot_path}")
            digest = _read_file_digest(snapshot_path)
        else:
            digest = external_content_digests.get(reference)
            if digest is None:
                digest = hashlib.sha256(read_external_input(reference)).hexdigest()
        return {
            "reference": reference,
            "kind": "external_url",
            "sha256": digest,
        }
    path = Path(reference).resolve()
    identity_path = Path(document_snapshots.get(reference, path)).resolve()
    if identity_path.is_file():
        return {
            "reference": str(path),
            "kind": "file",
            "sha256": _read_file_digest(identity_path),
        }
    if identity_path.is_dir():
        return {
            "reference": str(path),
            "kind": "directory",
            "files": _directory_identity(identity_path),
        }
    raise ValueError(f"review input is unreadable: {identity_path}")


class ConversationEvidence:
    """The conversation half of a round's reviewer inputs, moving as one value:
    the caller's artifact plus the image references delivery actually handed
    over. Its invariants live here — images cannot exist without the
    conversation, and every image identity is hashed beneath the artifact's
    own root.

    The images bound here are the ones delivery actually handed over, passed
    in rather than re-derived from the artifact's records: an undeliverable
    reference is skipped at delivery, so hashing every reference the records
    carry would fail the identity on inputs the round legitimately proceeded
    without.
    """

    def __init__(self, artifact_path, delivered_images=()):
        if artifact_path is None and delivered_images:
            raise ValueError(
                "delivered images cannot exist without a conversation artifact"
            )
        self.artifact_path = artifact_path
        self.delivered_images = tuple(delivered_images)

    def identity(self):
        """Return the artifact-plus-images identity, or ``None`` when the
        round has no conversation input."""
        if self.artifact_path is None:
            return None
        path = Path(self.artifact_path).resolve()
        try:
            artifact_bytes = path.read_bytes()
            lines = artifact_bytes.decode("utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as error:
            raise ValueError(f"review input is unreadable: {path}") from error
        for number, line in enumerate(lines, start=1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"review conversation is invalid JSONL at line {number}: {path}"
                ) from error
            if not isinstance(record, dict):
                raise ValueError(
                    f"review conversation line {number} is not an object: {path}"
                )
        assets = []
        for image in sorted(set(self.delivered_images)):
            relative_path = image_reference_path(image)
            if relative_path is None:
                raise ValueError(
                    "review conversation image path must be a normalized "
                    f"relative path: {image!r}"
                )
            asset_path = conversation_asset_path(path.parent, relative_path)
            if asset_path is None:
                raise ValueError(
                    "review conversation image path escapes its input root: "
                    f"{image!r}"
                )
            assets.append({"path": image, "sha256": _read_file_digest(asset_path)})
        return {
            "reference": str(path),
            "sha256": hashlib.sha256(artifact_bytes).hexdigest(),
            "assets": assets,
        }


def review_input_digest(
    candidate_digest_value,
    *,
    conversation_artifact_path=None,
    delivered_images=(),
    declared_docs=(),
    external_content_digests=None,
    document_snapshots=None,
):
    """Return a content identity for the formal inputs assembled for one reviewer.

    ``delivered_images`` names the image references delivered with the
    conversation; each is hashed beneath the artifact's own directory, so the
    identity covers exactly the images the reviewer was handed.
    """
    identity = {
        "candidate_digest": candidate_digest_value,
        "conversation": ConversationEvidence(
            conversation_artifact_path, delivered_images
        ).identity(),
        "declared_docs": [
            _document_identity(
                doc,
                external_content_digests or {},
                document_snapshots or {},
            )
            for doc in declared_docs
        ],
    }
    encoded = json.dumps(
        identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _resolved_within(path, root):
    resolved = Path(path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError(
            f"round input snapshot escapes its run directory: {resolved}"
        ) from error
    return resolved


def _load_round_input_manifest(
    expected_report_path,
    *,
    candidate_path,
    conversation_artifact_path,
    declared_docs,
    input_digest,
):
    """Load the fixed mapping from source references to reviewer snapshots."""
    run_dir = expected_report_path.parent.resolve()
    manifest_path = run_dir / REVIEW_INPUTS_MANIFEST_FILENAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(
            f"review input manifest is unreadable: {manifest_path}"
        ) from error
    if not isinstance(manifest, dict) or set(manifest) != REVIEW_INPUTS_MANIFEST_FIELDS:
        raise ValueError(f"review input manifest has an invalid shape: {manifest_path}")
    candidate = manifest.get("candidate")
    if (
        manifest.get("schema_version") != 1
        or manifest.get("input_digest") != input_digest
        or not isinstance(candidate, dict)
        or set(candidate) != {"reference", "snapshot"}
        or candidate.get("reference") != str(candidate_path)
        or not _is_nonempty_str(candidate.get("snapshot"))
    ):
        raise ValueError(
            f"review input manifest does not describe this round: {manifest_path}"
        )
    expected_conversation = (
        str(Path(conversation_artifact_path).resolve())
        if conversation_artifact_path is not None
        else None
    )
    if manifest.get("conversation_artifact") != expected_conversation:
        raise ValueError(
            f"review input manifest conversation mismatch: {manifest_path}"
        )
    delivered_images = manifest.get("delivered_images")
    if not isinstance(delivered_images, list) or not all(
        _is_nonempty_str(image) for image in delivered_images
    ):
        raise ValueError(
            f"review input manifest delivered images are invalid: {manifest_path}"
        )
    try:
        ConversationEvidence(expected_conversation, delivered_images)
    except ValueError as error:
        raise ValueError(
            "review input manifest lists delivered images without a "
            f"conversation: {manifest_path}"
        ) from error
    documents = manifest.get("documents")
    if (
        not isinstance(documents, list)
        or len(documents) != len(declared_docs)
        or any(
            not isinstance(document, dict)
            or set(document) != {"reference", "snapshot"}
            or document.get("reference") != reference
            or not _is_nonempty_str(document.get("snapshot"))
            for document, reference in zip(documents, declared_docs)
        )
    ):
        raise ValueError(f"review input manifest documents mismatch: {manifest_path}")
    candidate_snapshot = _resolved_within(candidate["snapshot"], run_dir)
    document_snapshots = {}
    for document in documents:
        snapshot = _resolved_within(document["snapshot"], run_dir)
        existing = document_snapshots.get(document["reference"])
        if existing is not None and existing != str(snapshot):
            raise ValueError(
                f"review input manifest duplicates a document inconsistently: "
                f"{manifest_path}"
            )
        document_snapshots[document["reference"]] = str(snapshot)
    return candidate_snapshot, document_snapshots, delivered_images


def extract_authority_load_failure(reply_text):
    """Return the reason from the reviewer's authority-load failure line, or
    ``None`` when the reply carries no such line."""
    match = _AUTHORITY_LOAD_FAILURE_LINE_RE.search(reply_text)
    return match.group(1) if match else None


def _validate_blocker_finding(index, finding, check_counts):
    if not isinstance(finding, dict):
        return [f"finding_not_object:{index}"]
    errors = [
        f"finding_unknown_field:{index}:{key}"
        for key in sorted(set(finding) - set(_BLOCKER_FINDING_FIELDS))
    ]
    check = finding.get("check")
    if check in check_counts:
        check_counts[check] += 1
    else:
        errors.append(f"finding_unknown_check:{index}")
    for field in _BLOCKER_FINDING_TEXT_FIELDS:
        if not _is_nonempty_str(finding.get(field)):
            errors.append(f"finding_{field}_missing:{index}")
    evidence = finding.get("evidence")
    if (
        not isinstance(evidence, list)
        or not evidence
        or not all(_is_nonempty_str(item) for item in evidence)
    ):
        errors.append(f"finding_evidence_missing:{index}")
    return errors


def _validate_blocker_only_report(
    report,
    *,
    expected_role,
    checks,
    expected_candidate_digest,
    expected_candidate_path,
    expected_input_digest,
    path_fields=(),
    document_list_fields=(),
    expected_path_fields=None,
    expected_document_list_fields=None,
):
    """Return the violations in the envelope both reviewers share.

    The report must name its own reviewer role, carry the reviewed Candidate's
    own digest, close as a completed review, and account for every check —
    each one either reporting findings or stating why it found none.

    ``path_fields`` and ``document_list_fields`` name the inputs this reviewer
    was given, as a single path and as a list of paths respectively. They are
    the only keys admitted on top of the shared set, so an input belonging to
    the other reviewer is rejected as an unknown field.
    """
    if not isinstance(report, dict):
        return ["report_not_object"]
    expected_path_fields = expected_path_fields or {}
    expected_document_list_fields = expected_document_list_fields or {}
    known_fields = {*_BLOCKER_ONLY_REPORT_FIELDS, *path_fields, *document_list_fields}
    errors = [
        f"report_unknown_field:{key}" for key in sorted(set(report) - known_fields)
    ]
    if report.get("reviewer_role") != expected_role:
        errors.append("reviewer_role_invalid")
    candidate_path = report.get("candidate_path")
    if not _is_nonempty_str(candidate_path):
        errors.append("candidate_path_missing")
    elif candidate_path != expected_candidate_path:
        errors.append("candidate_path_mismatch")
    digest = report.get("candidate_digest")
    if not _is_nonempty_str(digest):
        errors.append("candidate_digest_missing")
    elif digest != expected_candidate_digest:
        errors.append("candidate_digest_mismatch")
    input_digest = report.get("input_digest")
    if not _is_nonempty_str(input_digest):
        errors.append("input_digest_missing")
    elif input_digest != expected_input_digest:
        errors.append("input_digest_mismatch")
    for field in path_fields:
        value = report.get(field)
        if not _is_nonempty_str(value):
            errors.append(f"{field}_missing")
        elif field in expected_path_fields and value != expected_path_fields[field]:
            errors.append(f"{field}_mismatch")
    for field in document_list_fields:
        docs = report.get(field)
        if not isinstance(docs, list) or not all(_is_nonempty_str(doc) for doc in docs):
            errors.append(f"{field}_invalid")
        elif (
            field in expected_document_list_fields
            and docs != expected_document_list_fields[field]
        ):
            errors.append(f"{field}_mismatch")
    close_status = report.get("reviewer_close_status")
    if close_status not in BLOCKER_ONLY_CLOSE_STATUSES:
        errors.append("reviewer_close_status_invalid")
    elif close_status != COMPLETED_CLOSE_STATUS:
        errors.append("review_not_completed")

    check_counts = {check: 0 for check in checks}
    findings = report.get("findings")
    if not isinstance(findings, list):
        errors.append("findings_not_list")
    else:
        for index, finding in enumerate(findings):
            errors.extend(_validate_blocker_finding(index, finding, check_counts))

    conclusions = report.get("check_conclusions")
    if not isinstance(conclusions, dict):
        errors.append("check_conclusions_not_object")
        conclusions = {}
    for key, conclusion in conclusions.items():
        if key not in checks:
            errors.append(f"check_conclusions_unknown_check:{key}")
        elif not _is_nonempty_str(conclusion):
            errors.append(f"check_conclusion_invalid:{key}")
    # Silence is never a pass: a check that reported nothing must say what it
    # examined, so an unperformed check cannot look like a clean one.
    for check in checks:
        if check_counts[check] == 0 and check not in conclusions:
            errors.append(f"check_conclusion_missing:{check}")
    return errors


def _validate_blocker_only_round(
    argv,
    *,
    reviewer_role,
    validate,
    document_list_input,
    path_input=None,
):
    parser = argparse.ArgumentParser(
        prog=f"report_validation.py {reviewer_role}",
        description=f"Validate a {reviewer_role.replace('_', ' ')} review "
        "report against the Candidate it claims to have reviewed.",
    )
    parser.add_argument("report_path", nargs="?", help="path of the report JSON file")
    parser.add_argument(
        "--from-reply",
        help="path of a file holding the reviewer's reply/stdout; the report "
        "path is extracted from its REVIEW_REPORT_PATH line",
    )
    parser.add_argument(
        "--candidate",
        required=True,
        help="path of the frozen Candidate this round reviewed; its content "
        "derives the identity the report must carry",
    )
    parser.add_argument(
        "--expected-report",
        required=True,
        help="preassigned report path printed by the assembler for this round",
    )
    parser.add_argument(
        "--input-digest",
        required=True,
        help="content identity of the full reviewer input printed by the assembler",
    )
    if path_input is not None:
        option, destination, help_text = path_input
        parser.add_argument(option, dest=destination, required=True, help=help_text)
    option, destination, help_text = document_list_input
    parser.add_argument(
        option,
        dest=destination,
        action="append",
        default=[],
        help=help_text,
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
        authority_failure = extract_authority_load_failure(reply_text)
        if authority_failure is not None:
            print(f"invalid: authority_load_failure ({authority_failure})")
            return 1
        report_path = extract_report_path(reply_text)
        if report_path is None:
            print("invalid: report_path_line_missing")
            return 1

    expected_report_path = Path(args.expected_report).resolve()
    if Path(report_path).resolve() != expected_report_path:
        print("invalid: report_path_mismatch")
        return 1

    try:
        candidate_path = Path(args.candidate).resolve()
        candidate_text = candidate_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        print(f"invalid: candidate_unreadable ({error})")
        return 1
    try:
        report = json.loads(expected_report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        print(f"invalid: report_unreadable ({error})")
        return 1

    current_candidate_digest = candidate_digest(candidate_text)
    conversation_artifact_path = None
    path_destination = None
    if path_input is not None:
        _, path_destination, _ = path_input
        conversation_artifact_path = getattr(args, path_destination)
    _, document_destination, _ = document_list_input
    declared_docs = getattr(args, document_destination)
    expected_inputs = {
        "expected_candidate_digest": current_candidate_digest,
        "expected_candidate_path": str(candidate_path),
        "expected_input_digest": args.input_digest,
    }
    if path_destination is not None:
        expected_inputs[f"expected_{path_destination}"] = getattr(
            args, path_destination
        )
    expected_inputs[f"expected_{document_destination}"] = getattr(
        args, document_destination
    )
    errors = validate(report, **expected_inputs)
    if errors:
        print("invalid: " + "; ".join(errors))
        return 1
    try:
        (
            candidate_snapshot_path,
            document_snapshots,
            delivered_images,
        ) = _load_round_input_manifest(
            expected_report_path,
            candidate_path=candidate_path,
            conversation_artifact_path=conversation_artifact_path,
            declared_docs=declared_docs,
            input_digest=args.input_digest,
        )
        candidate_snapshot_text = candidate_snapshot_path.read_text(encoding="utf-8")
        snapshot_candidate_digest = candidate_digest(candidate_snapshot_text)
        snapshot_input_digest = review_input_digest(
            snapshot_candidate_digest,
            conversation_artifact_path=conversation_artifact_path,
            delivered_images=delivered_images,
            declared_docs=declared_docs,
            document_snapshots=document_snapshots,
        )
        current_source_input_digest = review_input_digest(
            current_candidate_digest,
            conversation_artifact_path=conversation_artifact_path,
            delivered_images=delivered_images,
            declared_docs=declared_docs,
        )
    except (OSError, UnicodeDecodeError, ValueError) as error:
        print(f"invalid: review_input_unreadable ({error})")
        return 1
    if (
        snapshot_candidate_digest != current_candidate_digest
        or snapshot_input_digest != args.input_digest
        or current_source_input_digest != args.input_digest
    ):
        print("invalid: review_inputs_changed")
        return 1
    print(f"valid {expected_report_path}")
    return 0


# ---------------------------------------------------------------------------
# conversation decisions review contract
# ---------------------------------------------------------------------------

# The reviewer role a report must name, and the token that selects this
# contract on the command line.
CONVERSATION_DECISIONS_ROLE = "conversation_decisions"

# The two directions this reviewer checks: forward, that every decision the
# user ratified landed; reverse, that every commitment the Candidate binds
# traces back to an authority.
DECISION_LANDING_CHECK = "ratified_decision_landing"
BINDING_AUTHORITY_CHECK = "binding_commitment_authority"
CONVERSATION_DECISIONS_CHECKS = (DECISION_LANDING_CHECK, BINDING_AUTHORITY_CHECK)


def validate_conversation_decisions_report(
    report,
    *,
    expected_candidate_digest,
    expected_candidate_path,
    expected_input_digest,
    expected_conversation_artifact_path,
    expected_authority_docs,
):
    """Return the list of violations; an empty list means the round passes."""
    return _validate_blocker_only_report(
        report,
        expected_role=CONVERSATION_DECISIONS_ROLE,
        checks=CONVERSATION_DECISIONS_CHECKS,
        expected_candidate_digest=expected_candidate_digest,
        expected_candidate_path=expected_candidate_path,
        expected_input_digest=expected_input_digest,
        path_fields=("conversation_artifact_path",),
        document_list_fields=("authority_docs",),
        expected_path_fields={
            "conversation_artifact_path": expected_conversation_artifact_path
        },
        expected_document_list_fields={"authority_docs": expected_authority_docs},
    )


# ---------------------------------------------------------------------------
# implementation ready review contract
# ---------------------------------------------------------------------------

IMPLEMENTATION_READY_ROLE = "implementation_ready"

# The five determinations an implementer must be able to reach from the
# Candidate alone. Everything outside them is free to emerge in code and
# tests, so this tuple is also the boundary that keeps unbound internal design
# out of the report: a finding has nowhere to sit unless it names one of these.
OBSERVABLE_BEHAVIOR_CHECK = "observable_behavior"
CALLER_CONTRACT_CHECK = "caller_contract"
ACCEPTANCE_ENDPOINT_CHECK = "acceptance_endpoint"
TESTING_SEAM_CHECK = "testing_seam"
UNRELAXABLE_CONSTRAINT_CHECK = "unrelaxable_constraint"
IMPLEMENTATION_READY_CHECKS = (
    OBSERVABLE_BEHAVIOR_CHECK,
    CALLER_CONTRACT_CHECK,
    ACCEPTANCE_ENDPOINT_CHECK,
    TESTING_SEAM_CHECK,
    UNRELAXABLE_CONSTRAINT_CHECK,
)


def validate_implementation_ready_report(
    report,
    *,
    expected_candidate_digest,
    expected_candidate_path,
    expected_input_digest,
    expected_allowed_docs,
):
    """Return the list of violations; an empty list means the round passes.

    The envelope admits the Candidate and the documents it declares, and
    nothing else: a conversation artifact or an authority the other reviewer
    holds is an unknown field here, so this reviewer's isolation survives in
    the report even if something reached it at dispatch.
    """
    return _validate_blocker_only_report(
        report,
        expected_role=IMPLEMENTATION_READY_ROLE,
        checks=IMPLEMENTATION_READY_CHECKS,
        expected_candidate_digest=expected_candidate_digest,
        expected_candidate_path=expected_candidate_path,
        expected_input_digest=expected_input_digest,
        document_list_fields=("allowed_docs",),
        expected_document_list_fields={"allowed_docs": expected_allowed_docs},
    )


def main(argv):
    """Validate one review round; the leading role token selects its contract."""
    if argv[:1] == [CONVERSATION_DECISIONS_ROLE]:
        return _validate_blocker_only_round(
            argv[1:],
            reviewer_role=CONVERSATION_DECISIONS_ROLE,
            validate=validate_conversation_decisions_report,
            path_input=(
                "--conversation-artifact",
                "conversation_artifact_path",
                "delivered conversation path printed by the assembler",
            ),
            document_list_input=(
                "--authority",
                "authority_docs",
                "one authority printed by the assembler; repeat in its original order",
            ),
        )
    if argv[:1] == [IMPLEMENTATION_READY_ROLE]:
        return _validate_blocker_only_round(
            argv[1:],
            reviewer_role=IMPLEMENTATION_READY_ROLE,
            validate=validate_implementation_ready_report,
            document_list_input=(
                "--allowed-doc",
                "allowed_docs",
                "one allowed document printed by the assembler; repeat in its "
                "original order",
            ),
        )
    # Reported as an invalid round rather than as usage help, so a caller that
    # forgot the role token reads a failure by the same rule as every other
    # one: anything but `valid <path>` fails the axis.
    print(
        f"invalid: reviewer_role_missing (expected {CONVERSATION_DECISIONS_ROLE} "
        f"or {IMPLEMENTATION_READY_ROLE} as the first argument)"
    )
    return 1


if __name__ == "__main__":  # pragma: no cover
    import sys

    raise SystemExit(main(sys.argv[1:]))
