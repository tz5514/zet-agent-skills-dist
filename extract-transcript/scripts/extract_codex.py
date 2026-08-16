"""Map Codex transcript records to normalized content records."""

import json
import re
from pathlib import Path

from extract_shared import (
    earliest_timestamp,
    normalized_agent_instructions_record,
    normalized_content_record,
    normalized_reasoning_record,
    normalized_tool_call_record,
    normalized_tool_result_record,
    normalized_turn_lifecycle_record,
    session_basic_data,
    split_tool_result_content,
    tool_lifecycle_report,
    tool_result_report,
    tool_lifecycle_status,
    unmatched_tool_result_report,
)


_EVENT_CONTENT_CATEGORIES = {
    "user_message": "user_prompt",
    "agent_message": "user_visible_agent_output",
}
_FILES_MENTIONED_PREFIX = "# Files mentioned by the user:"
_USER_REQUEST_MARKER = "## My request for Codex:"
_PAIRED_CALL_TYPES = frozenset({
    "custom_tool_call",
    "function_call",
    "tool_search_call",
})
_PAIRED_RESULT_TYPES = frozenset({
    "custom_tool_call_output",
    "function_call_output",
    "tool_search_output",
})
_SELF_CONTAINED_RESPONSE_TYPES = frozenset({
    "image_generation_call",
    "web_search_call",
})
_SELF_CONTAINED_EVENT_TYPES = frozenset({
    "mcp_tool_call_end",
    "view_image_tool_call",
})
INTERACTIVE_QUESTION_TOOLS = frozenset({"request_user_input"})
_PROGRESS_EVENT_TYPES = frozenset({
    "agent_message",
    "task_complete",
    "turn_aborted",
    "user_message",
})
_TURN_LIFECYCLE_EVENTS = {
    "task_started": (
        "started",
        (
            "turn_id",
            "started_at",
            "collaboration_mode_kind",
            "model_context_window",
        ),
    ),
    "task_complete": (
        "completed",
        (
            "turn_id",
            "started_at",
            "completed_at",
            "duration_ms",
            "time_to_first_token_ms",
        ),
    ),
    "turn_aborted": (
        "interrupted",
        ("turn_id", "started_at", "completed_at", "duration_ms", "reason"),
    ),
}
_SKILLS_WRAPPER_RE = re.compile(
    r"\A\s*<skills_instructions>(.*)</skills_instructions>\s*\Z",
    re.DOTALL,
)
_SKILLS_INDEX_HEADINGS = frozenset({
    "## Skills",
    "### Skill roots",
    "### Available skills",
})
_SKILLS_INDEX_PREAMBLE_PREFIXES = (
    "A skill is a set of local instructions",
    "Below is the list of skills",
    "Installed skill index.",
)
_SKILL_ROOT_ENTRY_RE = re.compile(r"- `?r\d+`?\s*=.*")
_AVAILABLE_SKILL_ENTRY_RE = re.compile(r"- .+?: .+\(file: .+\)")
_EXTRACT_TRANSCRIPT_SKILL_RE = re.compile(
    r"<skill>\s*<name>extract-transcript</name>",
    re.DOTALL,
)
_PROJECT_INSTRUCTIONS_RE = re.compile(
    r"\A# AGENTS\.md instructions for [^\n]+\n+"
    r"<INSTRUCTIONS>.*</INSTRUCTIONS>\s*\Z",
    re.DOTALL,
)
_RUNTIME_USER_INSTRUCTION_RES = (
    ("skill", re.compile(r"\A\s*<skill>.*</skill>\s*\Z", re.DOTALL)),
    ("hook", re.compile(r"\A\s*<hook_prompt>.*</hook_prompt>\s*\Z", re.DOTALL)),
    (
        "permission",
        re.compile(
            r"\A\s*<permissions instructions>.*</permissions instructions>\s*\Z",
            re.DOTALL,
        ),
    ),
)
_VIEW_IMAGE_DATA_URL_RE = re.compile(
    r"\Adata:(image/(?:gif|jpeg|png|webp));base64,(.+)\Z",
    re.DOTALL,
)


