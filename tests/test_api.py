"""
Tests for api.py — FastAPI endpoints.

Uses FastAPI's TestClient with unittest.mock to isolate all external
dependencies (scene_detector, OAMatcher, frame_extractor). No real video
file or Open Arena calls are made.
"""
import json
import os
import sys
import time
import tempfile
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# --- Shared mock data ---

MOCK_SHOTS = [
    {"shot_index": 0, "timecode": "00:00:00:00", "frame_number": 0, "seconds": 0.0},
    {"shot_index": 1, "timecode": "00:00:05:12", "frame_number": 137, "seconds": 5.48},
]

MOCK_VIDEO_INFO = (1500, 25.0)  # (total_frames, fps)

MOCK_RESULTS = [
    {
        "shot_index": 0, "timecode": "00:00:00:00", "frame_number": 0, "seconds": 0.0,
        "matched_entry": 1, "matched_description": "VARIOUS OF ARTEMIS I",
        "confidence": "high", "notes": "Clear match.",
    },
    {
        "shot_index": 1, "timecode": "00:00:05:12", "frame_number": 137, "seconds": 5.48,
        "matched_entry": 2, "matched_description": "VARIOUS OF MOON SURFACE",
        "confidence": "medium", "notes": "Probable match.",
    },
]

SIMPLE_SHOTLIST = "1. VARIOUS OF ARTEMIS I\n2. VARIOUS OF MOON SURFACE"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    """Return a TestClient with all heavy dependencies mocked."""
    with (
        patch("api.detect_scenes", return_value=MOCK_SHOTS),
        patch("api.get_video_info", return_value=MOCK_VIDEO_INFO),
        patch("api.extract_frames", side_effect=lambda vp, shots, d: shots),
        patch("api.OAMatcher") as MockMatcher,
    ):
        matcher_instance = MagicMock()
        matcher_instance.match.return_value = [dict(r) for r in MOCK_RESULTS]
        MockMatcher.return_value = matcher_instance

        from api import app, _jobs, limiter
        _jobs.clear()
        # Reset rate-limiter storage so per-IP counters don't bleed between tests
        limiter.reset()

        with TestClient(app) as c:
            yield c, _jobs


# ---------------------------------------------------------------------------
# /detect
# ---------------------------------------------------------------------------

class TestDetectEndpoint:

    def test_detect_returns_200(self, client):
        c, _ = client
        resp = c.post("/detect", json={"video_path": "/fake/video.mp4"})
        assert resp.status_code == 200

    def test_detect_returns_job_id(self, client):
        c, _ = client
        data = c.post("/detect", json={"video_path": "/fake/video.mp4"}).json()
        assert "job_id" in data
        assert len(data["job_id"]) == 36  # UUID format

    def test_detect_returns_shots(self, client):
        c, _ = client
        data = c.post("/detect", json={"video_path": "/fake/video.mp4"}).json()
        assert "shots" in data
        assert len(data["shots"]) == 2
        assert data["shots"][0]["timecode"] == "00:00:00:00"

    def test_detect_returns_video_info(self, client):
        c, _ = client
        data = c.post("/detect", json={"video_path": "/fake/video.mp4"}).json()
        assert "video_info" in data
        assert data["video_info"]["fps"] == 25.0
        assert data["video_info"]["total_frames"] == 1500

    def test_detect_returns_shot_count(self, client):
        c, _ = client
        data = c.post("/detect", json={"video_path": "/fake/video.mp4"}).json()
        assert data["shot_count"] == 2

    def test_detect_stores_job(self, client):
        c, jobs = client
        data = c.post("/detect", json={"video_path": "/fake/video.mp4"}).json()
        assert data["job_id"] in jobs

    def test_detect_400_on_value_error(self, client):
        """Returns 400 when detect_scenes raises ValueError."""
        c, _ = client
        with patch("api.detect_scenes", side_effect=ValueError("Video not found")):
            resp = c.post("/detect", json={"video_path": "/nonexistent.mp4"})
        assert resp.status_code == 400
        assert "Video not found" in resp.json()["detail"]

    def test_detect_502_on_unexpected_error(self, client):
        """Returns 502 when detect_scenes raises an unexpected exception."""
        c, _ = client
        with patch("api.detect_scenes", side_effect=RuntimeError("codec error")):
            resp = c.post("/detect", json={"video_path": "/fake/video.mp4"})
        assert resp.status_code == 502

    def test_detect_uses_custom_threshold(self, client):
        """Custom threshold is passed through to detect_scenes."""
        c, _ = client
        with patch("api.detect_scenes", return_value=MOCK_SHOTS) as mock_detect:
            with patch("api.get_video_info", return_value=MOCK_VIDEO_INFO):
                c.post("/detect", json={"video_path": "/fake/video.mp4", "threshold": 3.5})
                call_kwargs = mock_detect.call_args
                assert call_kwargs.kwargs.get("threshold") == 3.5 or call_kwargs.args[1] == 3.5


