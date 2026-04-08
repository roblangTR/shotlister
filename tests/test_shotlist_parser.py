"""
Tests for shotlist_parser.py.

Uses the Reuters example shotlist from CLAUDE.md / PLAN.md.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shotlist_parser import parse_shotlist, _is_location_block

# The example shotlist from CLAUDE.md / PLAN.md
EXAMPLE_SHOTLIST = """
CAPE CANAVERAL, FLORIDA, UNITED STATES (FILE - NOVEMBER 16, 2022) (NASA - For
editorial use only. Do not obscure logo)

1. VARIOUS OF ARTEMIS I AS IT TAKES OFF WITH SPEAKER COUNTING DOWN AND THEN
SAYING (English): 'And lift-off of Artemis I. We rise together back to the moon
and beyond."

IN SPACE (RECENT) (NASA TV - For editorial use only. Do not obscure logo)
2. VARIOUS OF MOON SURFACE SEEN FROM ORION SPACE CAPSULE

WASHINGTON D.C., UNITED STATES (RECENT - SEPTEMBER 12, 2025) (REUTERS - Access all)
3. (SOUNDBITE) (English) ACTING ADMINISTRATOR, NASA EXPLORATION SYSTEMS
DEVELOPMENT MISSION DIRECTORATE, DR LORI GLAZE, SAYING:
    "The Apollo missions landed near the equator of the moon..."
"""


class TestParseShotlist:

    def test_entry_count(self):
        """Parses exactly 3 entries from the example shotlist."""
        entries = parse_shotlist(EXAMPLE_SHOTLIST)
        assert len(entries) == 3

    def test_entry_numbers(self):
        """Entry numbers are 1, 2, 3."""
        entries = parse_shotlist(EXAMPLE_SHOTLIST)
        nums = [e["entry_number"] for e in entries]
        assert nums == [1, 2, 3]

    def test_is_various_flags(self):
        """Entries 1 and 2 are VARIOUS OF; entry 3 is not."""
        entries = parse_shotlist(EXAMPLE_SHOTLIST)
        assert entries[0]["is_various"] is True
        assert entries[1]["is_various"] is True
        assert entries[2]["is_various"] is False

    def test_is_soundbite_flags(self):
        """Only entry 3 is a soundbite."""
        entries = parse_shotlist(EXAMPLE_SHOTLIST)
        assert entries[0]["is_soundbite"] is False
        assert entries[1]["is_soundbite"] is False
        assert entries[2]["is_soundbite"] is True

    def test_location_blocks_present(self):
        """Each entry has a non-empty location block."""
        entries = parse_shotlist(EXAMPLE_SHOTLIST)
        for e in entries:
            assert e["location_block"], f"Entry {e['entry_number']} missing location block"

    def test_entry1_location_contains_cape_canaveral(self):
        """Entry 1 location block mentions CAPE CANAVERAL."""
        entries = parse_shotlist(EXAMPLE_SHOTLIST)
        assert "CAPE CANAVERAL" in entries[0]["location_block"].upper()

    def test_entry2_location_in_space(self):
        """Entry 2 location block mentions IN SPACE."""
        entries = parse_shotlist(EXAMPLE_SHOTLIST)
        assert "IN SPACE" in entries[1]["location_block"].upper()

    def test_entry3_location_washington(self):
        """Entry 3 location block mentions WASHINGTON."""
        entries = parse_shotlist(EXAMPLE_SHOTLIST)
        assert "WASHINGTON" in entries[2]["location_block"].upper()

    def test_description_stripped(self):
        """Descriptions have no leading/trailing whitespace."""
        entries = parse_shotlist(EXAMPLE_SHOTLIST)
        for e in entries:
            assert e["description"] == e["description"].strip()

    def test_description_content_entry1(self):
        """Entry 1 description contains 'ARTEMIS'."""
        entries = parse_shotlist(EXAMPLE_SHOTLIST)
        assert "ARTEMIS" in entries[0]["description"].upper()

    def test_empty_input(self):
        """Empty input returns empty list."""
        assert parse_shotlist("") == []
        assert parse_shotlist("   ") == []
        assert parse_shotlist(None) == []

    def test_no_entries(self):
        """Text with no numbered entries returns empty list."""
        assert parse_shotlist("CAPE CANAVERAL, FLORIDA\nSome text without numbers.") == []

    def test_raw_field_present(self):
        """Each entry has a 'raw' field."""
        entries = parse_shotlist(EXAMPLE_SHOTLIST)
        for e in entries:
            assert "raw" in e
            assert e["raw"]

    def test_single_entry(self):
        """Single-entry shotlist parses correctly."""
        entries = parse_shotlist("1. VARIOUS OF ROCKET LAUNCH")
        assert len(entries) == 1
        assert entries[0]["entry_number"] == 1
        assert entries[0]["is_various"] is True


class TestIsLocationBlock:

    def test_all_caps_location(self):
        """Pure ALL-CAPS line is a location block."""
        assert _is_location_block("CAPE CANAVERAL, FLORIDA") is True

    def test_location_with_parens(self):
        """Location with parenthesised date is still a block."""
        assert _is_location_block("CAPE CANAVERAL (NOVEMBER 16, 2022)") is True

    def test_numbered_entry_is_not_location(self):
        """Lines starting with a digit are not location blocks."""
        assert _is_location_block("1. VARIOUS OF ARTEMIS") is False

    def test_mixed_case_not_location(self):
        """Mixed-case description is not a location block."""
        assert _is_location_block("Various of rocket launch") is False

    def test_empty_string(self):
        """Empty string returns False."""
        assert _is_location_block("") is False

    def test_location_mixed_case_in_parens(self):
        """ALL-CAPS prefix followed by mixed-case in parens is still a location."""
        assert _is_location_block("CAPE CANAVERAL, FLORIDA (NASA - For editorial use only)") is True

    def test_in_space_location(self):
        """'IN SPACE' prefix with paren metadata is a location block."""
        assert _is_location_block("IN SPACE (RECENT) (NASA TV - For editorial use only)") is True

    def test_whitespace_only(self):
        """Whitespace-only string returns False."""
        assert _is_location_block("   ") is False


# ---------------------------------------------------------------------------
# Edge-case and extended shotlist tests
# ---------------------------------------------------------------------------

MULTI_LINE_SHOTLIST = """
LONDON, UNITED KINGDOM (APRIL 1, 2025) (REUTERS - Access all)

