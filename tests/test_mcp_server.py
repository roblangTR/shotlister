"""
Smoke tests for mcp_server.py.

Verifies that the module imports cleanly, the FastMCP app is configured
correctly, and both tools have the expected signatures and return the right
structure when called with mocked dependencies.
"""
import sys
import os
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Import smoke test
# ---------------------------------------------------------------------------

class TestMcpServerImport:

    def test_module_imports_without_error(self):
        """mcp_server.py imports cleanly."""
        import mcp_server  # noqa: F401

    def test_mcp_app_exists(self):
        """The FastMCP instance named 'mcp' is accessible."""
        import mcp_server
        assert hasattr(mcp_server, "mcp")

    def test_detect_shots_callable(self):
        """detect_shots is a callable registered on the mcp instance."""
        import mcp_server
        assert callable(mcp_server.detect_shots)

    def test_match_shotlist_callable(self):
        """match_shotlist is a callable registered on the mcp instance."""
        import mcp_server
        assert callable(mcp_server.match_shotlist)


# ---------------------------------------------------------------------------
# detect_shots
# ---------------------------------------------------------------------------

MOCK_SHOTS = [
    {"shot_index": 0, "timecode": "00:00:00:00", "frame_number": 0, "seconds": 0.0},
    {"shot_index": 1, "timecode": "00:00:05:00", "frame_number": 125, "seconds": 5.0},
]
MOCK_VIDEO_INFO = (1500, 25.0)


class TestDetectShotsTool:

    def test_returns_dict(self):
        """detect_shots returns a dict."""
        with (
            patch("mcp_server.detect_scenes", return_value=MOCK_SHOTS),
            patch("mcp_server.get_video_info", return_value=MOCK_VIDEO_INFO),
        ):
            import mcp_server
            result = mcp_server.detect_shots("/fake/video.mp4")
        assert isinstance(result, dict)

    def test_result_has_shots_key(self):
        with (
            patch("mcp_server.detect_scenes", return_value=MOCK_SHOTS),
            patch("mcp_server.get_video_info", return_value=MOCK_VIDEO_INFO),
        ):
            import mcp_server
            result = mcp_server.detect_shots("/fake/video.mp4")
        assert "shots" in result
        assert len(result["shots"]) == 2

    def test_result_has_video_info(self):
        with (
            patch("mcp_server.detect_scenes", return_value=MOCK_SHOTS),
            patch("mcp_server.get_video_info", return_value=MOCK_VIDEO_INFO),
        ):
            import mcp_server
            result = mcp_server.detect_shots("/fake/video.mp4")
        assert "video_info" in result
        assert result["video_info"]["fps"] == 25.0

    def test_result_has_shot_count(self):
        with (
            patch("mcp_server.detect_scenes", return_value=MOCK_SHOTS),
            patch("mcp_server.get_video_info", return_value=MOCK_VIDEO_INFO),
        ):
            import mcp_server
            result = mcp_server.detect_shots("/fake/video.mp4")
        assert result["shot_count"] == 2

    def test_returns_error_on_value_error(self):
        """detect_shots returns {'error': ...} when detect_scenes raises ValueError."""
        with patch("mcp_server.detect_scenes", side_effect=ValueError("file not found")):
            import mcp_server
            result = mcp_server.detect_shots("/nonexistent/video.mp4")
        assert "error" in result
        assert "file not found" in result["error"]

    def test_returns_error_on_unexpected_exception(self):
        """detect_shots returns {'error': ...} on any unexpected exception."""
        with patch("mcp_server.detect_scenes", side_effect=RuntimeError("codec error")):
            import mcp_server
            result = mcp_server.detect_shots("/fake/video.mp4")
        assert "error" in result


# ---------------------------------------------------------------------------
# match_shotlist
# ---------------------------------------------------------------------------