def _session_meta(records):
    return next(
        (
            record.get("payload")
            for record in records
            if (
                record.get("type") == "session_meta"
                and isinstance(record.get("payload"), dict)
            )
        ),
        None,
    )


def _spawn_launches(records):
    returned_task_names = {}
    for record in records:
        payload = record.get("payload")
        if not (
            record.get("type") == "response_item"
            and isinstance(payload, dict)
            and payload.get("type") == "function_call_output"
            and isinstance(payload.get("call_id"), str)
        ):
            continue
        output = payload.get("output")
        if isinstance(output, str):
            try:
                output = json.loads(output)
            except json.JSONDecodeError:
                output = None
        if isinstance(output, dict) and isinstance(output.get("task_name"), str):
            returned_task_names[payload["call_id"]] = output["task_name"]

    launches = []
    for record in records:
        payload = record.get("payload")
        if not (
            record.get("type") == "response_item"
            and isinstance(payload, dict)
            and payload.get("type") == "function_call"
            and payload.get("name") == "spawn_agent"
        ):
            continue
        call_id = payload.get("call_id")
        arguments = payload.get("arguments")
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = None
        requested_task_name = (
            arguments.get("task_name") if isinstance(arguments, dict) else None
        )
        returned_task_name = returned_task_names.get(call_id)
        launches.append({
            "agent_path": returned_task_name,
            "label": returned_task_name or requested_task_name or call_id
            or "unidentified spawn_agent launch",
        })
    return launches


def discover_launched_agent_transcripts(source_path, records):
    """Return Codex children whose session metadata names this parent thread."""
    launches = _spawn_launches(records)
    if not launches:
        return [], []

    session_meta = _session_meta(records)
    parent_thread_id = session_meta.get("id") if session_meta else None
    if not isinstance(parent_thread_id, str) or not parent_thread_id:
        return [], [
            "Codex launched-agent discovery is unavailable: parent thread id "
            "is missing"
        ]

    children = []
    source_path = Path(source_path).resolve()
    for candidate in sorted(source_path.parent.glob("*.jsonl")):
        if candidate.resolve() == source_path:
            continue
        try:
            with candidate.open(encoding="utf-8") as transcript:
                candidate_meta = None
                for raw_line in transcript:
                    try:
                        record = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue
                    if (
                        isinstance(record, dict)
                        and record.get("type") == "session_meta"
                    ):
                        candidate_meta = record.get("payload")
                        break
        except (OSError, UnicodeError):
            continue
        if not isinstance(candidate_meta, dict):
            continue
        source = candidate_meta.get("source")
        subagent = source.get("subagent") if isinstance(source, dict) else None
        thread_spawn = (
            subagent.get("thread_spawn") if isinstance(subagent, dict) else None
        )
        if (
            isinstance(thread_spawn, dict)
            and thread_spawn.get("parent_thread_id") == parent_thread_id
        ):
            children.append((candidate, thread_spawn.get("agent_path")))

    unmatched_launches = list(launches)
    child_paths = []
    conditions = []
    for child_path, agent_path in children:
        child_paths.append(child_path)
        matching_index = next(
            (
                index
                for index, launch in enumerate(unmatched_launches)
                if (
                    isinstance(agent_path, str)
                    and launch["agent_path"] == agent_path
                )
            ),
            None,
        )
        if matching_index is None:
            conditions.append(
                "Codex child {} could not be matched to a retained "
                "spawn_agent result".format(agent_path or child_path.name)
            )
        else:
            unmatched_launches.pop(matching_index)
    for launch in unmatched_launches:
        conditions.append(
            "Codex launched agent {} has no discoverable transcript".format(
                launch["label"]
            )
        )
    return child_paths, conditions