# ---------------------------------------------------------------------------
# /match
# ---------------------------------------------------------------------------

class TestMatchEndpoint:

    def _detect_and_get_job(self, client):
        """Helper: run /detect and return (job_id, jobs dict)."""
        c, jobs = client
        data = c.post("/detect", json={"video_path": "/fake/video.mp4"}).json()
        return data["job_id"], jobs

    def test_match_returns_200(self, client):
        c, jobs = client
        job_id, _ = self._detect_and_get_job(client)
        resp = c.post("/match", json={
            "job_id": job_id,
            "video_path": "/fake/video.mp4",
            "shotlist_text": SIMPLE_SHOTLIST,
            "esso_token": "tok",
            "workflow_id": "wf-uuid",
        })
        assert resp.status_code == 200

    def test_match_returns_results(self, client):
        c, _ = client
        job_id, _ = self._detect_and_get_job(client)
        data = c.post("/match", json={
            "job_id": job_id,
            "video_path": "/fake/video.mp4",
            "shotlist_text": SIMPLE_SHOTLIST,
            "esso_token": "tok",
            "workflow_id": "wf-uuid",
        }).json()
        assert "results" in data
        assert len(data["results"]) == 2

    def test_match_results_have_required_fields(self, client):
        c, _ = client
        job_id, _ = self._detect_and_get_job(client)
        data = c.post("/match", json={
            "job_id": job_id,
            "video_path": "/fake/video.mp4",
            "shotlist_text": SIMPLE_SHOTLIST,
            "esso_token": "tok",
            "workflow_id": "wf-uuid",
        }).json()
        for r in data["results"]:
            assert "timecode" in r
            assert "matched_entry" in r
            assert "confidence" in r

    def test_match_reuses_cached_shots(self, client):
        """When job_id is provided, detect_scenes is not called again."""
        c, _ = client
        job_id, _ = self._detect_and_get_job(client)
        with patch("api.detect_scenes") as mock_detect:
            c.post("/match", json={
                "job_id": job_id,
                "video_path": "/fake/video.mp4",
                "shotlist_text": SIMPLE_SHOTLIST,
                "esso_token": "tok",
                "workflow_id": "wf-uuid",
            })
            mock_detect.assert_not_called()

    def test_match_without_job_id_runs_detection(self, client):
        """Without job_id, /match runs its own scene detection."""
        c, _ = client
        with patch("api.detect_scenes", return_value=MOCK_SHOTS) as mock_detect:
            with patch("api.get_video_info", return_value=MOCK_VIDEO_INFO):
                resp = c.post("/match", json={
                    "video_path": "/fake/video.mp4",
                    "shotlist_text": SIMPLE_SHOTLIST,
                    "esso_token": "tok",
                    "workflow_id": "wf-uuid",
                })
                mock_detect.assert_called_once()
        assert resp.status_code == 200

    def test_match_400_on_empty_shotlist(self, client):
        """Returns 400 when shotlist has no parseable entries."""
        c, _ = client
        job_id, _ = self._detect_and_get_job(client)
        resp = c.post("/match", json={
            "job_id": job_id,
            "video_path": "/fake/video.mp4",
            "shotlist_text": "no entries here",
            "esso_token": "tok",
            "workflow_id": "wf-uuid",
        })
        assert resp.status_code == 400

    def test_match_401_on_expired_token(self, client):
        """Returns 401 when OAMatcher raises ESSO_TOKEN_EXPIRED."""
        c, _ = client
        job_id, _ = self._detect_and_get_job(client)
        with patch("api.OAMatcher") as MockM:
            instance = MagicMock()
            instance.match.side_effect = RuntimeError("ESSO_TOKEN_EXPIRED: HTTP 401")
            MockM.return_value = instance
            resp = c.post("/match", json={
                "job_id": job_id,
                "video_path": "/fake/video.mp4",
                "shotlist_text": SIMPLE_SHOTLIST,
                "esso_token": "expired",
                "workflow_id": "wf-uuid",
            })
        assert resp.status_code == 401
        assert "ESSO_TOKEN_EXPIRED" in resp.json()["detail"]

    def test_match_502_on_oa_failure(self, client):
        """Returns 502 when OAMatcher raises a generic RuntimeError."""
        c, _ = client
        job_id, _ = self._detect_and_get_job(client)
        with patch("api.OAMatcher") as MockM:
            instance = MagicMock()
            instance.match.side_effect = RuntimeError("Connection refused on all URLs")
            MockM.return_value = instance
            resp = c.post("/match", json={
                "job_id": job_id,
                "video_path": "/fake/video.mp4",
                "shotlist_text": SIMPLE_SHOTLIST,
                "esso_token": "tok",
                "workflow_id": "wf-uuid",
            })
        assert resp.status_code == 502

    def test_match_thumbnail_urls_in_results(self, client):
        """frame_path is replaced with thumbnail_url in the response."""
        c, _ = client
        job_id, _ = self._detect_and_get_job(client)
        # Return shots with frame_path set
        shots_with_path = [
            {**MOCK_RESULTS[0], "frame_path": "/tmp/shot_0000.jpg"},
            {**MOCK_RESULTS[1], "frame_path": "/tmp/shot_0001.jpg"},
        ]
        with patch("api.OAMatcher") as MockM:
            instance = MagicMock()
            instance.match.return_value = shots_with_path
            MockM.return_value = instance
            data = c.post("/match", json={
                "job_id": job_id,
                "video_path": "/fake/video.mp4",
                "shotlist_text": SIMPLE_SHOTLIST,
                "esso_token": "tok",
                "workflow_id": "wf-uuid",
            }).json()

        for r in data["results"]:
            assert "frame_path" not in r
            assert "thumbnail_url" in r
            assert r["thumbnail_url"].startswith("/thumbnails/")


