"""Shared transcript extraction interface for supported agent runtimes."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import extract_claude_code
import extract_codex
import extract_cursor
from detect_runtime import detect_runtime
from extract_shared import ImageAssetError, ImageAssets


_ADAPTERS = {
    "claude_code": extract_claude_code,
    "codex": extract_codex,
    "cursor": extract_cursor,
}
_DEFAULT_CONTENT_CATEGORIES = frozenset({
    "user_prompt",
    "user_visible_agent_output",
})
_CONTENT_CATEGORIES = frozenset({
    "agent_instructions",
    "reasoning",
    "tool_activity",
    "turn_lifecycle",
    "user_prompt",
    "user_visible_agent_output",
})
_TRANSCRIPT_PATH_SCRIPT = (
    Path(__file__).resolve().parents[2] / "transcript-path" / "scripts" / "main.py"
)
EXTRACTION_MANIFEST_FILENAME = "extraction-manifest.json"
EXTRACTION_MANIFEST_VERSION = 1


class UnsupportedRuntimeError(ValueError):
    """The source transcript does not match a supported runtime."""


class InvalidTranscriptPathError(ValueError):
    """The requested transcript path cannot be used as a source."""


class TranscriptResolutionError(RuntimeError):
    """The current session transcript could not be resolved."""


class TranscriptReadError(ValueError):
    """A complete source record cannot be decoded as UTF-8 JSON."""


class CurrentSessionBoundaryError(RuntimeError):
    """The current extraction invocation cannot be excluded reliably."""


def _resolve_current_session_transcript():
    completed = subprocess.run(
        [sys.executable, str(_TRANSCRIPT_PATH_SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    lines = completed.stdout.splitlines()
    if len(lines) != 1 or not Path(lines[0]).is_absolute():
        return None
    return lines[0]


def _validate_source_path(path):
    source_path = Path(path).expanduser()
    if not source_path.is_file():
        raise InvalidTranscriptPathError(
            "Transcript path is not a readable file: {}".format(source_path)
        )
    try:
        with source_path.open("rb") as source:
            source.read(1)
    except OSError as error:
        raise InvalidTranscriptPathError(
            "Transcript path is not a readable file: {}".format(source_path)
        ) from error
    return source_path


def _load_records(path):
    records = []
    with open(path, "rb") as transcript:
        snapshot_size = os.fstat(transcript.fileno()).st_size
        snapshot = transcript.read(snapshot_size)
    raw_lines = snapshot.splitlines(keepends=True)
    for line_number, raw_line in enumerate(raw_lines, start=1):
        try:
            record = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            is_incomplete_tail = (
                line_number == len(raw_lines)
                and not snapshot.endswith(b"\n")
            )
            if is_incomplete_tail:
                continue
            raise TranscriptReadError(
                "{}:{}: transcript record is not valid UTF-8 JSON".format(
                    path,
                    line_number,
                )
            ) from error
        if isinstance(record, dict):
            records.append(record)
    return records


def _report_extraction_conditions(conditions):
    sections = [
        "{}: {}".format(label, "; ".join(conditions[label]))
        for label in ("omitted", "exceptional", "unknown")
        if conditions[label]
    ]
    if sections:
        print(
            "Extraction conditions: {}".format(" | ".join(sections)),
            file=sys.stderr,
        )


def _write_jsonl(destination, records):
    with destination.open("w", encoding="utf-8") as output:
        for record in records:
            output.write(json.dumps(
                record,
                ensure_ascii=False,
                separators=(",", ":"),
            ))
            output.write("\n")


def _write_extraction_manifest(
    output_directory,
    primary_artifact,
    *,
    selected_categories,
    include_launched_agents,
):
    assets_directory = Path(output_directory) / "assets"
    assets = []
    if assets_directory.exists():
        for asset in sorted(
            path for path in assets_directory.rglob("*") if path.is_file()
        ):
            assets.append(
                {
                    "path": asset.relative_to(output_directory).as_posix(),
                    "sha256": hashlib.sha256(asset.read_bytes()).hexdigest(),
                }
            )
    manifest = {
        "producer": "extract-transcript",
        "schema_version": EXTRACTION_MANIFEST_VERSION,
        "primary_artifact": primary_artifact.name,
        "primary_artifact_sha256": hashlib.sha256(
            primary_artifact.read_bytes()
        ).hexdigest(),
        "content_categories": sorted(selected_categories),
        "include_launched_agents": include_launched_agents,
        "assets": assets,
    }
    (output_directory / EXTRACTION_MANIFEST_FILENAME).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _interactive_question_activity_ids(content_records, adapter):
    """Return the ids of calls to the runtime's known question tools."""
    return frozenset(
        record["activity_id"]
        for record in content_records
        if (
            record.get("type") == "tool_activity"
            and record.get("stage") == "call"
            and record.get("tool_name") in adapter.INTERACTIVE_QUESTION_TOOLS
        )
    )


