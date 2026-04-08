"""
Tests for frame_extractor.py.

Creates a tiny synthetic video in a temp directory using OpenCV so the tests
are fully self-contained — no external video file required.
"""
import os
import sys
import tempfile

import cv2
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from frame_extractor import extract_frames


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_video(path: str, n_frames: int = 50, fps: float = 25.0,
                width: int = 64, height: int = 48) -> None:
    """Write a minimal synthetic MP4 to disk using OpenCV."""
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(path, fourcc, fps, (width, height))
    for i in range(n_frames):
        # Each frame is a solid colour that changes so we can visually verify seeks
        frame = np.full((height, width, 3), (i * 5 % 255, 100, 200), dtype=np.uint8)
        out.write(frame)
    out.release()


@pytest.fixture(scope="module")
def synthetic_video(tmp_path_factory):
    """Return a path to a 50-frame synthetic video at 25fps."""
    d = tmp_path_factory.mktemp("video")
    path = str(d / "test.mp4")
    _make_video(path, n_frames=50, fps=25.0)
    return path


@pytest.fixture()
def output_dir(tmp_path):
    """Return a fresh temp directory for thumbnails."""
    return str(tmp_path / "thumbs")


# ---------------------------------------------------------------------------
# Shot fixtures matching the synthetic video
# ---------------------------------------------------------------------------

SHOTS_FULL = [
    {"shot_index": 0, "timecode": "00:00:00:00", "frame_number": 0, "seconds": 0.0},
    {"shot_index": 1, "timecode": "00:00:00:20", "frame_number": 20, "seconds": 0.8},
    {"shot_index": 2, "timecode": "00:00:01:05", "frame_number": 30, "seconds": 1.2},
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestExtractFrames:

    def test_returns_shots_list(self, synthetic_video, output_dir):
        """extract_frames returns the shots list (possibly augmented)."""
        shots = [dict(s) for s in SHOTS_FULL]
        result = extract_frames(synthetic_video, shots, output_dir)
        assert isinstance(result, list)
        assert len(result) == len(SHOTS_FULL)

    def test_frame_path_added_to_shots(self, synthetic_video, output_dir):
        """Each shot has a 'frame_path' key after extraction."""
        shots = [dict(s) for s in SHOTS_FULL]
        result = extract_frames(synthetic_video, shots, output_dir)
        for shot in result:
            assert "frame_path" in shot, f"shot {shot['shot_index']} missing frame_path"

    def test_jpeg_files_written(self, synthetic_video, output_dir):
        """A JPEG file is written for each shot."""
        shots = [dict(s) for s in SHOTS_FULL]
        extract_frames(synthetic_video, shots, output_dir)
        jpegs = [f for f in os.listdir(output_dir) if f.endswith(".jpg")]
        assert len(jpegs) == len(SHOTS_FULL)

    def test_jpeg_naming_convention(self, synthetic_video, output_dir):
        """Files are named shot_NNNN.jpg (zero-padded to 4 digits)."""
        shots = [dict(s) for s in SHOTS_FULL]
        extract_frames(synthetic_video, shots, output_dir)
        for i in range(len(SHOTS_FULL)):
            expected = os.path.join(output_dir, f"shot_{i:04d}.jpg")
            assert os.path.isfile(expected), f"Expected {expected}"

    def test_frame_path_matches_file(self, synthetic_video, output_dir):
        """frame_path in each shot dict points to an existing JPEG."""
        shots = [dict(s) for s in SHOTS_FULL]
        result = extract_frames(synthetic_video, shots, output_dir)
        for shot in result:
            assert os.path.isfile(shot["frame_path"])

    def test_jpeg_is_readable(self, synthetic_video, output_dir):
        """Written JPEG files can be read back by OpenCV."""
        shots = [dict(s) for s in SHOTS_FULL]
        result = extract_frames(synthetic_video, shots, output_dir)
        for shot in result:
            img = cv2.imread(shot["frame_path"])
            assert img is not None, f"Could not read {shot['frame_path']}"
            assert img.shape[2] == 3  # BGR channels

    def test_output_dir_created_if_missing(self, synthetic_video, tmp_path):
        """output_dir is created automatically if it doesn't exist."""
        new_dir = str(tmp_path / "nested" / "thumbs")
        assert not os.path.exists(new_dir)
        shots = [dict(SHOTS_FULL[0])]
        extract_frames(synthetic_video, shots, new_dir)
        assert os.path.isdir(new_dir)

    def test_single_shot(self, synthetic_video, output_dir):
        """Works correctly with a single-shot video."""
        shots = [{"shot_index": 0, "timecode": "00:00:00:00", "frame_number": 0, "seconds": 0.0}]
        result = extract_frames(synthetic_video, shots, output_dir)
        assert len(result) == 1
        assert os.path.isfile(result[0]["frame_path"])

    def test_offset_clamped_for_very_short_shot(self, synthetic_video, output_dir):
        """
        When offset_seconds puts the target beyond the next shot, the extractor
        clamps to the midpoint — still produces a valid JPEG.
        """
        # Shots that are only 2 frames apart — offset of 0.5s would overshoot
        shots = [
            {"shot_index": 0, "timecode": "00:00:00:00", "frame_number": 0, "seconds": 0.0},
            {"shot_index": 1, "timecode": "00:00:00:02", "frame_number": 2, "seconds": 0.08},
        ]
        result = extract_frames(synthetic_video, shots, output_dir, offset_seconds=0.5)
        # Both shots should still produce a thumbnail
        for shot in result:
            assert "frame_path" in shot
            assert os.path.isfile(shot["frame_path"])

    def test_missing_video_returns_shots_unchanged(self, output_dir):
        """When the video cannot be opened, shots are returned without frame_path."""
        shots = [dict(s) for s in SHOTS_FULL]
        result = extract_frames("/nonexistent/video.mp4", shots, output_dir)
        assert len(result) == len(SHOTS_FULL)
        # frame_path should NOT be present since no frames could be extracted
        for shot in result:
            assert "frame_path" not in shot

    def test_original_shot_fields_preserved(self, synthetic_video, output_dir):
        """extract_frames does not remove existing fields from shot dicts."""
        shots = [dict(s) for s in SHOTS_FULL]
        result = extract_frames(synthetic_video, shots, output_dir)
        for orig, res in zip(SHOTS_FULL, result):
            assert res["shot_index"] == orig["shot_index"]
            assert res["timecode"] == orig["timecode"]
            assert res["frame_number"] == orig["frame_number"]
            assert res["seconds"] == orig["seconds"]

    def test_large_offset_does_not_exceed_video(self, synthetic_video, output_dir):
        """A very large offset_seconds is clamped — no crash, valid JPEG written."""
        shots = [{"shot_index": 0, "timecode": "00:00:00:00", "frame_number": 0, "seconds": 0.0}]
        result = extract_frames(synthetic_video, shots, output_dir, offset_seconds=9999.0)
        assert "frame_path" in result[0]
        assert os.path.isfile(result[0]["frame_path"])
