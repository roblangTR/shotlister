"""
Tests for scene_detector.py.

Tests frames_to_timecode() with known values and detect_scenes()
for correct return structure. Does not require a real video for
timecode arithmetic tests.
"""
import pytest
import sys
import os

# Ensure the project root is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scene_detector import frames_to_timecode


class TestFramesToTimecode:
    """Unit tests for the frames_to_timecode() conversion function."""

    def test_zero_frame_25fps(self):
        """Frame 0 at 25fps → 00:00:00:00."""
        assert frames_to_timecode(0, 25.0) == "00:00:00:00"

    def test_first_second_25fps(self):
        """Frame 25 at 25fps = exactly 1 second → 00:00:01:00."""
        assert frames_to_timecode(25, 25.0) == "00:00:01:00"

    def test_one_minute_25fps(self):
        """Frame 1500 at 25fps = 60 s → 00:01:00:00."""
        assert frames_to_timecode(1500, 25.0) == "00:01:00:00"

    def test_sub_second_frames_25fps(self):
        """Frame 12 at 25fps = 0.48 s → 00:00:00:12."""
        assert frames_to_timecode(12, 25.0) == "00:00:00:12"

    def test_large_frame_count_25fps(self):
        """Frame 37560 at 25fps = 25 min 2.4 s → 00:25:02:10."""
        # 37560 / 25 = 1502.4 s = 25 min 2 s + 0.4 s * 25 = 10 frames
        result = frames_to_timecode(37560, 25.0)
        assert result == "00:25:02:10"

    def test_24fps(self):
        """Frame 24 at 24fps = exactly 1 second → 00:00:01:00."""
        assert frames_to_timecode(24, 24.0) == "00:00:01:00"

    def test_timecode_format(self):
        """Output must always be HH:MM:SS:FF (4 colon-separated zero-padded fields)."""
        result = frames_to_timecode(0, 25.0)
        parts = result.split(":")
        assert len(parts) == 4
        assert all(len(p) == 2 for p in parts)

    def test_hours_overflow(self):
        """Frame count that results in hours > 0."""
        # 25 fps * 3600 s = 90000 frames → 01:00:00:00
        assert frames_to_timecode(90000, 25.0) == "01:00:00:00"


class TestDetectScenes:
    """Integration smoke tests for detect_scenes()."""

    def _find_test_video(self):
        """Return the path to a test video file, or None if unavailable."""
        test_video_dirs = [
            "/Users/lng3369/Documents/Claude/2026/shot_detector/Test Videos",
        ]
        extensions = {".mp4", ".avi", ".mov", ".mkv", ".m4v"}
        for d in test_video_dirs:
            if os.path.isdir(d):
                for fn in os.listdir(d):
                    if os.path.splitext(fn)[1].lower() in extensions:
                        return os.path.join(d, fn)
        return None

    def test_detect_returns_list(self):
        """detect_scenes() returns a list (even with a real video)."""
        from scene_detector import detect_scenes
        video = self._find_test_video()
        if video is None:
            pytest.skip("No test video available — skipping integration test.")
        shots = detect_scenes(video)
        assert isinstance(shots, list)

    def test_detect_first_shot_is_frame_zero(self):
        """The first shot always starts at frame 0."""
        from scene_detector import detect_scenes
        video = self._find_test_video()
        if video is None:
            pytest.skip("No test video available — skipping integration test.")
        shots = detect_scenes(video)
        assert len(shots) >= 1
        assert shots[0]["frame_number"] == 0
        assert shots[0]["timecode"] == "00:00:00:00"
        assert shots[0]["shot_index"] == 0

    def test_detect_shot_dict_keys(self):
        """Each shot dict has the required keys."""
        from scene_detector import detect_scenes
        video = self._find_test_video()
        if video is None:
            pytest.skip("No test video available — skipping integration test.")
        shots = detect_scenes(video)
        required_keys = {"shot_index", "timecode", "frame_number", "seconds"}
        for shot in shots:
            assert required_keys.issubset(shot.keys()), f"Missing keys in shot: {shot}"

    def test_detect_raises_for_missing_video(self):
        """detect_scenes() raises ValueError for a non-existent file."""
        from scene_detector import detect_scenes
        with pytest.raises(ValueError, match="not found"):
            detect_scenes("/nonexistent/path/video.mp4")
