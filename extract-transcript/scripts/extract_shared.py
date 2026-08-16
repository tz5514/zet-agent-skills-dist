"""Shared source-content helpers for runtime adapters."""

import base64
from datetime import datetime
from pathlib import Path


_IMAGE_EXTENSIONS = {
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
_MEDIA_TYPES_BY_EXTENSION = {
    ".gif": "image/gif",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


class ImageAssetError(ValueError):
    """The selected image cannot be packaged into the extraction output."""


class ImageAssets:
    """Materialize selected image sources under one extraction directory."""

    def __init__(self, output_directory, source_directory):
        self._assets_directory = Path(output_directory) / "assets"
        self._source_directory = Path(source_directory)
        self._next_number = 1

    def materialize(self, sources, *, source_directory=None):
        source_directory = (
            self._source_directory
            if source_directory is None
            else Path(source_directory)
        )
        references = []
        for source in sources:
            if not isinstance(source, dict):
                raise ImageAssetError("unsupported image source")
            if source.get("type") == "base64":
                media_type = source.get("media_type")
                if media_type not in _IMAGE_EXTENSIONS:
                    raise ImageAssetError("unsupported image media type")
                try:
                    image_data = base64.b64decode(source.get("data"), validate=True)
                except (TypeError, ValueError) as error:
                    raise ImageAssetError("invalid base64 image data") from error
            elif source.get("type") == "path":
                source_path = Path(source.get("path", ""))
                if not source_path.is_absolute():
                    source_path = source_directory / source_path
                media_type = _MEDIA_TYPES_BY_EXTENSION.get(source_path.suffix.lower())
                if media_type is None:
                    raise ImageAssetError("unsupported image media type")
                try:
                    image_data = source_path.read_bytes()
                except OSError as error:
                    raise ImageAssetError(
                        "local image cannot be read: {}".format(source_path)
                    ) from error
            elif source.get("type") == "external_url":
                raise ImageAssetError(
                    "external image URL cannot be materialized: {}".format(
                        source.get("url", "unknown"),
                    )
                )
            else:
                raise ImageAssetError("unsupported image source")
            filename = "image-{:04d}{}".format(
                self._next_number,
                _IMAGE_EXTENSIONS[media_type],
            )
            self._next_number += 1
            self._assets_directory.mkdir(exist_ok=True)
            (self._assets_directory / filename).write_bytes(image_data)
            references.append({
                "path": "assets/{}".format(filename),
                "media_type": media_type,
            })
        return references


def normalized_content_record(content_category, *, text=None, image_sources=None):
    """Build one adapter record with optional dialogue text and owned images."""
    record = {"type": content_category}
    if text:
        record["text"] = text
    if image_sources:
        record["_images"] = image_sources
    return record


def mark_segmented_prompt(records, record_indexes, prompt_number):
    """Give fragments of one logical prompt a shared, stable identity."""
    if len(record_indexes) <= 1:
        return
    prompt_id = "prompt-{:04d}".format(prompt_number)
    for segment_index, record_index in enumerate(record_indexes):
        records[record_index]["prompt_id"] = prompt_id
        records[record_index]["segment_index"] = segment_index


def normalized_reasoning_record(
    representation,
    *,
    text=None,
    sequence_number=None,
):
    """Build one readable reasoning record."""
    if representation == "unreadable":
        return None
    record = {
        "type": "reasoning",
        "representation": representation,
    }
    if text:
        record["text"] = text
    if sequence_number is not None and representation == "summary":
        record["_content_report"] = "reasoning record {} is {}".format(
            sequence_number,
            "summarized",
        )
    return record


def normalized_anthropic_reasoning_record(block):
    """Map one readable Anthropic reasoning block."""
    thinking = block.get("thinking")
    if isinstance(thinking, str) and thinking:
        return normalized_reasoning_record("full", text=thinking)
    return None


def normalized_agent_instructions_record(source, text):
    """Build one substantive runtime-provided instruction record."""
    return {
        "type": "agent_instructions",
        "source": source,
        "text": text,
    }


def normalized_turn_lifecycle_record(event, **details):
    """Build one turn event from details directly present in the source."""
    record = {
        "type": "turn_lifecycle",
        "event": event,
    }
    record.update(
        (key, value) for key, value in details.items() if value is not None
    )
    return record


def normalized_tool_call_record(
    activity_id,
    tool_name,
    parameters,
    *,
    result_contract="expected",
    lifecycle_status="complete",
    lifecycle_report=None,
):
    """Build the call stage of one coupled tool activity."""
    record = {
        "type": "tool_activity",
        "activity_id": activity_id,
        "stage": "call",
        "tool_name": tool_name,
        "parameters": parameters,
        "result_contract": result_contract,
        "lifecycle_status": lifecycle_status,
    }
    if lifecycle_report:
        record["_lifecycle_report"] = lifecycle_report
    return record


def normalized_tool_result_record(
    activity_id,
    result,
    *,
    image_sources=None,
    is_error=None,
    lifecycle_status=None,
    lifecycle_report=None,
    result_available=True,
):
    """Build the result stage of one coupled tool activity."""
    record = {
        "type": "tool_activity",
        "activity_id": activity_id,
        "stage": "result",
    }
    if result_available:
        record["result"] = result
    if image_sources:
        record["_images"] = image_sources
    if isinstance(is_error, bool):
        record["is_error"] = is_error
    if lifecycle_status:
        record["lifecycle_status"] = lifecycle_status
    if lifecycle_report:
        record["_lifecycle_report"] = lifecycle_report
    return record


def tool_lifecycle_status(*, has_result, result_required, completion_evidenced):
    """Classify a tool call from its result contract and positive evidence."""
    if has_result or not result_required:
        return "complete"
    if completion_evidenced:
        return "expected_result_missing"
    return "unknown"


def tool_lifecycle_report(activity_id, tool_name, lifecycle_status):
    """Return user-facing report text for a non-routine lifecycle judgment."""
    if lifecycle_status == "expected_result_missing":
        detail = "expected result is missing"
    elif lifecycle_status == "unknown":
        detail = "lifecycle is unknown at the extraction boundary"
    elif lifecycle_status == "in_progress":
        detail = "activity was still in progress at the extraction boundary"
    elif lifecycle_status == "failed":
        detail = "activity failed"
    else:
        return None
    return "{} ({}): {}".format(activity_id, tool_name, detail)


def tool_result_report(activity_id, tool_name, lifecycle_report, is_error):
    """Add explicit error-result evidence to an activity report."""
    if is_error is not True:
        return lifecycle_report
    error_report = "{} ({}): completed with an error result".format(
        activity_id,
        tool_name,
    )
    return "; ".join(
        report for report in (lifecycle_report, error_report) if report
    )


def unmatched_tool_result_report(activity_id):
    """Return user-facing report text for a result lacking its source call."""
    return "{} (unknown tool): result could not be matched to a call".format(
        activity_id,
    )


def ordered_block_segments(content, boundary_type):
    """Return contiguous content segments around individual boundary blocks."""
    if not isinstance(content, list):
        return [("content", content)]
    segments = []
    retained = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == boundary_type:
            if retained:
                segments.append(("content", retained))
                retained = []
            segments.append((boundary_type, block))
        else:
            retained.append(block)
    if retained:
        segments.append(("content", retained))
    return segments


def split_tool_result_content(content):
    """Separate explicit result-image blocks from retained result content."""
    if not isinstance(content, list):
        return content, []
    retained = []
    image_sources = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "image":
            retained.append(block)
            continue
        source = block.get("source")
        if isinstance(source, dict):
            image_sources.append(source)
            continue
        if block.get("data") is not None and block.get("mimeType") is not None:
            image_sources.append({
                "type": "base64",
                "data": block["data"],
                "media_type": block["mimeType"],
            })
            continue
        retained.append(block)
    return retained, image_sources


def earliest_timestamp(records):
    """Return the source's earliest valid ISO-8601 timestamp."""
    candidates = []
    awareness = set()
    for record in records:
        timestamp = record.get("timestamp")
        if not isinstance(timestamp, str):
            continue
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            continue
        candidates.append((parsed, timestamp))
        awareness.add(parsed.utcoffset() is not None)
    if len(awareness) > 1:
        return None
    return min(candidates)[1] if candidates else None


def session_basic_data(
    runtime,
    *,
    session_start=None,
    model=None,
    working_directory=None,
    runtime_version=None,
    git_branch=None,
    token_usage=None,
):
    """Return the fixed session header with explicit unknown values."""
    def known_or_unknown(value):
        return "unknown" if value is None or value == "" else value

    return {
        "type": "session_basic_data",
        "runtime": runtime,
        "session_start": known_or_unknown(session_start),
        "model": known_or_unknown(model),
        "working_directory": known_or_unknown(working_directory),
        "runtime_version": known_or_unknown(runtime_version),
        "git_branch": known_or_unknown(git_branch),
        "token_usage": known_or_unknown(token_usage),
    }


def text_content(content):
    """Return text from a string or an ordered list of text blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""