# ---------------------------------------------------------------------------
# /export
# ---------------------------------------------------------------------------

class TestExportEndpoint:

    def _setup_job_with_results(self, client):
        """Run /detect then /match to populate a job with results."""
        c, jobs = client
        job_id, _ = self._detect_job(client)
        c.post("/match", json={
            "job_id": job_id,
            "video_path": "/fake/video.mp4",
            "shotlist_text": SIMPLE_SHOTLIST,
            "esso_token": "tok",
            "workflow_id": "wf-uuid",
        })
        return job_id

    def _detect_job(self, client):
        c, jobs = client
        data = c.post("/detect", json={"video_path": "/fake/video.mp4"}).json()
        return data["job_id"], jobs

    def test_export_csv_200(self, client):
        c, _ = client
        job_id = self._setup_job_with_results(client)
        resp = c.get(f"/export/{job_id}?format=csv")
        assert resp.status_code == 200

    def test_export_csv_content_type(self, client):
        c, _ = client
        job_id = self._setup_job_with_results(client)
        resp = c.get(f"/export/{job_id}?format=csv")
        assert "text/csv" in resp.headers["content-type"]

    def test_export_csv_has_header_row(self, client):
        c, _ = client
        job_id = self._setup_job_with_results(client)
        content = c.get(f"/export/{job_id}?format=csv").text
        first_line = content.splitlines()[0]
        assert "shot_index" in first_line
        assert "timecode" in first_line
        assert "confidence" in first_line

    def test_export_csv_data_rows(self, client):
        c, _ = client
        job_id = self._setup_job_with_results(client)
        content = c.get(f"/export/{job_id}?format=csv").text
        lines = [l for l in content.splitlines() if l.strip()]
        # header + 2 data rows
        assert len(lines) == 3

    def test_export_json_200(self, client):
        c, _ = client
        job_id = self._setup_job_with_results(client)
        resp = c.get(f"/export/{job_id}?format=json")
        assert resp.status_code == 200

    def test_export_json_is_valid(self, client):
        c, _ = client
        job_id = self._setup_job_with_results(client)
        resp = c.get(f"/export/{job_id}?format=json")
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2

    def test_export_txt_200(self, client):
        c, _ = client
        job_id = self._setup_job_with_results(client)
        resp = c.get(f"/export/{job_id}?format=txt")
        assert resp.status_code == 200

    def test_export_txt_contains_timecodes(self, client):
        c, _ = client
        job_id = self._setup_job_with_results(client)
        content = c.get(f"/export/{job_id}?format=txt").text
        assert "00:00:00:00" in content

    def test_export_default_is_csv(self, client):
        c, _ = client
        job_id = self._setup_job_with_results(client)
        resp = c.get(f"/export/{job_id}")
        assert "text/csv" in resp.headers["content-type"]

    def test_export_404_no_results(self, client):
        """Export on a job with no results yet returns 404."""
        c, jobs = client
        job_id, _ = self._detect_job(client)
        resp = c.get(f"/export/{job_id}?format=csv")
        assert resp.status_code == 404

    def test_export_404_unknown_job(self, client):
        c, _ = client
        resp = c.get("/export/nonexistent-job-id?format=csv")
        assert resp.status_code == 404

    def test_export_disposition_header(self, client):
        """Content-Disposition header includes the job_id and correct extension."""
        c, _ = client
        job_id = self._setup_job_with_results(client)
        resp = c.get(f"/export/{job_id}?format=csv")
        disp = resp.headers.get("content-disposition", "")
        assert job_id in disp
        assert ".csv" in disp


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

