"""Cursor adapter: transcript rows -> normalized dialogue events.

Adapter contract (shared with every runtime adapter):
    extract_events(messages) -> ordered list of ("user" | "assistant", text)
    session_meta(messages)   -> (session_id, first_ts, last_ts)

This targets cursor-agent JSONL rows ({role, message}), not the Cursor IDE
composer SQLite store. Cursor wraps the visible typed prompt in a
<user_query>...</user_query> envelope and may prepend injected material such as
<timestamp> or <manually_attached_skills>; the envelope body is the human query.
"""
import re


def _content_text(content):
    """Plain text from a message content field (str or list of blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            b.get("text", "") for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


_USER_QUERY_RE = re.compile(r"<user_query>\s*(.*?)\s*</user_query>", re.DOTALL)
_INJECTED_WRAPPER_RES = (
    re.compile(
        r"<manually_attached_skills>.*?</manually_attached_skills>",
        re.DOTALL,
    ),
    re.compile(r"<timestamp>.*?</timestamp>", re.DOTALL),
)
_CONTROL_QUERY_PREFIXES = (
    "Briefly inform the user about the task result and perform any follow-up "
    "actions (if needed).",
    "The beginning of the above subagent result is already visible to the user. "
    "Perform any follow-up actions (if needed).",
)


def _strip_injected_wrappers(text):
    """Remove Cursor-injected wrappers before scanning for real user envelopes."""
    for pattern in _INJECTED_WRAPPER_RES:
        text = pattern.sub("", text)
    return text


def _has_user_query(text):
    return bool(_USER_QUERY_RE.search(text))


def _human_query_text(text):
    """Return the Cursor user query body when the prompt wrapper is present."""
    text = _strip_injected_wrappers(text)
    matches = [m.group(1).strip() for m in _USER_QUERY_RE.finditer(text)]
    if matches:
        return matches[-1]
    return text.strip()


def _is_control_query(text):
    """Cursor runtime control prompts are not human-typed dialogue."""
    return any(text.startswith(prefix) for prefix in _CONTROL_QUERY_PREFIXES)


def _visible_assistant_text(text):
    """Strip Cursor placeholder lines that stand in for non-output blocks."""
    lines = [
        line for line in text.splitlines()
        if line.strip() != "[REDACTED]"
    ]
    cleaned = "\n".join(lines).strip()
    return re.sub(r"\n{3,}", "\n\n", cleaned)


def extract_events(messages):
    """messages (parsed transcript rows) -> ordered list of (role, text)."""
    user_texts = []
    for msg in messages:
        if msg.get("role") != "user":
            continue
        raw = msg.get("message", {})
        content = raw.get("content", "") if isinstance(raw, dict) else raw
        user_texts.append(_strip_injected_wrappers(_content_text(content)))
    envelope_mode = any(_has_user_query(text) for text in user_texts)

    events = []
    last_user_text = None
    skipped_wrapperless_user = False
    for msg in messages:
        role = msg.get("role")
        raw = msg.get("message", {})
        content = raw.get("content", "") if isinstance(raw, dict) else raw

        if role == "user":
            raw_text = _content_text(content)
            stripped_text = _strip_injected_wrappers(raw_text)
            if envelope_mode and not _has_user_query(stripped_text):
                skipped_wrapperless_user = True
                continue
            text = _human_query_text(raw_text)
            if text:
                if envelope_mode and _is_control_query(text):
                    continue
                replayed_after_system_row = (
                    envelope_mode and skipped_wrapperless_user
                    and text == last_user_text
                )
                if (envelope_mode and events and events[-1] == ("user", text)
                        or replayed_after_system_row):
                    continue
                events.append(("user", text))
                last_user_text = text
                skipped_wrapperless_user = False
        elif role == "assistant":
            if not isinstance(content, list):
                continue
            for block in content:
                if (isinstance(block, dict) and block.get("type") == "text"
                        and block.get("text", "").strip()):
                    text = _visible_assistant_text(block["text"])
                    if text:
                        events.append(("assistant", text))
    return events


def session_meta(messages):
    """Cursor has no stable in-row session id; keep any timestamp range present."""
    first_ts = last_ts = None
    for m in messages:
        ts = m.get("timestamp")
        if ts:
            if first_ts is None:
                first_ts = ts
            last_ts = ts
    return None, first_ts, last_ts