def _instruction_text(value):
    if isinstance(value, str):
        return value if value.strip() else None
    if isinstance(value, dict):
        text = value.get("text")
        return text if isinstance(text, str) and text.strip() else None
    return None


def _message_text(payload):
    if not isinstance(payload, dict) or payload.get("type") != "message":
        return ""
    content = payload.get("content")
    if not isinstance(content, list):
        return ""
    return "\n".join(
        text
        for block in content
        for text in (_instruction_text(block),)
        if text is not None
    )


def current_session_cutoff(records):
    """Return the first source record for this attached skill invocation."""
    skill_index = None
    for index in range(len(records) - 1, -1, -1):
        record = records[index]
        payload = record.get("payload")
        if (
            record.get("type") == "response_item"
            and isinstance(payload, dict)
            and payload.get("role") == "user"
            and _EXTRACT_TRANSCRIPT_SKILL_RE.search(_message_text(payload))
        ):
            skill_index = index
            break
    if skill_index is None:
        return None

    for event_index in range(skill_index - 1, -1, -1):
        record = records[event_index]
        payload = record.get("payload")
        if not (
            record.get("type") == "event_msg"
            and isinstance(payload, dict)
            and payload.get("type") == "user_message"
            and isinstance(payload.get("message"), str)
        ):
            continue
        cutoff = event_index
        if event_index > 0:
            previous = records[event_index - 1]
            previous_payload = previous.get("payload")
            if (
                previous.get("type") == "response_item"
                and isinstance(previous_payload, dict)
                and previous_payload.get("role") == "user"
                and _message_text(previous_payload) == payload["message"]
            ):
                cutoff -= 1
        return cutoff
    return None


def active_session_evidence(records):
    """Return whether a source record directly says work is still running."""
    active_statuses = frozenset({"generating", "in_progress", "running"})
    for index, record in enumerate(records):
        payload = record.get("payload")
        if not (
            isinstance(payload, dict)
            and payload.get("status") in active_statuses
        ):
            continue
        call_id = payload.get("call_id")
        has_matching_result = any(
            (
                call_id
                and isinstance(later_payload, dict)
                and later_payload.get("call_id") == call_id
                and later_payload.get("type") in _PAIRED_RESULT_TYPES
            )
            for later_record in records[index + 1:]
            for later_payload in (later_record.get("payload"),)
        )
        if not (
            has_matching_result
            or _has_progress_evidence_after(records, index)
        ):
            return True
    return False


def _developer_instruction_text(value):
    text = _instruction_text(value)
    if text is None:
        return None
    match = _SKILLS_WRAPPER_RE.fullmatch(text)
    if match is None:
        return text
    substantive_lines = []
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if (
            not stripped
            or stripped in _SKILLS_INDEX_HEADINGS
            or stripped.startswith(_SKILLS_INDEX_PREAMBLE_PREFIXES)
            or _SKILL_ROOT_ENTRY_RE.fullmatch(stripped)
            or _AVAILABLE_SKILL_ENTRY_RE.fullmatch(stripped)
        ):
            continue
        substantive_lines.append(line)
    substantive_text = "\n".join(substantive_lines).strip()
    return substantive_text or None


def _runtime_user_instruction_source(text):
    """Identify instruction-bearing user-role containers by source shape."""
    if _PROJECT_INSTRUCTIONS_RE.fullmatch(text):
        return "project"
    return next(
        (
            source
            for source, pattern in _RUNTIME_USER_INSTRUCTION_RES
            if pattern.fullmatch(text)
        ),
        None,
    )


