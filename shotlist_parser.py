"""
shotlist_parser.py — Reuters plain-text shotlist parser.

Parses the standard Reuters shotlist format into structured entry dicts.
Format example:

    CAPE CANAVERAL, FLORIDA, UNITED STATES (FILE - NOVEMBER 16, 2022) (NASA - ...)

    1. VARIOUS OF ARTEMIS I AS IT TAKES OFF WITH SPEAKER COUNTING DOWN AND THEN
    SAYING (English): 'And lift-off of Artemis I.'

    2. (SOUNDBITE) (English) SPEAKER, SAYING:
        "Quote text..."
"""
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def parse_shotlist(text: str) -> list[dict]:
    """
    Parse a Reuters-format shotlist into a list of entry dicts.

    Each entry corresponds to one numbered shot in the shotlist. Location blocks
    (ALL-CAPS header lines) are attached to the entry that immediately follows them.

    Args:
        text: Raw shotlist text as copied from a Reuters system.

    Returns:
        List of entry dicts, one per numbered shot:
        [
          {
            "entry_number": 1,        # shot number (1-based, from the shotlist)
            "description": str,       # full description text (stripped)
            "is_soundbite": bool,     # True if description contains "(SOUNDBITE)"
            "is_various": bool,       # True if description starts with "VARIOUS OF"
            "location_block": str,    # ALL-CAPS location/date/source line above the entry
            "raw": str,               # original text block for this entry
          },
          ...
        ]
    """
    if not text or not text.strip():
        return []

    lines = text.splitlines()

    # --- Pass 1: identify location blocks and numbered entry boundaries ---
    # A line is a location block if it is NOT empty, does NOT start with a
    # digit, and is substantially ALL-CAPS (ignoring punctuation/numbers).
    # Entry boundaries are lines matching /^\d+\.\s/ (e.g. "1. ", "12. ").

    entry_pattern = re.compile(r"^(\d+)\.\s+(.*)", re.DOTALL)

    # Split the full text on the numbered-entry boundaries.
    # We join back the lines so that multi-line descriptions are preserved.
    full_text = "\n".join(lines)
    # Split into tokens: everything before first entry, then alternating
    # (entry_number, entry_body) pairs.
    split_pattern = re.compile(r"(?m)^(\d+)\.\s+", re.MULTILINE)
    parts = split_pattern.split(full_text)

    # parts[0] = preamble (before first numbered entry)
    # parts[1], parts[2] = first entry number, first entry body
    # parts[3], parts[4] = second entry number, second entry body ...

    if len(parts) < 3:
        logger.warning("No numbered entries found in shotlist.")
        return []

    preamble = parts[0]

    # Build raw (number, body) pairs
    raw_entries: list[tuple[str, str]] = []
    i = 1
    while i + 1 < len(parts):
        raw_entries.append((parts[i].strip(), parts[i + 1]))
        i += 2

    # --- Pass 2: extract location blocks ---
    # Walk through the full text in order. Track the "last seen" location block.
    # A location block is an ALL-CAPS line that is not a numbered entry.
    # We build a mapping: entry_number -> location_block that precedes it.
    location_by_entry: dict[int, str] = {}
    current_location = ""

    # Re-scan line by line to capture location changes between entries
    # We need to know which location block immediately precedes each numbered entry.
    # Strategy: scan top-to-bottom; update current_location on location lines;
    # record it when we encounter a numbered entry line.
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        m = re.match(r"^(\d+)\.\s+", stripped)
        if m:
            entry_num = int(m.group(1))
            location_by_entry[entry_num] = current_location
        elif _is_location_block(stripped):
            current_location = stripped

    # --- Pass 3: build entry dicts ---
    results: list[dict] = []
    for num_str, body in raw_entries:
        try:
            entry_number = int(num_str)
        except ValueError:
            logger.warning("Could not parse entry number: %r — skipping.", num_str)
            continue

        description = _clean_description(body)
        is_soundbite = "(soundbite)" in description.lower()
        is_various = description.lower().startswith("various of")
        location_block = location_by_entry.get(entry_number, "")
        raw = f"{num_str}. {body}".strip()

        dateline = _parse_dateline(location_block)
        results.append({
            "entry_number": entry_number,
            "description": description,
            "is_soundbite": is_soundbite,
            "is_various": is_various,
            "location_block": location_block,
            "location": dateline["location"],
            "date": dateline["date"],
            "source": dateline["source"],
            "restrictions": dateline["restrictions"],
            "raw": raw,
        })

    return results