class TestRateLimiting:
    """Verify that /detect and /match enforce per-IP rate limits."""

    def _fresh_client(self):
        """Return a new TestClient with a reset limiter (avoids fixture-level reset)."""
        from api import app, _jobs, limiter
        _jobs.clear()
        limiter.reset()
        return TestClient(app)

    def test_detect_rate_limit_returns_429_after_limit(self, client):
        """POST /detect must return 429 once the per-minute limit is exceeded."""
        c, _ = client
        from api import _CFG
        limit = int(_CFG.get("rate_limits", {}).get("detect", "10/minute").split("/")[0])
        # Exhaust the limit
        for _ in range(limit):
            resp = c.post("/detect", json={"video_path": "/fake/video.mp4"})
            assert resp.status_code == 200, f"Expected 200 before limit, got {resp.status_code}"
        # The next request must be rate-limited
        over = c.post("/detect", json={"video_path": "/fake/video.mp4"})
        assert over.status_code == 429, f"Expected 429 after limit, got {over.status_code}"

    def test_match_rate_limit_returns_429_after_limit(self, client):
        """POST /match must return 429 once the per-minute limit is exceeded."""
        c, _ = client
        from api import _CFG, _jobs, limiter
        limit = int(_CFG.get("rate_limits", {}).get("match", "5/minute").split("/")[0])

        # Create a single detect job to reuse (avoids hitting /detect limit)
        detect_resp = c.post("/detect", json={"video_path": "/fake/video.mp4"})
        job_id = detect_resp.json()["job_id"]

        match_body = {
            "job_id": job_id,
            "video_path": "/fake/video.mp4",
            "shotlist_text": SIMPLE_SHOTLIST,
            "esso_token": "tok",
            "workflow_id": "wf-uuid",
        }

        # Exhaust the match limit
        for _ in range(limit):
            resp = c.post("/match", json=match_body)
            assert resp.status_code == 200, f"Expected 200 before limit, got {resp.status_code}"

        # The next request must be rate-limited
        over = c.post("/match", json=match_body)
        assert over.status_code == 429, f"Expected 429 after limit, got {over.status_code}"

    def test_rate_limit_resets_between_fixtures(self, client):
        """The limiter is reset per-fixture; a fresh fixture should not be limited."""
        c, _ = client
        resp = c.post("/detect", json={"video_path": "/fake/video.mp4"})
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Job store / TTL
# ---------------------------------------------------------------------------

class TestJobStore:

    def test_expired_job_returns_404(self, client):
        """A job past its TTL is purged and returns 404 on export."""
        c, jobs = client
        data = c.post("/detect", json={"video_path": "/fake/video.mp4"}).json()
        job_id = data["job_id"]
        # Backdate the creation time beyond the TTL
        jobs[job_id]["created_at"] = time.time() - 7200  # 2 hours ago
        resp = c.get(f"/export/{job_id}?format=csv")
        assert resp.status_code == 404

    def test_multiple_jobs_independent(self, client):
        """Two consecutive /detect calls produce distinct job IDs."""
        c, _ = client
        id1 = c.post("/detect", json={"video_path": "/fake/a.mp4"}).json()["job_id"]
        id2 = c.post("/detect", json={"video_path": "/fake/b.mp4"}).json()["job_id"]
        assert id1 != id2
