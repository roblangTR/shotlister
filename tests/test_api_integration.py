"""
tests/test_api_integration.py — full HTTP flow integration test.

Exercises the complete detect → match → export → thumbnails pipeline
over real HTTP (via FastAPI TestClient) with only detect_scenes and
OAMatcher mocked — the HTTP layer, job store, CSV serialisation, and
thumbnail serving are all exercised for real.
"""
import csv
import io
import os
import shutil
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ---------------------------------------------------------------------------
# Shared mock data
# ---------------------------------------------------------------------------

MOCK_SHOTS_DETECT = [
    {"shot_index": 0, "timecode": "00:00:00:00", "frame_number": 0,   "seconds": 0.0},
    {"shot_index": 1, "timecode": "00:00:05:12", "frame_number": 137, "seconds": 5.48},
    {"shot_index": 2, "timecode": "00:00:11:03", "frame_number": 278, "seconds": 11.12},
]

MOCK_VIDEO_INFO = (750, 25.0)  # (total_frames, fps)

MOCK_MATCH_RESULTS = [
    {
        "shot_index": 0, "timecode": "00:00:00:00", "timecode_in": "00:00:00:00",
        "timecode_out": "00:00:05:12", "frame_number": 0, "seconds": 0.0,
        "matched_entry": 1, "matched_description": "VARIOUS OF ARTEMIS I AS IT TAKES OFF",
        "confidence": "high", "notes": "Rocket visible on launchpad.",
        "location": "CAPE CANAVERAL", "date": "NOVEMBER 16, 2022",
        "source": "NASA", "restrictions": "For editorial use only",
        "restrictions_broadcast": "For editorial use only",
        "restrictions_digital": "For editorial use only",
        "location_block": "CAPE CANAVERAL, FLORIDA",
    },
    {
        "shot_index": 1, "timecode": "00:00:05:12", "timecode_in": "00:00:05:12",
        "timecode_out": "00:00:11:03", "frame_number": 137, "seconds": 5.48,
        "matched_entry": 2, "matched_description": "VARIOUS OF MOON SURFACE",
        "confidence": "medium", "notes": "Moon surface visible.",
        "location": "IN SPACE", "date": "RECENT",
        "source": "NASA TV", "restrictions": "For editorial use only",
        "restrictions_broadcast": "For editorial use only",
        "restrictions_digital": "For editorial use only",
        "location_block": "IN SPACE",
    },
    {
        "shot_index": 2, "timecode": "00:00:11:03", "timecode_in": "00:00:11:03",
        "timecode_out": "00:00:30:00", "frame_number": 278, "seconds": 11.12,
        "matched_entry": 3, "matched_description": "(SOUNDBITE) DR LORI GLAZE SAYING",
        "confidence": "high", "notes": "Speaker visible, audio matches.",
        "location": "WASHINGTON D.C.", "date": "SEPTEMBER 12, 2025",
        "source": "REUTERS", "restrictions": "Access all",
        "restrictions_broadcast": "Access all",
        "restrictions_digital": "Access all",
        "location_block": "WASHINGTON D.C.",
    },
]

SIMPLE_SHOTLIST = (
    "CAPE CANAVERAL, FLORIDA (NOVEMBER 16, 2022) (NASA)\n"
    "1. VARIOUS OF ARTEMIS I AS IT TAKES OFF\n"
    "\n"
    "IN SPACE (RECENT) (NASA TV)\n"
    "2. VARIOUS OF MOON SURFACE\n"
    "\n"
    "WASHINGTON D.C. (SEPTEMBER 12, 2025) (REUTERS)\n"
    "3. (SOUNDBITE) DR LORI GLAZE SAYING: The Apollo missions...\n"
)