1. VARIOUS OF BIG BEN AT DAWN WITH MIST ROLLING ACROSS
THE THAMES RIVER AND EARLY MORNING COMMUTERS WALKING PAST

2. (SOUNDBITE) (English) PRIME MINISTER, SAYING:
    "We will not waver in our commitment to the people."

PARIS, FRANCE (APRIL 1, 2025) (REUTERS - Access all)

3. WIDE SHOT OF EIFFEL TOWER
4. CLOSE-UP OF PROTESTERS IN THE STREET
"""

SHOTLIST_NO_LOCATION = """
1. VARIOUS OF ROCKET LAUNCH
2. CLOSE-UP OF CONTROL ROOM
"""

SHOTLIST_LARGE_NUMBERS = """
BRUSSELS, BELGIUM (RECENT) (REUTERS - Access all)

9. VARIOUS OF EU PARLIAMENT EXTERIOR
10. (SOUNDBITE) (French) EU OFFICIAL SAYING:
    "L'Europe est unie."
11. AERIAL OF CITY CENTRE
"""

UTF8_SHOTLIST = """
BEIJING, CHINA (RECENT) (REUTERS - Access all)

1. VARIOUS OF GREAT WALL OF CHINA AT SUNRISE
2. (SOUNDBITE) (Mandarin) SPOKESPERSON, SAYING:
    "北京欢迎您 — Beijing welcomes you."
