"""Cut this round's review conversation out of an extract-transcript artifact.

The caller owns the endpoint cut: the review conversation must end at the
user's latest message — the last ``user_prompt`` record, or the last
interactive-question answer, whichever comes later in the artifact. This
script finds that endpoint from record fields alone, then writes every line
up to and including it, byte for byte, into a sibling review file in the
same artifact directory. The extractor's own output and its manifest are
never touched, and the sibling resolves the same relative ``assets/``
references.

The input is the artifact of extract-transcript's fixed default selection,
where the only tool activity present is the runtime's known interactive
question tool — so a ``tool_activity`` record with ``stage: "result"`` whose
``activity_id`` pairs it to an earlier call is the user's answer, and no
tool catalog is needed here. A call without a stored result is the agent
asking, not the user answering, and never ends the conversation.
"""

import argparse
import json
import os
import sys


REVIEW_FILE_NAME = "review-conversation.jsonl"


class CropError(Exception):
    """The artifact cannot yield a review conversation."""


def crop_review_conversation(artifact_path):
    """Write the sibling review file and return its absolute path."""
    artifact_path = os.path.abspath(artifact_path)
    if os.path.basename(artifact_path) == REVIEW_FILE_NAME:
        raise CropError(
            "input is already named %s; refusing to cut a cut" % REVIEW_FILE_NAME
        )
    try:
        with open(artifact_path, "rb") as source:
            raw = source.read()
    except OSError as error:
        raise CropError("cannot read artifact: %s" % error)
    lines = raw.splitlines(keepends=True)
    endpoint = None
    seen_calls = set()
    for index, line in enumerate(lines):
        try:
            record = json.loads(line)
        except (ValueError, UnicodeDecodeError) as error:
            raise CropError("line %d is not valid JSON: %s" % (index + 1, error))
        if not isinstance(record, dict):
            raise CropError("line %d is not a JSON object record" % (index + 1))
        if record.get("type") == "user_prompt":
            endpoint = index
        elif record.get("type") == "tool_activity":
            if record.get("stage") == "call":
                seen_calls.add(record.get("activity_id"))
            elif (
                record.get("stage") == "result"
                and record.get("activity_id") in seen_calls
            ):
                endpoint = index
    if endpoint is None:
        raise CropError(
            "no user message found: the artifact has no user_prompt record "
            "and no paired interactive-question answer"
        )
    review_path = os.path.join(os.path.dirname(artifact_path), REVIEW_FILE_NAME)
    try:
        with open(review_path, "wb") as review:
            review.write(b"".join(lines[: endpoint + 1]))
    except OSError as error:
        raise CropError("cannot write review file: %s" % error)
    return review_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "artifact", help="extract-transcript primary artifact (JSONL path)"
    )
    args = parser.parse_args(argv)
    try:
        review_path = crop_review_conversation(args.artifact)
    except CropError as error:
        print("error: %s" % error, file=sys.stderr)
        return 1
    print(review_path)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
