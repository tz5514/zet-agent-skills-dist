"""Claude Code adapter: transcript rows -> normalized dialogue events.

Adapter contract (shared with every runtime adapter):
    extract_events(messages) -> ordered list of ("user" | "assistant", text)
    session_meta(messages)   -> (session_id, first_ts, last_ts)

Whether a user-type row is human-typed is decided by structure (isMeta /
system markers), never by length — a one-word prompt like `停` is kept.
"""
import re

# system-generated event/output wrappers — records of an event, not text the
# human keyed in.
SYSTEM_PREFIXES = (
    "[Request interrupted",
    "<local-command-stdout>",
    "<local-command-caveat>",
    "<ide_opened_file>",
)


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


def _is_human_typed(msg, text):
    """A user-type row is human-typed unless it is a system injection/event."""
    if msg.get("isMeta") is True:
        return False
    if any(text.startswith(p) for p in SYSTEM_PREFIXES):
        return False
    if "<task-notification>" in text:
        return False
    return True


def _restore_command(text):
    """Render a slash-command envelope as the human typed it: `/cmd args`."""
    name = re.search(r"<command-name>(.*?)</command-name>", text, re.DOTALL)
    args = re.search(r"<command-args>(.*?)</command-args>", text, re.DOTALL)
    cmd = name.group(1).strip() if name else ""
    a = args.group(1).strip() if args else ""
    return f"{cmd} {a}".strip() if a else cmd


def _queued_command_prompt(msg):
    """The human prompt from a queued_command attachment, or None."""
    att = msg.get("attachment", {})
    if not (isinstance(att, dict) and att.get("type") == "queued_command"):
        return None
    prompt = att.get("prompt") or ""
    if isinstance(prompt, list):
        prompt = "".join(
            b.get("text", "") for b in prompt
            if isinstance(b, dict) and b.get("type") == "text"
        )
    return prompt.strip() or None


def extract_events(messages):
    """messages (parsed transcript rows) -> ordered list of (role, text)."""
    events = []
    for msg in messages:
        t = msg.get("type")
        if t == "user":
            raw = msg.get("message", {})
            content = raw.get("content", "") if isinstance(raw, dict) else raw
            text = _content_text(content).strip()
            if text and _is_human_typed(msg, text):
                if "<command-name>" in text:
                    text = _restore_command(text)
                events.append(("user", text))
        elif t == "assistant":
            content = (msg.get("message") or {}).get("content", [])
            if isinstance(content, list):
                for block in content:
                    if block.get("type") == "text" and block.get("text", "").strip():
                        events.append(("assistant", block["text"]))
        elif t == "attachment":
            prompt = _queued_command_prompt(msg)
            if prompt:
                events.append(("user", prompt))
    return events


def session_meta(messages):
    """First sessionId and the first/last timestamps seen, for the header."""
    session_id = first_ts = last_ts = None
    for m in messages:
        if session_id is None and "sessionId" in m:
            session_id = m["sessionId"]
        ts = m.get("timestamp")
        if ts:
            if first_ts is None:
                first_ts = ts
            last_ts = ts
    return session_id, first_ts, last_ts
