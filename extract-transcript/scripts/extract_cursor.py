"""Map Cursor agent transcript records to normalized content records."""

import re
from pathlib import Path

from extract_shared import (
    earliest_timestamp,
    mark_segmented_prompt,
    normalized_agent_instructions_record,
    normalized_anthropic_reasoning_record,
    normalized_content_record,
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


_USER_QUERY_TAG_RE = re.compile(r"</?user_query>")
_USER_QUERY_LINE_OPEN_RE = re.compile(r"(?m)^[ \t]*<user_query>")
_MANUALLY_ATTACHED_SKILLS_TAG_RE = re.compile(
    r"</?manually_attached_skills>",
)
_IMAGE_FILES_RE = re.compile(r"<image_files>(.*?)</image_files>", re.DOTALL)
_IMAGE_FILE_ENTRY_RE = re.compile(r"(\d+)\.[ \t]+(.+)")
_LEADING_IMAGE_MARKERS_RE = re.compile(
    r"\A(?:[ \t]*\[Image\][ \t]*\r?\n)+",
)
_IMAGE_FILES_HEADERS = frozenset({
    "The following images were provided by the user and saved to the "
    "workspace for future use:",
    "The following images were provdied by the user and saved to the "
    "workspace for future use:",
})
_IMAGE_FILES_FOOTER = "These images can be copied for use in other locations."
_TIMESTAMP_RE = re.compile(r"<timestamp>.*?</timestamp>", re.DOTALL)
# Cursor wraps these runtime-authored follow-up contracts like submitted queries.
_CONTROL_QUERY_PREFIXES = (
    "Briefly inform the user about the task result and perform any follow-up "
    "actions (if needed).",
    "The beginning of the above subagent result is already visible to the user. "
    "Perform any follow-up actions (if needed).",
)
_NO_RESULT_TOOLS = frozenset({"Task", "UpdateCurrentStep"})
INTERACTIVE_QUESTION_TOOLS = frozenset({"AskQuestion"})
# Cursor sources prove visible assistant text, while images are only proven in
# prompts or tool results; assistant image-looking blocks stay out.
UNAVAILABLE_CONTENT_CATEGORIES = {
    "turn_lifecycle": "the transcript has no direct turn lifecycle records",
}


def unavailable_content_categories(records):
    """Return categories absent from this specific Cursor transcript."""
    unavailable = dict(UNAVAILABLE_CONTENT_CATEGORIES)
    has_reasoning = any(
        isinstance(block, dict)
        and block.get("type") in ("thinking", "redacted_thinking")
        for record in records
        if record.get("role") == "assistant"
        for message in (record.get("message"),)
        if isinstance(message, dict)
        for content in (message.get("content"),)
        if isinstance(content, list)
        for block in content
    )
    if not has_reasoning:
        unavailable["reasoning"] = "the transcript has no explicit reasoning records"
    return unavailable


def discover_launched_agent_transcripts(source_path, records):
    """Report Task launches whose stored transcript relationship is unproven."""
    launch_descriptions = []
    for record in records:
        if record.get("role") != "assistant":
            continue
        message = record.get("message")
        content = message.get("content", []) if isinstance(message, dict) else []
        if not isinstance(content, list):
            continue
        for block in content:
            if not (
                isinstance(block, dict)
                and block.get("type") == "tool_use"
                and block.get("name") == "Task"
            ):
                continue
            tool_input = block.get("input")
            description = (
                tool_input.get("description")
                if isinstance(tool_input, dict)
                else None
            )
            launch_descriptions.append(
                description or "unidentified Task launch"
            )
    if not launch_descriptions:
        return [], []

    return [], [
        "Cursor launched-agent transcripts were not exported because Task "
        "launches [{}] do not share direct parent/child identifiers with "
        "stored child transcripts".format(", ".join(launch_descriptions))
    ]


def current_session_cutoff(records):
    """Return the record before which this attached skill invocation begins."""
    skill_name = re.compile(r"(?m)^Skill Name:\s*extract-transcript\s*$")
    for index in range(len(records) - 1, -1, -1):
        record = records[index]
        if record.get("role") != "user":
            continue
        message = record.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        text = text_content(content)
        queries, outside_text, malformed = _user_query_envelope(text)
        if malformed or not queries:
            continue
        skill_envelope = _leading_skill_envelope(outside_text)
        if skill_envelope and skill_name.search(skill_envelope[2]):
            return index
    return None


def extract_session_basic_data(records):
    """Return Cursor session data available at the extraction boundary."""
    return session_basic_data(
        "cursor",
        session_start=earliest_timestamp(records),
    )


def _strip_injected_wrappers(text, *, strip_prompt_images=False):
    skill_envelope = _leading_skill_envelope(text)
    without_skills = (
        text[:skill_envelope[0]] + text[skill_envelope[1]:]
        if skill_envelope
        else text
    )
    if strip_prompt_images:
        _, without_skills = _prompt_image_files(without_skills)
    return _TIMESTAMP_RE.sub("", without_skills)


def _prompt_image_files(text):
    """Return source-ordered paths and text without proven image wrappers."""
    image_sources, noise_spans = _prompt_image_contract(text)
    if not image_sources:
        return [], text
    retained_parts = []
    retained_from = 0
    for start, end in sorted(noise_spans):
        retained_parts.append(text[retained_from:start])
        retained_from = end
    retained_parts.append(text[retained_from:])
    return image_sources, "".join(retained_parts)


def _image_file_paths(wrapper):
    """Return paths from one complete observed Cursor image wrapper."""
    lines = [
        line.strip()
        for line in wrapper.group(1).splitlines()
        if line.strip()
    ]
    if (
        len(lines) < 3
        or lines[0] not in _IMAGE_FILES_HEADERS
        or lines[-1] != _IMAGE_FILES_FOOTER
    ):
        return None
    entries = [
        _IMAGE_FILE_ENTRY_RE.fullmatch(line)
        for line in lines[1:-1]
    ]
    if any(entry is None for entry in entries):
        return None
    paths = [entry.group(2).strip() for entry in entries]
    numbers = [int(entry.group(1)) for entry in entries]
    if (
        numbers != list(range(1, len(paths) + 1))
        or not all(Path(path).is_absolute() for path in paths)
    ):
        return None
    return paths


def _prompt_image_contract(text, excluded_span=None):
    """Return proven prompt images and their runtime framing spans."""
    marker_prefix = _LEADING_IMAGE_MARKERS_RE.match(text)
    if marker_prefix is None:
        return [], []
    marker_count = marker_prefix.group(0).count("[Image]")
    recognized_wrappers = []
    for wrapper in _IMAGE_FILES_RE.finditer(text):
        if (
            excluded_span is not None
            and excluded_span[0] <= wrapper.start() < excluded_span[1]
        ):
            continue
        paths = _image_file_paths(wrapper)
        if paths is None:
            continue
        recognized_wrappers.append((wrapper, paths))
    if len(recognized_wrappers) != 1:
        return [], []
    wrapper, paths = recognized_wrappers[0]
    if marker_count != len(paths):
        return [], []
    image_sources = [
        {"type": "path", "path": path}
        for path in paths
    ]
    return image_sources, [
        (marker_prefix.start(), marker_prefix.end()),
        (wrapper.start(), wrapper.end()),
    ]


def _prompt_image_sources(text):
    """Return images proven to belong to one terminal query envelope."""
    queries, outside_text, malformed = _user_query_envelope(text)
    if malformed or not queries:
        return []
    skill_envelope = _leading_skill_envelope(outside_text)
    without_skills = (
        outside_text[:skill_envelope[0]] + outside_text[skill_envelope[1]:]
        if skill_envelope
        else outside_text
    )
    image_sources, _ = _prompt_image_files(without_skills)
    return image_sources


def _leading_skill_envelope(text):
    """Return the position-framed runtime skill wrapper, if proven."""
    tags = list(_MANUALLY_ATTACHED_SKILLS_TAG_RE.finditer(text))
    if not tags:
        return None
    opening = tags[0]
    if opening.group(0) != "<manually_attached_skills>":
        return None
    closings = [
        match
        for match in tags[1:]
        if match.group(0) == "</manually_attached_skills>"
    ]
    if not closings:
        return None
    closing = closings[-1]
    return (
        opening.start(),
        closing.end(),
        text[opening.end():closing.start()],
        opening.end(),
        closing.start(),
    )


def _query_openings_outside_skill(text, openings):
    """Return one query opening only when positional ownership is unique."""
    if len(openings) <= 1:
        return openings
    candidates = []
    marker = "SKILL.md content:"
    for opening in openings:
        prefix = text[:opening.start()]
        skill_envelope = _leading_skill_envelope(prefix)
        if skill_envelope is None or marker not in skill_envelope[2]:
            continue
        prefix_without_skill = (
            prefix[:skill_envelope[0]] + prefix[skill_envelope[1]:]
        )
        if (
            _USER_QUERY_TAG_RE.search(prefix_without_skill)
            or _MANUALLY_ATTACHED_SKILLS_TAG_RE.search(prefix_without_skill)
        ):
            continue
        earlier_openings = [
            earlier
            for earlier in openings
            if earlier.start() < opening.start()
        ]
        if not all(
            skill_envelope[0] <= earlier.start() < skill_envelope[1]
            for earlier in earlier_openings
        ):
            continue
        candidates.append(opening)
    return candidates if len(candidates) == 1 else []


def _trailing_user_query_envelope(text):
    """Return the terminal Cursor query wrapper and malformed evidence."""
    content_end = len(text.rstrip())
    tags = list(_USER_QUERY_TAG_RE.finditer(text, 0, content_end))
    if (
        tags
        and tags[-1].group(0) == "</user_query>"
        and tags[-1].end() == content_end
    ):
        openings = list(_USER_QUERY_LINE_OPEN_RE.finditer(
            text,
            0,
            tags[-1].start(),
        ))
        openings = _query_openings_outside_skill(text, openings)
        if len(openings) != 1:
            return None, True
        opening = openings[0]
        closing = tags[-1]
        return (
            opening.start(),
            closing.end(),
            text[opening.end():closing.start()],
            opening.end(),
            closing.start(),
        ), False

    skill_envelope = _leading_skill_envelope(text)
    text_without_skill = (
        text[:skill_envelope[0]] + text[skill_envelope[1]:]
        if skill_envelope
        else text
    )
    return None, bool(_USER_QUERY_TAG_RE.search(text_without_skill))


def _user_query_envelope(text):
    """Return query bodies, outside text, and malformed-envelope evidence."""
    query_envelope, malformed = _trailing_user_query_envelope(text)
    if query_envelope is None:
        return [], text, malformed
    start, end, body = query_envelope[:3]
    return [body], text[:start] + text[end:], False


def _runtime_instruction_text(text):
    """Return runtime-owned text outside a well-formed user-query envelope."""
    queries, outside_text, malformed = _user_query_envelope(text)
    if malformed:
        return None
    return _strip_injected_wrappers(
        outside_text,
        strip_prompt_images=bool(queries),
    ).strip()


def _skill_instruction_texts(text, wrappers_are_runtime=False):
    instructions = []
    marker = "SKILL.md content:"
    queries, outside_text, _ = _user_query_envelope(text)
    if not queries:
        if not wrappers_are_runtime:
            return instructions
        outside_text = text
    skill_envelope = _leading_skill_envelope(outside_text)
    if skill_envelope is None:
        return instructions
    wrapper = skill_envelope[2]
    if marker not in wrapper:
        return instructions
    skill_text = wrapper.split(marker, 1)[1].strip()
    if skill_text:
        instructions.append(skill_text)
    return instructions


def _has_user_query(text):
    matches, _, malformed = _user_query_envelope(text)
    return bool(matches) and not malformed


def _has_user_query_markup(text):
    matches, _, malformed = _user_query_envelope(text)
    return bool(matches) or malformed


def _user_prompt(text):
    queries, _, malformed = _user_query_envelope(text)
    if malformed or not queries:
        return text.strip()
    return queries[-1].strip()


def _is_control_query(text):
    return any(text.startswith(prefix) for prefix in _CONTROL_QUERY_PREFIXES)


def _visible_agent_output(text):
    lines = text.splitlines(keepends=True)
    placeholder_indexes = {
        index
        for index, line in enumerate(lines)
        if line.rstrip("\r\n").strip() == "[REDACTED]"
    }
    if not placeholder_indexes:
        return text

    removed_indexes = set(placeholder_indexes)

    def is_blank(index):
        return lines[index].rstrip("\r\n").strip() == ""

    for index in placeholder_indexes:
        previous_is_blank = index > 0 and is_blank(index - 1)
        next_is_blank = index + 1 < len(lines) and is_blank(index + 1)
        if previous_is_blank and next_is_blank:
            removed_indexes.add(index + 1)
        elif index == 0 and next_is_blank:
            removed_indexes.add(index + 1)
        elif index == len(lines) - 1 and previous_is_blank:
            removed_indexes.add(index - 1)
    return "".join(
        line for index, line in enumerate(lines) if index not in removed_indexes
    )


def _image_sources(content):
    if not isinstance(content, list):
        return []
    return [
        {
            "type": "base64",
            "data": block.get("data"),
            "media_type": block.get("mimeType"),
        }
        for block in content
        if isinstance(block, dict) and block.get("type") == "image"
    ]


def _record_image_sources(content, wrapper_images):
    """Return record-owned prompt images in source-proven attachment order."""
    if not isinstance(content, list):
        return list(wrapper_images)
    image_sources = []
    wrappers_added = False
    for block in content:
        if isinstance(block, dict) and block.get("type") == "image":
            image_sources.extend(_image_sources([block]))
            continue
        if not (
            wrapper_images
            and not wrappers_added
            and isinstance(block, dict)
            and block.get("type") == "text"
            and _IMAGE_FILES_RE.search(block.get("text", ""))
        ):
            continue
        image_sources.extend(wrapper_images)
        wrappers_added = True
    if wrapper_images and not wrappers_added:
        image_sources.extend(wrapper_images)
    return image_sources


def _segment_text_ranges(segments):
    """Map content segments to their ranges in text_content(record_content)."""
    ranges = []
    cursor = 0
    saw_text_block = False
    for segment_type, segment in segments:
        if segment_type != "content":
            ranges.append(None)
            continue
        if isinstance(segment, str):
            block_texts = [segment]
        elif isinstance(segment, list):
            block_texts = [
                block.get("text", "")
                for block in segment
                if isinstance(block, dict) and block.get("type") == "text"
            ]
        else:
            block_texts = []
        if not block_texts:
            ranges.append(None)
            continue
        if saw_text_block:
            cursor += 1
        start = cursor
        cursor += sum(len(block_text) for block_text in block_texts)
        cursor += len(block_texts) - 1
        ranges.append((start, cursor))
        saw_text_block = True
    return ranges


def _skill_content_span(text, skill_envelope):
    """Return the source span of skill content without runtime framing."""
    if skill_envelope is None:
        return None
    marker = "SKILL.md content:"
    wrapper_start, wrapper_end = skill_envelope[3:5]
    marker_start = text.find(marker, wrapper_start, wrapper_end)
    if marker_start < 0:
        return None
    content_start = marker_start + len(marker)
    content_end = wrapper_end
    while content_start < content_end and text[content_start].isspace():
        content_start += 1
    while content_end > content_start and text[content_end - 1].isspace():
        content_end -= 1
    return (
        (content_start, content_end)
        if content_start < content_end
        else None
    )


def _subtract_spans(span, exclusions):
    """Return the portions of one source span outside excluded ranges."""
    retained = [span]
    for excluded_start, excluded_end in sorted(exclusions):
        next_retained = []
        for start, end in retained:
            if excluded_end <= start or excluded_start >= end:
                next_retained.append((start, end))
                continue
            if start < excluded_start:
                next_retained.append((start, excluded_start))
            if excluded_end < end:
                next_retained.append((excluded_end, end))
        retained = next_retained
    return retained


def _record_instruction_fragments(
    text,
    segment_range,
    query_envelope,
    skill_envelope,
    skill_content_span,
    noise_spans,
):
    """Map record-wide instruction ownership back to one source segment."""
    segment_start, segment_end = segment_range
    envelope_start, envelope_end = query_envelope[:2]
    outside_spans = []
    if segment_start < envelope_start:
        outside_spans.append((
            segment_start,
            min(segment_end, envelope_start),
        ))
    if segment_end > envelope_end:
        outside_spans.append((
            max(segment_start, envelope_end),
            segment_end,
        ))

    runtime_exclusions = list(noise_spans)
    if skill_envelope is not None:
        runtime_exclusions.append(skill_envelope[:2])
    owned_spans = []
    for outside_span in outside_spans:
        owned_spans.extend(
            (start, end, "runtime")
            for start, end in _subtract_spans(
                outside_span,
                runtime_exclusions,
            )
        )
    if skill_content_span is not None:
        skill_start = max(segment_start, skill_content_span[0])
        skill_end = min(segment_end, skill_content_span[1])
        if skill_start < skill_end:
            owned_spans.append((skill_start, skill_end, "skill"))

    fragments = []
    for start, end, source in sorted(
        owned_spans,
        key=lambda owned: (owned[2] != "skill", owned[0]),
    ):
        fragment_text = text[start:end].strip()
        if not fragment_text:
            continue
        if fragments and fragments[-1][0] == source:
            fragments[-1] = (
                source,
                fragments[-1][1] + "\n" + fragment_text,
            )
            continue
        fragments.append((source, fragment_text))
    return fragments


def _has_completion_evidence_before(
    records,
    activity,
    boundary_record_index,
    boundary_block_index,
):
    """Return whether source content before a boundary proves advancement."""
    stop_record_index = min(boundary_record_index, len(records) - 1)
    for record_index in range(
        activity["record_index"] + 1,
        stop_record_index + 1,
    ):
        record = records[record_index]
        message = record.get("message")
        content = message.get("content", []) if isinstance(message, dict) else []
        if not isinstance(content, list):
            continue
        stop = (
            boundary_block_index
            if record_index == boundary_record_index
            else len(content)
        )
        for block in content[:stop]:
            if not isinstance(block, dict) or block.get("type") != "text":
                continue
            text = block.get("text", "")
            if isinstance(text, str) and text.strip():
                return True
    return False


def _has_completion_evidence_after(records, activity):
    """Return whether later source content proves execution advanced."""
    return _has_completion_evidence_before(
        records,
        activity,
        len(records),
        0,
    )


def extract_records(records):
    """Return content records in their source-relative order."""
    calls = []
    calls_by_block = {}
    calls_by_source_id = {}
    results = []
    results_by_block = {}
    for record_index, record in enumerate(records):
        message = record.get("message")
        content = message.get("content", []) if isinstance(message, dict) else []
        if not isinstance(content, list):
            continue
        for block_index, block in enumerate(content):
            if not isinstance(block, dict):
                continue
            if record.get("role") == "assistant" and block.get("type") == "tool_use":
                activity = {
                    "activity_id": "tool-{:04d}".format(len(calls) + 1),
                    "block": block,
                    "record_index": record_index,
                }
                calls.append(activity)
                calls_by_block[id(block)] = activity
                if block.get("id"):
                    calls_by_source_id[block["id"]] = activity
            elif record.get("role") == "user" and block.get("type") == "tool_result":
                result = {"block": block}
                results.append(result)
                results_by_block[id(block)] = result

    paired_activities = set()
    for result in results:
        source_id = result["block"].get("tool_use_id")
        activity = calls_by_source_id.get(source_id) if source_id else None
        if activity is not None:
            result["activity"] = activity
            activity["has_result"] = True
            paired_activities.add(id(activity))
    outstanding_calls = []
    for record_index, record in enumerate(records):
        message = record.get("message")
        content = message.get("content", []) if isinstance(message, dict) else []
        if not isinstance(content, list):
            continue
        for block_index, block in enumerate(content):
            if not isinstance(block, dict):
                continue
            if record.get("role") == "assistant" and block.get("type") == "tool_use":
                activity = calls_by_block[id(block)]
                outstanding_calls = [
                    outstanding
                    for outstanding in outstanding_calls
                    if not _has_completion_evidence_before(
                        records,
                        outstanding,
                        record_index,
                        block_index,
                    )
                ]
                if (
                    id(activity) not in paired_activities
                    and block.get("name") not in _NO_RESULT_TOOLS
                ):
                    outstanding_calls.append(activity)
                continue
            if not (
                record.get("role") == "user"
                and block.get("type") == "tool_result"
            ):
                continue
            result = results_by_block[id(block)]
            if "activity" in result or block.get("tool_use_id"):
                continue
            outstanding_calls = [
                outstanding
                for outstanding in outstanding_calls
                if not _has_completion_evidence_before(
                    records,
                    outstanding,
                    record_index,
                    block_index,
                )
            ]
            if len(outstanding_calls) == 1:
                activity = outstanding_calls.pop()
                result["activity"] = activity
                activity["has_result"] = True
                paired_activities.add(id(activity))

    unmatched_number = len(calls) + 1
    for result in results:
        if "activity" not in result:
            result["activity_id"] = "tool-{:04d}".format(unmatched_number)
            unmatched_number += 1

    for activity in calls:
        tool_name = activity["block"].get("name", "unknown")
        result_required = tool_name not in _NO_RESULT_TOOLS
        activity["result_required"] = result_required
        activity["lifecycle_status"] = tool_lifecycle_status(
            has_result=activity.get("has_result", False),
            result_required=result_required,
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
        result_content, image_sources = split_tool_result_content(
            block.get("content"),
        )
        is_error = block.get("is_error")
        lifecycle_report = tool_result_report(
            activity_id,
            tool_name,
            lifecycle_report,
            is_error,
        )
        return normalized_tool_result_record(
            activity_id,
            result_content,
            image_sources=image_sources,
            is_error=is_error,
            lifecycle_status=lifecycle_status,
            lifecycle_report=lifecycle_report,
        )

    user_texts = []
    for record in records:
        if record.get("role") != "user":
            continue
        message = record.get("message")
        content = message.get("content", "") if isinstance(message, dict) else message
        user_texts.append(text_content(content))
    envelope_mode = any(_has_user_query(text) for text in user_texts)

    normalized = []
    logical_prompt_number = 0
    last_user_prompt = None
    skipped_wrapperless_user = False
    runtime_followup_evidenced = False
    for record in records:
        role = record.get("role")
        message = record.get("message")
        content = (
            message.get("content", "")
            if isinstance(message, dict)
            else message
        )
        if role == "user":
            prompt_record_indexes = []
            raw_text = text_content(content)
            query_envelope, query_malformed = _trailing_user_query_envelope(
                raw_text,
            )
            record_has_user_query = (
                query_envelope is not None and not query_malformed
            )
            record_skill_envelope = None
            record_skill_content_span = None
            record_noise_spans = []
            wrapper_images = []
            if record_has_user_query:
                record_prefix = raw_text[:query_envelope[0]]
                record_skill_envelope = _leading_skill_envelope(record_prefix)
                record_skill_content_span = _skill_content_span(
                    raw_text,
                    record_skill_envelope,
                )
                wrapper_images, image_noise_spans = _prompt_image_contract(
                    record_prefix,
                    excluded_span=(
                        record_skill_envelope[:2]
                        if record_skill_envelope is not None
                        else None
                    ),
                )
                record_noise_spans.extend(image_noise_spans)
                record_noise_spans.extend(
                    (match.start(), match.end())
                    for match in _TIMESTAMP_RE.finditer(record_prefix)
                )
            has_tool_results = (
                any(
                    isinstance(block, dict) and block.get("type") == "tool_result"
                    for block in content
                )
                if isinstance(content, list)
                else False
            )
            record_images = (
                _record_image_sources(content, wrapper_images)
                if record_has_user_query
                else _image_sources(content)
            )
            suppress_prompt = (
                envelope_mode
                and not _has_user_query_markup(raw_text)
                and not record_images
            )
            if suppress_prompt:
                if not has_tool_results:
                    skipped_wrapperless_user = True
                    runtime_followup_evidenced = False
            segments = ordered_block_segments(
                content,
                "tool_result",
            )
            segment_ranges = _segment_text_ranges(segments)
            record_images_attached = False
            for segment_number, (segment_type, segment) in enumerate(segments):
                if segment_type == "tool_result":
                    normalized.append(result_record(segment))
                    continue
                segment_text = text_content(segment)
                segment_range = segment_ranges[segment_number]
                if record_has_user_query and segment_range is not None:
                    for instruction_source, instruction_text in (
                        _record_instruction_fragments(
                            raw_text,
                            segment_range,
                            query_envelope,
                            record_skill_envelope,
                            record_skill_content_span,
                            record_noise_spans,
                        )
                    ):
                        normalized.append(
                            normalized_agent_instructions_record(
                                instruction_source,
                                instruction_text,
                            )
                        )
                elif not record_has_user_query:
                    for skill_text in _skill_instruction_texts(
                        segment_text,
                        wrappers_are_runtime=suppress_prompt,
                    ):
                        normalized.append(
                            normalized_agent_instructions_record(
                                "skill",
                                skill_text,
                            )
                        )
                if suppress_prompt:
                    instruction_text = _runtime_instruction_text(
                        segment_text,
                    )
                    if (
                        instruction_text
                        and instruction_text != last_user_prompt
                    ):
                        normalized.append(normalized_agent_instructions_record(
                            "runtime",
                            instruction_text,
                        ))
                    continue
                if record_has_user_query:
                    if segment_range is None:
                        continue
                    segment_start, segment_end = segment_range
                    body_start, body_end = query_envelope[3:5]
                    fragment_start = max(segment_start, body_start)
                    fragment_end = min(segment_end, body_end)
                    has_body_overlap = fragment_start < fragment_end
                    text = (
                        raw_text[fragment_start:fragment_end].strip()
                        if has_body_overlap
                        else ""
                    )
                    logical_prompt_text = query_envelope[2].strip()
                    owns_empty_prompt = (
                        not logical_prompt_text
                        and segment_start <= body_start <= segment_end
                    )
                    segment_images = (
                        record_images
                        if (
                            not record_images_attached
                            and (
                                text
                                or has_body_overlap
                                or owns_empty_prompt
                            )
                        )
                        else []
                    )
                else:
                    segment_images = _image_sources(segment)
                    if envelope_mode and not (
                        _has_user_query_markup(segment_text) or segment_images
                    ):
                        continue
                    if envelope_mode and _has_user_query(segment_text):
                        instruction_text = _runtime_instruction_text(segment_text)
                        if instruction_text:
                            normalized.append(
                                normalized_agent_instructions_record(
                                    "runtime",
                                    instruction_text,
                                )
                            )
                    text = _user_prompt(segment_text)
                    logical_prompt_text = text
                if not (text or segment_images):
                    continue
                replayed_after_control_record = (
                    envelope_mode
                    and skipped_wrapperless_user
                    and logical_prompt_text == last_user_prompt
                )
                if replayed_after_control_record:
                    runtime_followup_evidenced = True
                    continue
                if (
                    envelope_mode
                    and runtime_followup_evidenced
                    and _is_control_query(logical_prompt_text)
                ):
                    normalized.append(normalized_agent_instructions_record(
                        "runtime",
                        logical_prompt_text,
                    ))
                    continue
                prompt_record_indexes.append(len(normalized))
                normalized.append(normalized_content_record(
                    "user_prompt",
                    text=text,
                    image_sources=segment_images,
                ))
                if segment_images:
                    record_images_attached = True
                last_user_prompt = logical_prompt_text
                skipped_wrapperless_user = False
                runtime_followup_evidenced = False
            if prompt_record_indexes:
                logical_prompt_number += 1
                mark_segmented_prompt(
                    normalized,
                    prompt_record_indexes,
                    logical_prompt_number,
                )
        elif role == "assistant" and isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") in ("thinking", "redacted_thinking"):
                    reasoning_record = normalized_anthropic_reasoning_record(
                        block,
                    )
                    if reasoning_record is not None:
                        normalized.append(reasoning_record)
                elif block.get("type") == "text":
                    text = block.get("text", "")
                    if not isinstance(text, str):
                        continue
                    text = _visible_agent_output(text)
                    if text:
                        normalized.append(normalized_content_record(
                            "user_visible_agent_output",
                            text=text,
                        ))
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
                        result_contract=(
                            "expected"
                            if activity["result_required"]
                            else "not_required"
                        ),
                        lifecycle_status=lifecycle_status,
                        lifecycle_report=lifecycle_report,
                    ))
    return normalized