EXPECTED_CSV_HEADERS = {
    "shot_index", "timecode", "matched_entry",
    "matched_description", "confidence", "notes",
}


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def pipeline_client():
    """
    TestClient with detect_scenes and OAMatcher mocked.
    extract_frames is also mocked to avoid needing real video files,
    but returns shots with a real temp-file frame_path so that the
    thumbnails endpoint can be tested.
    """
    with tempfile.TemporaryDirectory() as thumb_dir:
        # Create fake thumbnail files so FileResponse can serve them
        fake_thumbs = []
        for i in range(len(MOCK_SHOTS_DETECT)):
            p = os.path.join(thumb_dir, f"shot_{i:04d}.jpg")
            # Write a minimal valid JPEG (1×1 white pixel)
            with open(p, "wb") as f:
                f.write(bytes([
                    0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
                    0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
                    0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
                    0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
                    0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
                    0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
                    0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
                    0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
                    0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
                    0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
                    0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
                    0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
                    0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
                    0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00, 0xFB, 0xD2,
                    0x8A, 0x00, 0xFF, 0xD9,
                ]))
            fake_thumbs.append(p)

        def mock_extract_frames(video_path, shots, output_dir, **kwargs):
            """
            Copy fake thumbnails into output_dir (the API's own temp dir) and
            return shots annotated with frame_paths inside that dir.

            The /thumbnails endpoint serves files from job["thumbnails_dir"]
            (which api.py sets to output_dir), so the paths must be inside it.
            """
            os.makedirs(output_dir, exist_ok=True)
            result = []
            for i, shot in enumerate(shots):
                s = dict(shot)
                if i < len(fake_thumbs):
                    dest = os.path.join(output_dir, f"shot_{i:04d}.jpg")
                    shutil.copy2(fake_thumbs[i], dest)
                    s["frame_path"] = dest
                result.append(s)
            return result

        def mock_matcher_match(video_path, shots, entries, file_uuid=None):
            """
            Simulate OAMatcher.match(): merge MOCK_MATCH_RESULTS fields into
            the shot dicts that extract_frames already annotated with frame_path.
            This mirrors the real implementation which mutates and returns the
            shots list passed in.
            """
            result = []
            for i, shot in enumerate(shots):
                merged = dict(shot)  # preserves frame_path from extract_frames
                if i < len(MOCK_MATCH_RESULTS):
                    merged.update(MOCK_MATCH_RESULTS[i])
                    # Restore frame_path if the template doesn't have it
                    if "frame_path" not in merged and "frame_path" in shot:
                        merged["frame_path"] = shot["frame_path"]
                result.append(merged)
            return result

        with (
            patch("api.detect_scenes", return_value=[dict(s) for s in MOCK_SHOTS_DETECT]),
            patch("api.get_video_info", return_value=MOCK_VIDEO_INFO),
            patch("api.extract_frames", side_effect=mock_extract_frames),
            patch("api.OAMatcher") as MockMatcher,
        ):
            matcher_instance = MagicMock()
            matcher_instance.match.side_effect = mock_matcher_match
            MockMatcher.return_value = matcher_instance

            from api import app, _jobs, limiter
            _jobs.clear()
            # Reset rate-limiter storage so per-IP counters don't bleed between tests
            limiter.reset()

            with TestClient(app) as client:
                yield client, _jobs


# ---------------------------------------------------------------------------
# Integration tests — full pipeline
# ---------------------------------------------------------------------------

