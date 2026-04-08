"""
Tests for timecode_utils.py.

Covers detect_framerate, parse_frame_timecode, frame_tc_to_total_frames,
tc_to_frames, frame_tc_diff, frames_to_tc, and categorize_accuracy.
"""
import math
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from timecode_utils import (
    detect_framerate,
    parse_frame_timecode,
    frame_tc_to_total_frames,
    tc_to_frames,
    frame_tc_diff,
    frames_to_tc,
    categorize_accuracy,
)


class TestDetectFramerate:

    def test_colon_separator_is_25fps(self):
        assert detect_framerate("00:00:01:00") == 25.0

    def test_semicolon_separator_is_2997fps(self):
        assert detect_framerate("00:00:01;00") == 29.97

    def test_none_returns_25fps(self):
        assert detect_framerate(None) == 25.0

    def test_empty_string_returns_25fps(self):
        assert detect_framerate("") == 25.0

    def test_nan_returns_25fps(self):
        assert detect_framerate(float("nan")) == 25.0


class TestParseFrameTimecode:

    def test_valid_colon_timecode(self):
        result = parse_frame_timecode("01:02:03:04")
        assert result == {"hours": 1, "minutes": 2, "seconds": 3, "frames": 4}

    def test_valid_semicolon_timecode(self):
        """Semicolons (drop-frame format) are normalised to colons."""
        result = parse_frame_timecode("00:00:01;12")
        assert result == {"hours": 0, "minutes": 0, "seconds": 1, "frames": 12}

    def test_zero_timecode(self):
        result = parse_frame_timecode("00:00:00:00")
        assert result == {"hours": 0, "minutes": 0, "seconds": 0, "frames": 0}

    def test_none_returns_none(self):
        assert parse_frame_timecode(None) is None

    def test_empty_string_returns_none(self):
        assert parse_frame_timecode("") is None

    def test_nan_returns_none(self):
        assert parse_frame_timecode(float("nan")) is None

    def test_too_few_parts_returns_none(self):
        assert parse_frame_timecode("00:01:02") is None

    def test_too_many_parts_returns_none(self):
        assert parse_frame_timecode("00:00:00:00:00") is None

    def test_non_numeric_returns_none(self):
        assert parse_frame_timecode("AA:BB:CC:DD") is None


class TestFrameTcToTotalFrames:

    def test_zero(self):
        assert frame_tc_to_total_frames({"hours": 0, "minutes": 0, "seconds": 0, "frames": 0}) == 0

    def test_one_second_25fps(self):
        assert frame_tc_to_total_frames({"hours": 0, "minutes": 0, "seconds": 1, "frames": 0}, fps=25.0) == 25

    def test_one_minute_25fps(self):
        result = frame_tc_to_total_frames({"hours": 0, "minutes": 1, "seconds": 0, "frames": 0}, fps=25.0)
        assert result == 1500

    def test_one_hour_25fps(self):
        result = frame_tc_to_total_frames({"hours": 1, "minutes": 0, "seconds": 0, "frames": 0}, fps=25.0)
        assert result == 90000

    def test_none_returns_none(self):
        assert frame_tc_to_total_frames(None) is None


class TestTcToFrames:

    def test_zero_timecode(self):
        assert tc_to_frames("00:00:00:00") == 0

    def test_one_second_at_25fps(self):
        assert tc_to_frames("00:00:01:00") == 25

    def test_one_minute_at_25fps(self):
        assert tc_to_frames("00:01:00:00") == 1500

    def test_drop_frame_detected(self):
        """Semicolon triggers 29.97 fps calculation."""
        result = tc_to_frames("00:00:01;00")
        # 1 second × 29.97 fps = 29 frames (integer)
        assert result == 29


class TestFrameTcDiff:

    def test_same_timecode_is_zero(self):
        assert frame_tc_diff("00:00:05:00", "00:00:05:00") == 0

    def test_one_second_apart(self):
        assert frame_tc_diff("00:00:00:00", "00:00:01:00") == 25

    def test_order_independent(self):
        """Diff is absolute value — order doesn't matter."""
        assert frame_tc_diff("00:00:01:00", "00:00:00:00") == 25

    def test_none_returns_none(self):
        assert frame_tc_diff(None, "00:00:01:00") is None
        assert frame_tc_diff("00:00:01:00", None) is None


class TestFramesToTc:

    def test_zero(self):
        assert frames_to_tc(0, fps=25.0) == "00:00:00:00"

    def test_one_second_at_25fps(self):
        assert frames_to_tc(25, fps=25.0) == "00:00:01:00"

    def test_one_minute_at_25fps(self):
        assert frames_to_tc(1500, fps=25.0) == "00:01:00:00"

    def test_one_hour_at_25fps(self):
        assert frames_to_tc(90000, fps=25.0) == "01:00:00:00"

    def test_large_value(self):
        # 37560 / 25 = 1502.4 s = 25 min 2 s + 10 frames
        assert frames_to_tc(37560, fps=25.0) == "00:25:02:10"

    def test_format_zero_padded(self):
        parts = frames_to_tc(0, fps=25.0).split(":")
        assert len(parts) == 4
        assert all(len(p) == 2 for p in parts)


class TestCategorizeAccuracy:

    def test_none_is_unknown(self):
        assert categorize_accuracy(None) == "Unknown"

    def test_zero_is_perfect(self):
        assert categorize_accuracy(0) == "Perfect"

    def test_one_is_excellent(self):
        assert categorize_accuracy(1) == "Excellent"

    def test_two_is_excellent(self):
        assert categorize_accuracy(2) == "Excellent"

    def test_three_is_good(self):
        assert categorize_accuracy(3) == "Good"

    def test_five_is_good(self):
        assert categorize_accuracy(5) == "Good"

    def test_six_is_fair(self):
        assert categorize_accuracy(6) == "Fair"

    def test_ten_is_fair(self):
        assert categorize_accuracy(10) == "Fair"

    def test_eleven_is_poor(self):
        assert categorize_accuracy(11) == "Poor"