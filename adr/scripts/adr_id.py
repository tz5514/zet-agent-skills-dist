"""ADR id generation and parsing helpers."""

from datetime import date as date_type
from datetime import datetime
import re
import secrets
from pathlib import Path


ADR_ID_RANDOM_ALPHABET = "123456789abcdefghjkmnpqrstuvwxyz"
_LEGACY_ID_RE = re.compile(r"^\d{4}$")
_NEW_ID_RE = re.compile(rf"^(?P<date>\d{{8}})-(?P<random>[{ADR_ID_RANDOM_ALPHABET}]{{4}})$")
_LEGACY_FILENAME_RE = re.compile(r"^(?P<id>\d{4})-(?P<slug>.+)\.md$")
_NEW_FILENAME_RE = re.compile(
    rf"^(?P<date>\d{{8}})-(?P<random>[{ADR_ID_RANDOM_ALPHABET}]{{4}})-(?P<slug>.+)\.md$"
)
_DATE_RANDOM_PREFIX_RE = re.compile(r"^\d{8}-")


def generate_adr_id(*, today=None, choose=None):
    today = today or date_type.today()
    choose = choose or secrets.choice
    return f"{today:%Y%m%d}-" + "".join(choose(ADR_ID_RANDOM_ALPHABET) for _ in range(4))


def is_adr_id(value):
    try:
        parse_adr_id(value)
    except ValueError:
        return False
    return True


def parse_adr_id(value):
    if not isinstance(value, str):
        raise ValueError("ADR id must be a string")
    if _LEGACY_ID_RE.fullmatch(value):
        return {"scheme": "legacy", "id": value}
    match = _NEW_ID_RE.fullmatch(value)
    if match and _valid_date(match.group("date")):
        return {
            "scheme": "date_random",
            "id": value,
            "date": match.group("date"),
            "random": match.group("random"),
        }
    raise ValueError(f"invalid ADR id: {value}")


def parse_adr_filename(filename):
    name = Path(filename).name
    match = _NEW_FILENAME_RE.fullmatch(name)
    if match and _valid_date(match.group("date")) and match.group("slug"):
        return {
            "scheme": "date_random",
            "id": f"{match.group('date')}-{match.group('random')}",
            "date": match.group("date"),
            "random": match.group("random"),
            "slug": match.group("slug"),
        }
    if _DATE_RANDOM_PREFIX_RE.match(name) and name.endswith(".md"):
        raise ValueError(f"invalid ADR filename: {filename}")
    match = _LEGACY_FILENAME_RE.fullmatch(name)
    if match:
        return {"scheme": "legacy", "id": match.group("id"), "slug": match.group("slug")}
    raise ValueError(f"invalid ADR filename: {filename}")


def adr_id_from_filename(filename):
    try:
        return parse_adr_filename(filename)["id"]
    except ValueError:
        return Path(filename).stem


def _valid_date(value):
    try:
        datetime.strptime(value, "%Y%m%d")
    except ValueError:
        return False
    return True
