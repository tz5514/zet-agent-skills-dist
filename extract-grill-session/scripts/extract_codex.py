"""Codex adapter: transcript rows -> normalized dialogue events.

Adapter contract (shared with every runtime adapter):
    extract_events(messages) -> ordered list of ("user" | "assistant", text)
    session_meta(messages)   -> (session_id, first_ts, last_ts)

The dialogue source is the event stream, not the model-visible conversation:
`event_msg`/`user_message` is recorded exactly when the human submitted a
message, and `event_msg`/`agent_message` carries the text the agent actually
showed. System injections (AGENTS.md instructions, <skill>, <goal_context>,
<hook_prompt>, <turn_aborted>, compaction history, …) reach the model only as
`response_item` rows and never get an event, and the assistant `response_item`
copy can trail non-displayed attachments (e.g. <oai-mem-citation>). So
"human-typed" is decided by which stream a row lives in — structural, never a
marker blacklist and never a length floor.
"""


def extract_events(messages):
    """messages (parsed transcript rows) -> ordered list of (role, text)."""
    events = []
    for msg in messages:
        if msg.get("type") != "event_msg":
            continue
        payload = msg.get("payload", {})
        pt = payload.get("type")
        if pt not in ("user_message", "agent_message"):
            continue
        text = payload.get("message")
        if not isinstance(text, str):
            continue
        if pt == "user_message":
            text = text.strip()
            if text:
                events.append(("user", text))
        elif text.strip():
            events.append(("assistant", text))
    return events


def session_meta(messages):
    """The session_meta row's id and the first/last envelope timestamps."""
    session_id = first_ts = last_ts = None
    for m in messages:
        if session_id is None and m.get("type") == "session_meta":
            payload = m.get("payload")
            if isinstance(payload, dict):
                session_id = payload.get("id")
        ts = m.get("timestamp")
        if ts:
            if first_ts is None:
                first_ts = ts
            last_ts = ts
    return session_id, first_ts, last_ts