def extract_transcript(
    source_path=None,
    content_categories=None,
    *,
    include_launched_agents=False,
    transcript_resolver=None,
):
    """Normalize a primary transcript and optionally its proven launched agents."""
    automatically_resolved = source_path is None
    if source_path is None:
        if transcript_resolver is None:
            transcript_resolver = _resolve_current_session_transcript
        source_path = transcript_resolver()
        if not source_path:
            raise TranscriptResolutionError(
                "Current session transcript could not be resolved"
            )
    source_path = _validate_source_path(source_path)
    source_records = _load_records(source_path)
    runtime = detect_runtime(source_path)
    primary_adapter = _ADAPTERS.get(runtime)
    if primary_adapter is None:
        raise UnsupportedRuntimeError(
            "Unsupported or unknown transcript runtime: {}".format(runtime)
        )

    explicit_source_is_active = False
    if not automatically_resolved:
        active_session_evidence = getattr(
            primary_adapter,
            "active_session_evidence",
            None,
        )
        explicit_source_is_active = bool(
            active_session_evidence
            and active_session_evidence(source_records)
        )
    if automatically_resolved:
        cutoff = primary_adapter.current_session_cutoff(source_records)
        if cutoff is None:
            raise CurrentSessionBoundaryError(
                "Current session extraction boundary could not be resolved"
            )
        source_records = source_records[:cutoff]
    default_selection = content_categories is None
    selected_categories = (
        _DEFAULT_CONTENT_CATEGORIES
        if default_selection
        else frozenset(content_categories)
    )
    output_directory = Path(tempfile.mkdtemp(prefix="extract-transcript-"))
    try:
        conditions = {
            "omitted": [],
            "unknown": [],
            "exceptional": [],
        }
        destination = output_directory / "transcript.jsonl"

        def identified_condition(artifact_name, message):
            return "{}: {}".format(artifact_name, message)

        if explicit_source_is_active:
            conditions["exceptional"].append(
                identified_condition(
                    destination.name,
                    "source was active; artifact is a fixed snapshot",
                )
            )
        image_assets = ImageAssets(output_directory, Path(source_path).parent)

        def normalize_agent(
            agent_source_path,
            agent_runtime,
            agent_adapter,
            agent_source_records,
            artifact_name,
            parent_artifact_path=None,
        ):
            header = agent_adapter.extract_session_basic_data(agent_source_records)
            if parent_artifact_path is not None:
                header["parent_artifact_path"] = parent_artifact_path
            normalized_records = [header]
            unavailable_categories = getattr(
                agent_adapter,
                "UNAVAILABLE_CONTENT_CATEGORIES",
                {},
            )
            resolve_unavailable = getattr(
                agent_adapter,
                "unavailable_content_categories",
                None,
            )
            if resolve_unavailable is not None:
                unavailable_categories = resolve_unavailable(agent_source_records)
            for category in sorted(selected_categories):
                if category not in _CONTENT_CATEGORIES:
                    conditions["omitted"].append(
                        identified_condition(
                            artifact_name,
                            "{} is unsupported: not a content category".format(
                                category
                            ),
                        )
                    )
                elif category in unavailable_categories:
                    conditions["omitted"].append(
                        identified_condition(
                            artifact_name,
                            "{} is unavailable for {}: {}".format(
                                category,
                                agent_runtime,
                                unavailable_categories[category],
                            ),
                        )
                    )
            content_records = agent_adapter.extract_records(agent_source_records)
            # Adapters give every unpairable result its own fresh activity id, so
            # matching that id is the pairing proof a question answer must carry.
            question_activity_ids = (
                _interactive_question_activity_ids(content_records, agent_adapter)
                if default_selection
                else frozenset()
            )
            for source_record in content_records:
                if not (
                    source_record.get("type") in selected_categories
                    or source_record.get("activity_id") in question_activity_ids
                ):
                    continue
                record = dict(source_record)
                lifecycle_report = record.pop("_lifecycle_report", None)
                if lifecycle_report:
                    condition = (
                        "unknown"
                        if record.get("lifecycle_status") == "unknown"
                        else "exceptional"
                    )
                    conditions[condition].append(identified_condition(
                        artifact_name,
                        lifecycle_report,
                    ))
                content_report = record.pop("_content_report", None)
                if content_report:
                    conditions["exceptional"].append(identified_condition(
                        artifact_name,
                        content_report,
                    ))
                image_sources = record.pop("_images", None)
                if image_sources:
                    record["images"] = image_assets.materialize(
                        image_sources,
                        source_directory=Path(agent_source_path).parent,
                    )
                normalized_records.append(record)
            return normalized_records

        normalized_records = normalize_agent(
            source_path,
            runtime,
            primary_adapter,
            source_records,
            destination.name,
        )
        _write_jsonl(destination, normalized_records)

        if include_launched_agents:
            next_artifact_number = 1
            visited_sources = {source_path.resolve()}

            def export_children(
                parent_source_path,
                parent_adapter,
                parent_source_records,
                parent_artifact,
                parent_normalized_records,
            ):
                nonlocal next_artifact_number
                discover = getattr(
                    parent_adapter,
                    "discover_launched_agent_transcripts",
                    None,
                )
                if discover is None:
                    return
                try:
                    child_sources, discovery_conditions = discover(
                        parent_source_path,
                        parent_source_records,
                    )
                except Exception as error:
                    conditions["exceptional"].append(
                        identified_condition(
                            parent_artifact.name,
                            "launched-agent discovery failed for {}: {}".format(
                                parent_source_path,
                                error,
                            ),
                        )
                    )
                    return
                conditions["exceptional"].extend(
                    identified_condition(parent_artifact.name, condition)
                    for condition in discovery_conditions
                )
                child_artifact_paths = []
                for child_source in child_sources:
                    child_source = Path(child_source)
                    child_number = next_artifact_number
                    next_artifact_number += 1
                    child_artifact = output_directory / "agent-{:04d}.jsonl".format(
                        child_number
                    )
                    try:
                        validated_child_source = _validate_source_path(child_source)
                        resolved_child_source = validated_child_source.resolve()
                        if resolved_child_source in visited_sources:
                            raise ValueError("launched-agent transcript cycle detected")
                        child_runtime = detect_runtime(validated_child_source)
                        child_adapter = _ADAPTERS.get(child_runtime)
                        if child_adapter is None:
                            raise UnsupportedRuntimeError(
                                "unsupported or unknown transcript runtime: {}".format(
                                    child_runtime
                                )
                            )
                        child_source_records = _load_records(validated_child_source)
                        child_normalized_records = normalize_agent(
                            validated_child_source,
                            child_runtime,
                            child_adapter,
                            child_source_records,
                            child_artifact.name,
                            parent_artifact_path=parent_artifact.name,
                        )
                        _write_jsonl(child_artifact, child_normalized_records)
                    except Exception as error:
                        conditions["exceptional"].append(
                            identified_condition(
                                child_artifact.name,
                                "launched agent {} was not exported: {}".format(
                                    child_source,
                                    error,
                                ),
                            )
                        )
                        continue
                    visited_sources.add(resolved_child_source)
                    child_artifact_paths.append(child_artifact.name)
                    export_children(
                        validated_child_source,
                        child_adapter,
                        child_source_records,
                        child_artifact,
                        child_normalized_records,
                    )
                if child_artifact_paths:
                    parent_normalized_records[0][
                        "child_artifact_paths"
                    ] = child_artifact_paths
                    _write_jsonl(parent_artifact, parent_normalized_records)

            export_children(
                source_path,
                primary_adapter,
                source_records,
                destination,
                normalized_records,
            )
        _write_extraction_manifest(
            output_directory,
            destination,
            selected_categories=selected_categories,
            include_launched_agents=include_launched_agents,
        )
        _report_extraction_conditions(conditions)
    except Exception:
        shutil.rmtree(output_directory)
        raise
    return destination


def _parse_args(argv):
    parser = argparse.ArgumentParser(
        description=(
            "Extract a category-selective normalized transcript for Claude "
            "Code, Cursor, or Codex."
        )
    )
    parser.add_argument(
        "transcript_path",
        nargs="?",
        help="source transcript; omit to resolve the current session",
    )
    parser.add_argument(
        "--content-category",
        action="append",
        dest="content_categories",
        help="content category to retain; repeat to select multiple categories",
    )
    parser.add_argument(
        "--include-launched-agents",
        action="store_true",
        help="recursively export launched agents proven by the runtime",
    )
    return parser.parse_args(argv)


def main(argv=None, *, transcript_resolver=None):
    """Run the command-line interface and return its process status."""
    arguments = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        artifact = extract_transcript(
            arguments.transcript_path,
            content_categories=arguments.content_categories,
            include_launched_agents=arguments.include_launched_agents,
            transcript_resolver=transcript_resolver,
        ).resolve()
    except (OSError, RuntimeError, ValueError) as error:
        print("error: {}".format(error), file=sys.stderr)
        return 2
    print("Session artifact directory: {}".format(artifact.parent))
    print("Primary artifact: {}".format(artifact))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