"""

SHOTLIST_ADJACENT_ENTRIES = "1. SHOT ONE\n2. SHOT TWO\n3. SHOT THREE"


class TestParseShotlistEdgeCases:

    def test_multi_line_description(self):
        """Multi-line entry descriptions are collapsed to a single string."""
        entries = parse_shotlist(MULTI_LINE_SHOTLIST)
        desc = entries[0]["description"]
        # Should not contain raw newlines
        assert "\n" not in desc
        # Should contain key words from both lines
        assert "BIG BEN" in desc
        assert "THAMES" in desc

    def test_four_entries_in_multi_line_shotlist(self):
        """Correct number of entries extracted from MULTI_LINE_SHOTLIST."""
        entries = parse_shotlist(MULTI_LINE_SHOTLIST)
        assert len(entries) == 4

    def test_location_change_mid_shotlist(self):
        """Entries 3 and 4 pick up the PARIS location, not LONDON."""
        entries = parse_shotlist(MULTI_LINE_SHOTLIST)
        assert "PARIS" in entries[2]["location_block"].upper()
        assert "PARIS" in entries[3]["location_block"].upper()

    def test_entries_without_location_block(self):
        """Entries without a preceding location block have empty string."""
        entries = parse_shotlist(SHOTLIST_NO_LOCATION)
        assert len(entries) == 2
        # No location block defined — should be empty string, not raise
        assert entries[0]["location_block"] == ""
        assert entries[1]["location_block"] == ""

    def test_two_digit_entry_numbers(self):
        """Entry numbers >= 10 are parsed correctly."""
        entries = parse_shotlist(SHOTLIST_LARGE_NUMBERS)
        nums = [e["entry_number"] for e in entries]
        assert 9 in nums
        assert 10 in nums
        assert 11 in nums

    def test_two_digit_entry_is_soundbite(self):
        """is_soundbite flag works for entry 10."""
        entries = parse_shotlist(SHOTLIST_LARGE_NUMBERS)
        entry10 = next(e for e in entries if e["entry_number"] == 10)
        assert entry10["is_soundbite"] is True

    def test_utf8_description(self):
        """UTF-8 characters in descriptions are preserved."""
        entries = parse_shotlist(UTF8_SHOTLIST)
        assert len(entries) == 2
        # Chinese characters should survive the round-trip
        soundbite = next(e for e in entries if e["is_soundbite"])
        assert "北京" in soundbite["description"]

    def test_adjacent_entries_no_blank_lines(self):
        """Entries work even without blank lines between them."""
        entries = parse_shotlist(SHOTLIST_ADJACENT_ENTRIES)
        assert len(entries) == 3
        assert entries[0]["entry_number"] == 1
        assert entries[2]["entry_number"] == 3

    def test_whitespace_only_description_stripped(self):
        """Descriptions with only whitespace are stripped to empty string."""
        entries = parse_shotlist("1.    \n2. REAL SHOT")
        # Entry 1 body may be empty — should not crash
        assert len(entries) >= 1

    def test_entry_number_in_raw(self):
        """The 'raw' field starts with the entry number."""
        entries = parse_shotlist(MULTI_LINE_SHOTLIST)
        for e in entries:
            assert e["raw"].startswith(str(e["entry_number"]))

    def test_is_various_case_insensitive(self):
        """'various of' in lowercase is also detected."""
        entries = parse_shotlist("1. various of something")
        assert entries[0]["is_various"] is True

    def test_is_soundbite_case_insensitive(self):
        """'(soundbite)' in lowercase is detected."""
        entries = parse_shotlist("1. (soundbite) speaker saying something")
        assert entries[0]["is_soundbite"] is True

    def test_very_large_shotlist(self):
        """Parser handles a large shotlist (100 entries) without error."""
        lines = ["LOCATION, COUNTRY (RECENT) (REUTERS - Access all)\n"]
        for i in range(1, 101):
            lines.append(f"{i}. SHOT DESCRIPTION NUMBER {i}\n")
        text = "\n".join(lines)
        entries = parse_shotlist(text)
        assert len(entries) == 100
        assert entries[-1]["entry_number"] == 100