def _user_prompt_text(text, local_images):
    if not local_images or not text.lstrip().startswith(_FILES_MENTIONED_PREFIX):
        return text
    lines = text.splitlines()
    marker_index = next(
        (
            index
            for index, line in enumerate(lines)
            if line.strip() == _USER_REQUEST_MARKER
        ),
        None,
    )
    if marker_index is None:
        return text
    wrapper_lines = set(lines[:marker_index])
    expected_file_lines = {
        "## {}: {}".format(Path(path).name, path)
        for path in local_images
        if isinstance(path, str) and path
    }
    if expected_file_lines and expected_file_lines.issubset(wrapper_lines):
        return "\n".join(lines[marker_index + 1:]).strip()
    return text


def extract_session_basic_data(records):
    """Return Codex session data available at the extraction boundary."""
    header_values = {}
    token_usage = None
    for record in records:
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        if record.get("type") == "session_meta":
            for source_key, header_key in (
                ("cwd", "working_directory"),
                ("cli_version", "runtime_version"),
            ):
                value = payload.get(source_key)
                if header_key not in header_values and value not in (None, ""):
                    header_values[header_key] = value
            git_data = payload.get("git")
            if isinstance(git_data, dict) and git_data.get("branch") not in (None, ""):
                header_values.setdefault("git_branch", git_data["branch"])
        if "model" not in header_values and payload.get("model") not in (None, ""):
            header_values["model"] = payload["model"]
        if record.get("type") != "event_msg" or payload.get("type") != "token_count":
            continue
        info = payload.get("info")
        cumulative = info.get("total_token_usage") if isinstance(info, dict) else None
        total = cumulative.get("total_tokens") if isinstance(cumulative, dict) else None
        if isinstance(total, (int, float)) and not isinstance(total, bool):
            token_usage = total

    return session_basic_data(
        "codex",
        session_start=earliest_timestamp(records),
        token_usage=token_usage,
        **header_values,
    )


def _has_progress_evidence_after(records, record_index):
    """Return whether later Codex records prove execution advanced."""
    for record in records[record_index + 1:]:
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        if record.get("type") == "turn_context":
            return True
        if (
            record.get("type") == "event_msg"
            and payload.get("type") in _PROGRESS_EVENT_TYPES
        ):
            return True
        if (
            record.get("type") == "response_item"
            and payload.get("type") == "message"
            and payload.get("role") in ("assistant", "user")
        ):
            return True
    return False


def _decode_json_container(value):
    if not isinstance(value, str):
        return value
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return value
    return decoded if isinstance(decoded, (dict, list)) else value


def _split_view_image_result_content(content):
    """Separate images only from the known Codex view_image result shape."""
    if not isinstance(content, list):
        return content, []
    retained = []
    image_sources = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "input_image":
            retained.append(block)
            continue
        image_url = block.get("image_url")
        match = (
            _VIEW_IMAGE_DATA_URL_RE.fullmatch(image_url)
            if isinstance(image_url, str)
            else None
        )
        if match is not None:
            image_sources.append({
                "type": "base64",
                "data": match.group(2),
                "media_type": match.group(1),
            })
            continue
        if isinstance(image_url, str) and image_url:
            image_sources.append({
                "type": "external_url",
                "url": image_url,
            })
            continue
        image_sources.append({"type": "unsupported"})
    return retained, image_sources


def _split_mcp_result_content(result):
    """Separate images only from the MCP Ok.content contract."""
    if not isinstance(result, dict):
        return result, []
    ok_result = result.get("Ok")
    if not (
        isinstance(ok_result, dict)
        and isinstance(ok_result.get("content"), list)
    ):
        return result, []
    retained_content, image_sources = split_tool_result_content(
        ok_result["content"],
    )
    if not image_sources:
        return result, []
    retained_ok = dict(ok_result)
    retained_ok["content"] = retained_content
    retained_result = dict(result)
    retained_result["Ok"] = retained_ok
    return retained_result, image_sources


