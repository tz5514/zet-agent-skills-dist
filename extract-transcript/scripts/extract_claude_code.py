"""Map Claude Code transcript records to normalized content records."""

import json
import re
from pathlib import Path

from extract_shared import (
    earliest_timestamp,
    mark_segmented_prompt,
    normalized_agent_instructions_record,
    normalized_anthropic_reasoning_record,
    normalized_content_record,
    normalized_turn_lifecycle_record,
    normalized_tool_call_record,
    normalized_tool_result_record,
    ordered_block_segments,
    session_basic_data,
    split_tool_result_content,
    text_content,
    tool_lifecycle_report,
    tool_result_report,
    tool_lifecycle_status,
    unmatched_tool_result_report,
)


_SYSTEM_PREFIXES = (
    "[Request interrupted",
    "<local-command-stdout>",
    "<local-command-caveat>",
    "<ide_opened_file>",
)
INTERACTIVE_QUESTION_TOOLS = frozenset({"AskUserQuestion"})
# Claude Code sources prove visible assistant text, while images are only proven
# in prompts or tool results; assistant image-looking blocks stay out.


def discover_launched_agent_transcripts(source_path, records):
    """Return child transcripts proven by Agent calls and runtime metadata."""
    tool_use_ids = []
    for record in records:
        if record.get("type") != "assistant":
            continue
        message = record.get("message")
        content = message.get("content", []) if isinstance(message, dict) else []
        if not isinstance(content, list):
            continue
        tool_use_ids.extend(
            block["id"]
            for block in content
            if (
                isinstance(block, dict)
                and block.get("type") == "tool_use"
                and block.get("name") == "Agent"
                and isinstance(block.get("id"), str)
                and block["id"]
            )
        )
    if not tool_use_ids:
        return [], []

    source_path = Path(source_path)
    child_directory = (
        source_path.parent
        if source_path.parent.name == "subagents"
        else source_path.parent / source_path.stem / "subagents"
    )
    paths_by_tool_use_id = {}
    if child_directory.is_dir():
        for metadata_path in sorted(child_directory.glob("agent-*.meta.json")):
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(metadata, dict):
                continue
            tool_use_id = metadata.get("toolUseId")
            if tool_use_id not in tool_use_ids:
                continue
            transcript_name = metadata_path.name[:-len(".meta.json")] + ".jsonl"
            paths_by_tool_use_id[tool_use_id] = metadata_path.with_name(
                transcript_name
            )

    child_paths = []
    conditions = []
    for tool_use_id in tool_use_ids:
        child_path = paths_by_tool_use_id.get(tool_use_id)
        if child_path is None:
            conditions.append(
                "Claude Code Agent launch {} has no discoverable transcript"
                .format(tool_use_id)
            )
        elif not child_path.is_file():
            conditions.append(
                "Claude Code Agent launch {} transcript is missing: {}".format(
                    tool_use_id,
                    child_path,
                )
            )
        else:
            child_paths.append(child_path)
    return child_paths, conditions


def current_session_cutoff(records):
    """Return the record before which this skill invocation begins."""
    command_name = "<command-name>/extract-transcript</command-name>"
    for index in range(len(records) - 1, -1, -1):
        record = records[index]
        if record.get("type") != "user":
            continue
        message = record.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if command_name in text_content(content):
            return index
    return None