def _is_location_block(line: str) -> bool:
    """
    Return True if the line looks like a Reuters location/date/source block.

    Reuters location blocks start with an ALL-CAPS place name, e.g.:
      CAPE CANAVERAL, FLORIDA, UNITED STATES (FILE - NOVEMBER 16, 2022) (NASA - For...
      IN SPACE (RECENT) (NASA TV - ...)
      WASHINGTON D.C., UNITED STATES (RECENT - SEPTEMBER 12, 2025) (REUTERS - ...)

    The metadata in parentheses may contain mixed-case text (e.g. "For editorial
    use only"), so we only check the portion of the line *before* the first
    opening parenthesis.  That prefix must be non-empty and all-uppercase.
    """
    if not line:
        return False
    # Must not start with a digit (that would be a numbered entry)
    if line[0].isdigit():
        return False
    # Take only the part before the first parenthesis
    prefix = line.split("(")[0].strip()
    if not prefix:
        return False
    # Extract only alphabetic characters from the prefix
    alpha = "".join(c for c in prefix if c.isalpha())
    if not alpha:
        return False
    # All alpha chars in the prefix must be uppercase
    return alpha.isupper()


def _parse_dateline(location_block: str) -> dict[str, str]:
    """
    Parse a Reuters location/date/source/restrictions block.

    Formats handled:
      SEOUL, SOUTH KOREA (APRIL 8, 2026) (REUTERS - Access all)
      CAPE CANAVERAL, FLORIDA (FILE - NOVEMBER 16, 2022) (NASA - Editorial use only)
      IN SPACE (RECENT) (NASA TV - For editorial use only, no resales)
      WASHINGTON D.C. (RECENT - SEPTEMBER 12, 2025) (REUTERS - Access all)

    Returns:
        {"location": str, "date": str, "source": str, "restrictions": str}
    """
    if not location_block:
        return {"location": "", "date": "", "source": "", "restrictions": ""}

    # 1. Location = text before the first parenthesis (trimmed)
    location = location_block.split("(")[0].strip().rstrip(",").strip()

    # 2. Extract all parenthesised groups
    paren_groups = re.findall(r"\(([^)]+)\)", location_block)

    date = ""
    source = ""
    restrictions = ""

    for group in paren_groups:
        group = group.strip()
        # Groups containing " - " are either "FILE - DATE", "RECENT - DATE", or "SOURCE - RESTRICTIONS"
        if " - " in group:
            left, _, right = group.partition(" - ")
            left = left.strip()
            right = right.strip()
            # If left side is FILE or RECENT, it's a date group
            if left.upper() in ("FILE", "RECENT"):
                date = right
            else:
                # SOURCE - RESTRICTIONS
                source = left
                restrictions = right
        else:
            # Pure date group (e.g. "APRIL 8, 2026") or "RECENT"
            upper = group.upper()
            if upper == "RECENT" or any(m in upper for m in ("JANUARY", "FEBRUARY", "MARCH", "APRIL",
                "MAY", "JUNE", "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER")):
                date = group
            else:
                # Treat as source with no restrictions
                source = group

    return {"location": location, "date": date, "source": source, "restrictions": restrictions}


def _clean_description(body: str) -> str:
    """
    Strip leading/trailing whitespace from a multi-line description block.
    Normalise internal whitespace: collapse runs of spaces/tabs to a single space,
    but preserve intentional line breaks as single spaces (makes the description
    a clean single-string value).
    """
    # Collapse all whitespace (including newlines) to single spaces
    cleaned = re.sub(r"\s+", " ", body.strip())
    return cleaned


if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python shotlist_parser.py <shotlist.txt>")
        sys.exit(1)

    with open(sys.argv[1], "r", encoding="utf-8") as f:
        content = f.read()

    entries = parse_shotlist(content)
    print(json.dumps(entries, indent=2))