class TestFullPipeline:
    """Exercises POST /detect → POST /match → GET /export → GET /thumbnails."""

    def _run_detect(self, client):
        resp = client.post("/detect", json={"video_path": "/fake/artemis.mp4"})
        assert resp.status_code == 200, f"/detect failed: {resp.text}"
        return resp.json()["job_id"]

    def _run_match(self, client, job_id):
        resp = client.post("/match", json={
            "job_id": job_id,
            "video_path": "/fake/artemis.mp4",
            "shotlist_text": SIMPLE_SHOTLIST,
            "esso_token": "test-token",
            "workflow_id": "ee360c20-9f8a-4fcd-95a1-ceacb4224cce",
        })
        assert resp.status_code == 200, f"/match failed: {resp.text}"
        return resp.json()

    # --- Step 1: /detect ---

    def test_detect_creates_job(self, pipeline_client):
        client, jobs = pipeline_client
        job_id = self._run_detect(client)
        assert job_id in jobs

    def test_detect_returns_three_shots(self, pipeline_client):
        client, _ = pipeline_client
        resp = client.post("/detect", json={"video_path": "/fake/artemis.mp4"})
        assert resp.json()["shot_count"] == 3

    def test_detect_returns_video_info(self, pipeline_client):
        client, _ = pipeline_client
        resp = client.post("/detect", json={"video_path": "/fake/artemis.mp4"})
        info = resp.json()["video_info"]
        assert info["fps"] == 25.0
        assert info["total_frames"] == 750

    # --- Step 2: /match ---

    def test_match_returns_three_results(self, pipeline_client):
        client, _ = pipeline_client
        job_id = self._run_detect(client)
        data = self._run_match(client, job_id)
        assert data["shot_count"] == 3
        assert len(data["results"]) == 3

    def test_match_results_have_required_fields(self, pipeline_client):
        client, _ = pipeline_client
        job_id = self._run_detect(client)
        data = self._run_match(client, job_id)
        for r in data["results"]:
            assert "shot_index"          in r
            assert "timecode"            in r
            assert "matched_entry"       in r
            assert "matched_description" in r
            assert "confidence"          in r
            assert "notes"               in r

    def test_match_confidence_values_valid(self, pipeline_client):
        client, _ = pipeline_client
        job_id = self._run_detect(client)
        data = self._run_match(client, job_id)
        valid = {"high", "medium", "low"}
        for r in data["results"]:
            assert r["confidence"] in valid

    def test_match_thumbnail_urls_present(self, pipeline_client):
        client, _ = pipeline_client
        job_id = self._run_detect(client)
        data = self._run_match(client, job_id)
        for r in data["results"]:
            assert "thumbnail_url" in r
            assert r["thumbnail_url"].startswith(f"/thumbnails/{job_id}/")

    def test_match_does_not_expose_frame_path(self, pipeline_client):
        client, _ = pipeline_client
        job_id = self._run_detect(client)
        data = self._run_match(client, job_id)
        for r in data["results"]:
            assert "frame_path" not in r

    def test_match_reuses_cached_shots(self, pipeline_client):
        """detect_scenes must not be called again when job_id is supplied."""
        client, _ = pipeline_client
        job_id = self._run_detect(client)
        with patch("api.detect_scenes") as mock_detect:
            self._run_match(client, job_id)
            mock_detect.assert_not_called()

    # --- Step 3: GET /export?format=csv ---

    def test_export_csv_status_200(self, pipeline_client):
        client, _ = pipeline_client
        job_id = self._run_detect(client)
        self._run_match(client, job_id)
        resp = client.get(f"/export/{job_id}?format=csv")
        assert resp.status_code == 200

    def test_export_csv_content_type(self, pipeline_client):
        client, _ = pipeline_client
        job_id = self._run_detect(client)
        self._run_match(client, job_id)
        resp = client.get(f"/export/{job_id}?format=csv")
        assert "text/csv" in resp.headers["content-type"]

    def test_export_csv_headers(self, pipeline_client):
        """CSV must contain the mandatory column headers."""
        client, _ = pipeline_client
        job_id = self._run_detect(client)
        self._run_match(client, job_id)
        content = client.get(f"/export/{job_id}?format=csv").text
        reader = csv.DictReader(io.StringIO(content))
        fieldnames = set(reader.fieldnames or [])
        assert EXPECTED_CSV_HEADERS.issubset(fieldnames), (
            f"Missing headers: {EXPECTED_CSV_HEADERS - fieldnames}"
        )

    def test_export_csv_data_rows(self, pipeline_client):
        """CSV must have exactly 3 data rows (one per shot)."""
        client, _ = pipeline_client
        job_id = self._run_detect(client)
        self._run_match(client, job_id)
        content = client.get(f"/export/{job_id}?format=csv").text
        rows = list(csv.DictReader(io.StringIO(content)))
        assert len(rows) == 3

    def test_export_csv_timecodes_correct(self, pipeline_client):
        """First data row timecode must match the first detected shot."""
        client, _ = pipeline_client
        job_id = self._run_detect(client)
        self._run_match(client, job_id)
        content = client.get(f"/export/{job_id}?format=csv").text
        rows = list(csv.DictReader(io.StringIO(content)))
        assert rows[0]["timecode"] == "00:00:00:00"
        assert rows[1]["timecode"] == "00:00:05:12"
        assert rows[2]["timecode"] == "00:00:11:03"

    def test_export_csv_matched_entries_correct(self, pipeline_client):
        """matched_entry values must be 1, 2, 3 for the three shots."""
        client, _ = pipeline_client
        job_id = self._run_detect(client)
        self._run_match(client, job_id)
        content = client.get(f"/export/{job_id}?format=csv").text
        rows = list(csv.DictReader(io.StringIO(content)))
        assert rows[0]["matched_entry"] == "1"
        assert rows[1]["matched_entry"] == "2"
        assert rows[2]["matched_entry"] == "3"

    def test_export_csv_descriptions_present(self, pipeline_client):
        """matched_description cells must be non-empty."""
        client, _ = pipeline_client
        job_id = self._run_detect(client)
        self._run_match(client, job_id)
        content = client.get(f"/export/{job_id}?format=csv").text
        rows = list(csv.DictReader(io.StringIO(content)))
        for row in rows:
            assert row["matched_description"].strip() != ""

    def test_export_csv_confidence_values_valid(self, pipeline_client):
        """All confidence values in CSV must be high/medium/low."""
        client, _ = pipeline_client
        job_id = self._run_detect(client)
        self._run_match(client, job_id)
        content = client.get(f"/export/{job_id}?format=csv").text
        rows = list(csv.DictReader(io.StringIO(content)))
        valid = {"high", "medium", "low"}
        for row in rows:
            assert row["confidence"] in valid

    # --- Step 4: GET /thumbnails ---

    def test_thumbnails_returns_200(self, pipeline_client):
        client, _ = pipeline_client
        job_id = self._run_detect(client)
        data = self._run_match(client, job_id)
        # Use the first thumbnail URL from the match response
        thumb_url = data["results"][0]["thumbnail_url"]
        resp = client.get(thumb_url)
        assert resp.status_code == 200

    def test_thumbnails_content_type_jpeg(self, pipeline_client):
        client, _ = pipeline_client
        job_id = self._run_detect(client)
        data = self._run_match(client, job_id)
        thumb_url = data["results"][0]["thumbnail_url"]
        resp = client.get(thumb_url)
        assert "image/jpeg" in resp.headers["content-type"]

    def test_thumbnails_unknown_file_returns_404(self, pipeline_client):
        client, _ = pipeline_client
        job_id = self._run_detect(client)
        self._run_match(client, job_id)
        resp = client.get(f"/thumbnails/{job_id}/nonexistent.jpg")
        assert resp.status_code == 404

    def test_thumbnails_unknown_job_returns_404(self, pipeline_client):
        client, _ = pipeline_client
        resp = client.get("/thumbnails/deadbeef-0000-0000-0000-000000000000/shot_0000.jpg")
        assert resp.status_code == 404

    # --- Cross-cutting: export before match returns 404 ---

    def test_export_before_match_returns_404(self, pipeline_client):
        """Exporting a job that has not been matched yet must return 404."""
        client, _ = pipeline_client
        job_id = self._run_detect(client)
        resp = client.get(f"/export/{job_id}?format=csv")
        assert resp.status_code == 404