def extract_session_basic_data(records):
    """Return Claude Code session data available at the extraction boundary."""
    first_values = {}
    model = None
    usage_by_request = {}
    has_unidentified_usage = False
    usage_fields = (
        "input_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
        "output_tokens",
    )
    for record in records:
        for source_key, header_key in (
            ("cwd", "working_directory"),
            ("version", "runtime_version"),
            ("gitBranch", "git_branch"),
        ):
            value = record.get(source_key)
            if header_key not in first_values and value not in (None, ""):
                first_values[header_key] = value

        message = record.get("message")
        if not isinstance(message, dict):
            continue
        if model is None and message.get("model") not in (None, ""):
            model = message["model"]
        usage = message.get("usage")
        if not isinstance(usage, dict):
            continue
        request_identity = record.get("requestId") or message.get("id")
        if not isinstance(request_identity, str) or not request_identity:
            has_unidentified_usage = True
            continue
        numeric_usage = [
            value
            for field in usage_fields
            for value in (usage.get(field),)
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        ]
        if not numeric_usage:
            has_unidentified_usage = True
            continue
        usage_by_request[request_identity] = sum(numeric_usage)

    token_usage = None
    if usage_by_request and not has_unidentified_usage:
        token_usage = sum(usage_by_request.values())

    return session_basic_data(
        "claude_code",
        session_start=earliest_timestamp(records),
        model=model,
        token_usage=token_usage,
        **first_values,
    )


def _is_user_prompt(record, text):
    if record.get("isMeta") is True:
        return False
    if any(text.startswith(prefix) for prefix in _SYSTEM_PREFIXES):
        return False
    return "<task-notification>" not in text


def _restore_command(text):
    name = re.search(r"<command-name>(.*?)</command-name>", text, re.DOTALL)
    arguments = re.search(r"<command-args>(.*?)</command-args>", text, re.DOTALL)
    command = name.group(1).strip() if name else ""
    argument_text = arguments.group(1).strip() if arguments else ""
    return "{} {}".format(command, argument_text).strip()


