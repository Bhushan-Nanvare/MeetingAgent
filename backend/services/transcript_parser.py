"""Turn transcript files into plain text the model can read.

Handles WebVTT (.vtt) and SubRip (.srt) exports from Teams, Zoom and Meet, and
plain text. Timestamps and cue numbers are dropped; speaker names are kept
because the extractor needs them to work out who owns an action item.
"""

import html
import re

_CUE_ID = re.compile(r"^\d+$")
_VOICE_TAG = re.compile(r"^<v\s+([^>]+?)>(.*)$", re.IGNORECASE)
_ANY_TAG = re.compile(r"<[^>]*>")
# A name-like prefix only: up to four capitalised words, as Zoom and Meet write them.
_SPEAKER_PREFIX = re.compile(r"^([A-Z][\w.'-]*(?: [A-Z][\w.'-]*){0,3}):\s+(.*)$")
_SKIP_PREFIXES = ("WEBVTT", "NOTE", "STYLE", "REGION", "X-TIMESTAMP-MAP")


def parse_transcript(raw: str) -> str:
    """Return speaker-labelled plain text, or "" if there is nothing usable."""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")

    if "-->" not in text:
        return _clean_plain_text(text)

    lines: list[tuple[str | None, str]] = []
    in_skipped_block = False

    for line in text.split("\n"):
        line = line.strip()

        if not line:
            in_skipped_block = False
            continue
        if in_skipped_block:
            continue
        if line.startswith(_SKIP_PREFIXES):
            # NOTE and STYLE blocks run until the next blank line.
            in_skipped_block = True
            continue
        if "-->" in line or _CUE_ID.match(line):
            continue

        speaker, content = _split_speaker(line)
        if not content:
            continue
        # Live caption exports repeat a line as it grows; keep only the last one.
        if lines and lines[-1][0] == speaker and content.startswith(lines[-1][1]):
            lines[-1] = (speaker, content)
            continue
        lines.append((speaker, content))

    return _join(lines)


def _split_speaker(line: str) -> tuple[str | None, str]:
    voice = _VOICE_TAG.match(line)
    if voice:
        speaker = _strip_tags(voice.group(1)).strip()
        return (speaker or None, _strip_tags(voice.group(2)).strip())

    plain = _strip_tags(line).strip()
    prefix = _SPEAKER_PREFIX.match(plain)
    if prefix:
        return (prefix.group(1).strip(), prefix.group(2).strip())
    return (None, plain)


def _strip_tags(value: str) -> str:
    return html.unescape(_ANY_TAG.sub("", value))


def _join(lines: list[tuple[str | None, str]]) -> str:
    """Merge neighbouring lines from the same speaker into one paragraph."""
    merged: list[tuple[str | None, str]] = []
    for speaker, content in lines:
        if merged and merged[-1][0] == speaker and speaker is not None:
            merged[-1] = (speaker, f"{merged[-1][1]} {content}")
        else:
            merged.append((speaker, content))

    return "\n".join(
        f"{speaker}: {content}" if speaker else content for speaker, content in merged
    ).strip()


def _clean_plain_text(text: str) -> str:
    kept = [line.strip() for line in text.split("\n") if line.strip()]
    return "\n".join(kept).strip()