MOCK_RESULTS = [
    {
        "shot_index": 0, "timecode": "00:00:00:00", "frame_number": 0, "seconds": 0.0,
        "matched_entry": 1, "matched_description": "VARIOUS OF ARTEMIS I",
        "confidence": "high", "notes": "Clear match.",
    },
]
SIMPLE_SHOTLIST = "1. VARIOUS OF ARTEMIS I AS IT TAKES OFF"


class TestMatchShotlistTool:

    def _patch_all(self, shots=None, results=None):
        """Return a context-manager stack patching all heavy dependencies."""
        shots = shots or MOCK_SHOTS
        results = results or MOCK_RESULTS

        mock_matcher = MagicMock()
        mock_matcher.match.return_value = [dict(r) for r in results]

        return (
            patch("mcp_server.detect_scenes", return_value=shots),
            patch("mcp_server.parse_shotlist", return_value=[
                {"entry_number": 1, "description": "VARIOUS OF ARTEMIS I",
                 "is_various": True, "is_soundbite": False,
                 "location_block": "", "raw": "1. VARIOUS OF ARTEMIS I"},
            ]),
            patch("mcp_server.OAMatcher", return_value=mock_matcher),
            # extract_frames is imported inside the function body, so patch
            # it at its source module rather than on mcp_server.
            patch("frame_extractor.extract_frames", side_effect=lambda vp, s, d: s),
        )

    def test_returns_dict(self):
        import mcp_server
        patches = self._patch_all()
        with patches[0], patches[1], patches[2], patches[3]:
            result = mcp_server.match_shotlist(
                video_path="/fake/video.mp4",
                shotlist_text=SIMPLE_SHOTLIST,
                esso_token="tok",
                workflow_id="wf-uuid",
            )
        assert isinstance(result, dict)

    def test_result_has_results_key(self):
        import mcp_server
        patches = self._patch_all()
        with patches[0], patches[1], patches[2], patches[3]:
            result = mcp_server.match_shotlist(
                video_path="/fake/video.mp4",
                shotlist_text=SIMPLE_SHOTLIST,
                esso_token="tok",
                workflow_id="wf-uuid",
            )
        assert "results" in result
        assert isinstance(result["results"], list)

    def test_result_has_csv_key(self):
        import mcp_server
        patches = self._patch_all()
        with patches[0], patches[1], patches[2], patches[3]:
            result = mcp_server.match_shotlist(
                video_path="/fake/video.mp4",
                shotlist_text=SIMPLE_SHOTLIST,
                esso_token="tok",
                workflow_id="wf-uuid",
            )
        assert "csv" in result
        assert "shot_index" in result["csv"]  # CSV header present

    def test_result_has_summary_key(self):
        import mcp_server
        patches = self._patch_all()
        with patches[0], patches[1], patches[2], patches[3]:
            result = mcp_server.match_shotlist(
                video_path="/fake/video.mp4",
                shotlist_text=SIMPLE_SHOTLIST,
                esso_token="tok",
                workflow_id="wf-uuid",
            )
        assert "summary" in result
        assert "total_shots" in result["summary"]
        assert "matched" in result["summary"]

    def test_returns_error_on_empty_shotlist(self):
        import mcp_server
        with patch("mcp_server.detect_scenes", return_value=MOCK_SHOTS):
            result = mcp_server.match_shotlist(
                video_path="/fake/video.mp4",
                shotlist_text="no entries here",
                esso_token="tok",
                workflow_id="wf-uuid",
            )
        assert "error" in result

    def test_returns_error_on_esso_expired(self):
        import mcp_server
        mock_matcher = MagicMock()
        mock_matcher.match.side_effect = RuntimeError("ESSO_TOKEN_EXPIRED: HTTP 401")
        patches = self._patch_all()
        with patches[0], patches[1], patch("mcp_server.OAMatcher", return_value=mock_matcher), patches[3]:
            result = mcp_server.match_shotlist(
                video_path="/fake/video.mp4",
                shotlist_text=SIMPLE_SHOTLIST,
                esso_token="expired",
                workflow_id="wf-uuid",
            )
        assert "error" in result
        assert "ESSO_TOKEN_EXPIRED" in result["error"]