def _queued_command_prompt(record):
    attachment = record.get("attachment")
    if not isinstance(attachment, dict) or attachment.get("type") != "queued_command":
        return None
    prompt = attachment.get("prompt", "")
    if isinstance(prompt, list):
        prompt = "".join(
            block.get("text", "")
            for block in prompt
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return prompt.strip() if isinstance(prompt, str) and prompt.strip() else None


def _has_completion_evidence_after(records, activity):
    """Return whether later source content proves execution advanced."""
    for record_index in range(activity["record_index"] + 1, len(records)):
        record = records[record_index]
        message = record.get("message")
        content = message.get("content", []) if isinstance(message, dict) else message
        if isinstance(content, str):
            if content.strip():
                return True
            continue
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "text":
                continue
            text = block.get("text", "")
            if isinstance(text, str) and text.strip():
                return True
    return False


def extract_records(records):
    """Return content records in their source-relative order."""
    calls_by_block = {}
    calls_by_source_id = {}
    results = []
    results_by_block = {}
    for record_index, record in enumerate(records):
        message = record.get("message")
        content = message.get("content", []) if isinstance(message, dict) else []
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if record.get("type") == "assistant" and block.get("type") == "tool_use":
                activity = {
                    "activity_id": "tool-{:04d}".format(len(calls_by_block) + 1),
                    "block": block,
                    "record_index": record_index,
                }
                calls_by_block[id(block)] = activity
                source_id = block.get("id")
                if source_id:
                    calls_by_source_id[source_id] = activity
            elif record.get("type") == "user" and block.get("type") == "tool_result":
                result = {"block": block}
                results.append(result)
                results_by_block[id(block)] = result

    for result in results:
        activity = calls_by_source_id.get(result["block"].get("tool_use_id"))
        if activity is not None:
            result["activity"] = activity
            activity["has_result"] = True
    unmatched_number = len(calls_by_block) + 1
    for result in results:
        if "activity" not in result:
            result["activity_id"] = "tool-{:04d}".format(unmatched_number)
            unmatched_number += 1

    for activity in calls_by_block.values():
        activity["lifecycle_status"] = tool_lifecycle_status(
            has_result=activity.get("has_result", False),
            result_required=True,
            completion_evidenced=_has_completion_evidence_after(records, activity),
        )

    def result_record(block):
        result_info = results_by_block[id(block)]
        activity = result_info.get("activity")
        if activity is None:
            activity_id = result_info["activity_id"]
            lifecycle_status = "unknown"
            lifecycle_report = unmatched_tool_result_report(activity_id)
            tool_name = "unknown"
        else:
            activity_id = activity["activity_id"]
            lifecycle_status = None
            lifecycle_report = None
            tool_name = activity["block"].get("name", "unknown")
        result, image_sources = split_tool_result_content(block.get("content"))
        is_error = block.get("is_error")
        lifecycle_report = tool_result_report(
            activity_id,
            tool_name,
            lifecycle_report,
            is_error,
        )
        return normalized_tool_result_record(
            activity_id,
            result,
            image_sources=image_sources,
            is_error=is_error,
            lifecycle_status=lifecycle_status,
            lifecycle_report=lifecycle_report,
        )

    normalized = []
    logical_prompt_number = 0
    for record in records:
        record_type = record.get("type")
        message = record.get("message")
        if record_type == "user":
            content = (
                message.get("content", "")
                if isinstance(message, dict)
                else message
            )
            if (
                isinstance(content, str)
                and content.startswith("[Request interrupted")
            ):
                normalized.append(normalized_turn_lifecycle_record(
                    "interrupted",
                    detail=content,
                ))
                continue
            record_text = text_content(content)
            retain_prompt = _is_user_prompt(record, record_text)
            prompt_record_indexes = []
            for segment_type, segment in ordered_block_segments(
                content,
                "tool_result",
            ):
                if segment_type == "tool_result":
                    normalized.append(result_record(segment))
                    continue
                text = text_content(segment)
                images = [
                    block.get("source")
                    for block in segment
                    if isinstance(block, dict) and block.get("type") == "image"
                ] if isinstance(segment, list) else []
                if record.get("isMeta") is True:
                    if text.strip():
                        normalized.append(normalized_agent_instructions_record(
                            "runtime",
                            text,
                        ))
                    continue
                if not retain_prompt or not (text.strip() or images):
                    continue
                if "<command-name>" in text:
                    text = _restore_command(text)
                prompt_record_indexes.append(len(normalized))
                normalized.append(normalized_content_record(
                    "user_prompt",
                    text=text,
                    image_sources=images,
                ))
            if prompt_record_indexes:
                logical_prompt_number += 1
                mark_segmented_prompt(
                    normalized,
                    prompt_record_indexes,
                    logical_prompt_number,
                )
        elif record_type == "assistant" and isinstance(message, dict):
            content = message.get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    text = block.get("text", "")
                    if not isinstance(text, str) or not text.strip():
                        continue
                    normalized.append(normalized_content_record(
                        "user_visible_agent_output",
                        text=text,
                    ))
                elif block.get("type") in ("thinking", "redacted_thinking"):
                    reasoning_record = normalized_anthropic_reasoning_record(
                        block,
                    )
                    if reasoning_record is not None:
                        normalized.append(reasoning_record)
                elif block.get("type") == "tool_use":
                    activity = calls_by_block[id(block)]
                    lifecycle_status = activity["lifecycle_status"]
                    lifecycle_report = tool_lifecycle_report(
                        activity["activity_id"],
                        block.get("name", "unknown"),
                        lifecycle_status,
                    )
                    normalized.append(normalized_tool_call_record(
                        activity["activity_id"],
                        block.get("name", "unknown"),
                        block.get("input", {}),
                        lifecycle_status=lifecycle_status,
                        lifecycle_report=lifecycle_report,
                    ))
        elif record_type == "attachment":
            prompt = _queued_command_prompt(record)
            if prompt:
                logical_prompt_number += 1
                normalized.append(normalized_content_record(
                    "user_prompt",
                    text=prompt,
                ))
        elif record_type == "system" and record.get("subtype") == "api_error":
            normalized.append(normalized_turn_lifecycle_record(
                "error",
                error=record.get("error"),
                retry_attempt=record.get("retryAttempt"),
                max_retries=record.get("maxRetries"),
                retry_in_ms=record.get("retryInMs"),
                source=record.get("source"),
            ))
        elif (
            record_type == "system"
            and record.get("subtype") == "turn_duration"
        ):
            normalized.append(normalized_turn_lifecycle_record(
                "completed",
                duration_ms=record.get("durationMs"),
                message_count=record.get("messageCount"),
            ))
    return normalized