def _result_error_evidence(result):
    decoded = _decode_json_container(result)
    if not isinstance(decoded, dict):
        return None
    metadata = decoded.get("metadata")
    exit_code = metadata.get("exit_code") if isinstance(metadata, dict) else None
    if isinstance(exit_code, int) and not isinstance(exit_code, bool):
        return exit_code != 0
    if isinstance(decoded.get("success"), bool):
        return not decoded["success"]
    if "Err" in decoded:
        return True
    if "Ok" in decoded:
        return False
    return None


def _mcp_result_error_evidence(result):
    """Return error evidence from the MCP result wrapper contract."""
    decoded = _decode_json_container(result)
    if isinstance(decoded, dict):
        ok_result = decoded.get("Ok")
        if (
            isinstance(ok_result, dict)
            and isinstance(ok_result.get("isError"), bool)
        ):
            return ok_result["isError"]
    return _result_error_evidence(decoded)


def _source_lifecycle_status(payload, *, has_result=False, terminal=False):
    if has_result:
        return "complete"
    status = payload.get("status")
    if status in ("completed", "success"):
        return "complete"
    if status in ("generating", "in_progress", "running"):
        return "in_progress"
    if status in ("error", "failed"):
        return "failed"
    return "complete" if terminal else "unknown"


def _paired_lifecycle_status(records, activity):
    """Classify a paired call without overriding explicit execution state."""
    if activity.get("has_result", False):
        return "complete"
    source_status = activity["payload"].get("status")
    if source_status in ("generating", "in_progress", "running"):
        return "in_progress"
    if source_status in ("error", "failed"):
        return "failed"
    return tool_lifecycle_status(
        has_result=False,
        result_required=True,
        completion_evidenced=(
            source_status in ("completed", "success")
            or _has_progress_evidence_after(
                records,
                activity["record_index"],
            )
        ),
    )


def extract_records(records):
    """Return visible event-stream content records in source-relative order."""
    activities = []
    activities_by_payload = {}
    calls_by_source_id = {}
    results = []
    results_by_payload = {}
    for record_index, record in enumerate(records):
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        payload_type = payload.get("type")
        is_tool_activity = (
            record.get("type") == "response_item"
            and payload_type in (_PAIRED_CALL_TYPES | _SELF_CONTAINED_RESPONSE_TYPES)
        ) or (
            record.get("type") == "event_msg"
            and payload_type in _SELF_CONTAINED_EVENT_TYPES
        )
        if is_tool_activity:
            activity = {
                "activity_id": "tool-{:04d}".format(len(activities) + 1),
                "record_index": record_index,
                "payload": payload,
            }
            activities.append(activity)
            activities_by_payload[id(payload)] = activity
            if payload_type in _PAIRED_CALL_TYPES and payload.get("call_id"):
                calls_by_source_id[payload["call_id"]] = activity
        elif (
            record.get("type") == "response_item"
            and payload_type in _PAIRED_RESULT_TYPES
        ):
            result = {"payload": payload}
            results.append(result)
            results_by_payload[id(payload)] = result

    for result in results:
        payload = result["payload"]
        activity = calls_by_source_id.get(payload.get("call_id"))
        if activity is not None:
            result["activity"] = activity
            activity["has_result"] = True
    unmatched_number = len(activities) + 1
    for result in results:
        if "activity" not in result:
            result["activity_id"] = "tool-{:04d}".format(unmatched_number)
            unmatched_number += 1

    for activity in activities:
        payload = activity["payload"]
        if payload.get("type") not in _PAIRED_CALL_TYPES:
            continue
        activity["lifecycle_status"] = _paired_lifecycle_status(
            records,
            activity,
        )

    def paired_result_record(payload):
        result_info = results_by_payload[id(payload)]
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
            tool_name = activity["payload"].get("name", "unknown")
            if activity["payload"].get("type") == "tool_search_call":
                tool_name = "tool_search"
        raw_result = (
            payload.get("tools")
            if payload.get("type") == "tool_search_output"
            else payload.get("output")
        )
        decoded_result = _decode_json_container(raw_result)
        has_view_image_contract = (
            activity is not None
            and activity["payload"].get("type") == "function_call"
            and activity["payload"].get("name") == "view_image"
            and payload.get("type") == "function_call_output"
        )
        if has_view_image_contract:
            result, image_sources = _split_view_image_result_content(
                decoded_result,
            )
        else:
            result = decoded_result
            image_sources = []
        is_error = _result_error_evidence(raw_result)
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

    def paired_call_record(payload):
        activity = activities_by_payload[id(payload)]
        if payload.get("type") == "custom_tool_call":
            parameters = payload.get("input", {})
        else:
            parameters = payload.get("arguments", {})
            parameters = _decode_json_container(parameters)
        tool_name = (
            "tool_search"
            if payload.get("type") == "tool_search_call"
            else payload.get("name", "unknown")
        )
        lifecycle_status = activity["lifecycle_status"]
        record = normalized_tool_call_record(
            activity["activity_id"],
            tool_name,
            parameters,
            lifecycle_status=lifecycle_status,
            lifecycle_report=tool_lifecycle_report(
                activity["activity_id"],
                tool_name,
                lifecycle_status,
            ),
        )
        if payload.get("status") is not None:
            record["source_status"] = payload["status"]
        if (
            payload.get("type") == "tool_search_call"
            and payload.get("execution") is not None
        ):
            record["execution"] = payload["execution"]
        return record

    def self_contained_records(payload):
        activity = activities_by_payload[id(payload)]
        payload_type = payload.get("type")
        result = payload.get("result")
        has_result = result is not None
        lifecycle_status = _source_lifecycle_status(
            payload,
            has_result=has_result,
            terminal=payload_type in _SELF_CONTAINED_EVENT_TYPES,
        )
        if payload_type == "web_search_call":
            tool_name = "web_search"
            parameters = payload.get("action", {})
        elif payload_type == "view_image_tool_call":
            tool_name = "view_image"
            parameters = {"path": payload.get("path")}
        elif payload_type == "mcp_tool_call_end":
            invocation = payload.get("invocation", {})
            server = invocation.get("server", "unknown")
            tool = invocation.get("tool", "unknown")
            tool_name = "{}.{}".format(server, tool)
            parameters = invocation.get("arguments", {})
        else:
            tool_name = "image_generation"
            parameters = {"revised_prompt": payload.get("revised_prompt")}
        call_record = normalized_tool_call_record(
            activity["activity_id"],
            tool_name,
            parameters,
            result_contract="not_required",
            lifecycle_status=lifecycle_status,
            lifecycle_report=tool_lifecycle_report(
                activity["activity_id"],
                tool_name,
                lifecycle_status,
            ),
        )
        if payload.get("status") is not None:
            call_record["source_status"] = payload["status"]
        if payload.get("execution") is not None:
            call_record["execution"] = payload["execution"]
        if payload.get("duration") is not None:
            call_record["duration"] = payload["duration"]
        normalized_activity = [call_record]
        if payload_type == "mcp_tool_call_end" and "result" in payload:
            decoded_result = _decode_json_container(result)
            result_content, image_sources = _split_mcp_result_content(
                decoded_result,
            )
            is_error = _mcp_result_error_evidence(decoded_result)
            normalized_activity.append(normalized_tool_result_record(
                activity["activity_id"],
                result_content,
                image_sources=image_sources,
                is_error=is_error,
                lifecycle_report=tool_result_report(
                    activity["activity_id"],
                    tool_name,
                    None,
                    is_error,
                ),
            ))
        elif payload_type == "image_generation_call" and has_result:
            normalized_activity.append(normalized_tool_result_record(
                activity["activity_id"],
                None,
                image_sources=[{
                    "type": "base64",
                    "data": result,
                    "media_type": "image/png",
                }],
                result_available=False,
            ))
        return normalized_activity

    normalized = []
    seen_instructions = set()
    submitted_user_messages = {
        payload.get("message")
        for record in records
        for payload in (record.get("payload"),)
        if (
            record.get("type") == "event_msg"
            and isinstance(payload, dict)
            and payload.get("type") == "user_message"
            and isinstance(payload.get("message"), str)
        )
    }

    def append_instruction(source, text):
        identity = (source, text)
        if identity in seen_instructions:
            return
        seen_instructions.add(identity)
        normalized.append(normalized_agent_instructions_record(source, text))

    reasoning_number = 0
    for record in records:
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        payload_type = payload.get("type")
        if record.get("type") == "session_meta":
            base_instructions = _instruction_text(
                payload.get("base_instructions"),
            )
            if base_instructions:
                append_instruction(
                    "system",
                    base_instructions,
                )
        elif (
            record.get("type") == "response_item"
            and payload_type == "message"
            and payload.get("role") in ("developer", "system")
        ):
            content = payload.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "input_text":
                    continue
                text = _developer_instruction_text(block.get("text"))
                if text:
                    append_instruction(
                        payload["role"],
                        text,
                    )
        elif (
            record.get("type") == "response_item"
            and payload_type == "message"
            and payload.get("role") == "user"
        ):
            content = payload.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "input_text":
                    continue
                text = _instruction_text(block.get("text"))
                if text is None or text in submitted_user_messages:
                    continue
                source = _runtime_user_instruction_source(text)
                if source is not None:
                    append_instruction(source, text)
        elif record.get("type") == "response_item" and payload_type == "reasoning":
            summary = payload.get("summary")
            summary_text = "\n".join(
                block.get("text", "")
                for block in summary
                if (
                    isinstance(block, dict)
                    and block.get("type") == "summary_text"
                    and isinstance(block.get("text"), str)
                    and block.get("text")
                )
            ) if isinstance(summary, list) else ""
            if summary_text:
                reasoning_number += 1
                normalized.append(normalized_reasoning_record(
                    "summary",
                    text=summary_text,
                    sequence_number=reasoning_number,
                ))
        elif (
            record.get("type") == "event_msg"
            and payload_type in _TURN_LIFECYCLE_EVENTS
        ):
            event, detail_keys = _TURN_LIFECYCLE_EVENTS[payload_type]
            normalized.append(normalized_turn_lifecycle_record(
                event,
                **{key: payload.get(key) for key in detail_keys},
            ))
        elif (
            record.get("type") == "event_msg"
            and payload_type in _EVENT_CONTENT_CATEGORIES
        ):
            content_category = _EVENT_CONTENT_CATEGORIES[payload_type]
            text = payload.get("message")
            if not isinstance(text, str):
                continue
            local_images = payload.get("local_images", [])
            external_images = payload.get("images", [])
            image_sources = [
                {"type": "path", "path": path}
                for path in local_images
                if isinstance(path, str) and path
            ]
            image_sources.extend(
                {"type": "external_url", "url": url}
                for url in external_images
                if isinstance(url, str) and url
            )
            if content_category == "user_prompt" and image_sources:
                text = _user_prompt_text(text, local_images)
            if text.strip() or image_sources:
                normalized.append(normalized_content_record(
                    content_category,
                    text=text,
                    image_sources=image_sources,
                ))
        elif (
            record.get("type") == "response_item"
            and payload_type in _PAIRED_CALL_TYPES
        ):
            normalized.append(paired_call_record(payload))
        elif (
            record.get("type") == "response_item"
            and payload_type in _PAIRED_RESULT_TYPES
        ):
            normalized.append(paired_result_record(payload))
        elif (
            record.get("type") == "response_item"
            and payload_type in _SELF_CONTAINED_RESPONSE_TYPES
        ) or (
            record.get("type") == "event_msg"
            and payload_type in _SELF_CONTAINED_EVENT_TYPES
        ):
            normalized.extend(self_contained_records(payload))
    return normalized
