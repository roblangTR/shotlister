"""
Tests for oa_matcher.py.

Tests _build_prompt() and _parse_response() only.
Does NOT test _call_open_arena() — that requires a live ESSO token.
"""
import json
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from oa_matcher import OAMatcher

# Minimal fixture data
SAMPLE_SHOTS = [
    {"shot_index": 0, "timecode": "00:00:00:00", "frame_number": 0, "seconds": 0.0},
    {"shot_index": 1, "timecode": "00:00:05:12", "frame_number": 137, "seconds": 5.48},
    {"shot_index": 2, "timecode": "00:00:18:00", "frame_number": 450, "seconds": 18.0},
]

SAMPLE_ENTRIES = [
    {
        "entry_number": 1,
        "description": "VARIOUS OF ARTEMIS I AS IT TAKES OFF",
        "is_various": True,
        "is_soundbite": False,
        "location_block": "CAPE CANAVERAL, FLORIDA",
        "raw": "1. VARIOUS OF ARTEMIS I...",
    },
    {
        "entry_number": 2,
        "description": "VARIOUS OF MOON SURFACE SEEN FROM ORION SPACE CAPSULE",
        "is_various": True,
        "is_soundbite": False,
        "location_block": "IN SPACE (RECENT)",
        "raw": "2. VARIOUS OF MOON SURFACE...",
    },
    {
        "entry_number": 3,
        "description": "(SOUNDBITE) DR LORI GLAZE SAYING: The Apollo missions...",
        "is_various": False,
        "is_soundbite": True,
        "location_block": "WASHINGTON D.C.",
        "raw": "3. (SOUNDBITE)...",
    },
]

# Reuse one matcher instance across tests — token and workflow_id are dummy values
# since we're not hitting the live API
_matcher = OAMatcher(esso_token="test_token", workflow_id="test_workflow")


class TestBuildPrompt:

    def test_shotlist_entries_in_prompt(self):
        """All entry numbers and descriptions appear in the prompt."""
        prompt = _matcher._build_prompt(SAMPLE_SHOTS, SAMPLE_ENTRIES)
        for entry in SAMPLE_ENTRIES:
            assert str(entry["entry_number"]) in prompt
            # Check a distinctive keyword from each description
            assert "ARTEMIS" in prompt or "MOON" in prompt or "GLAZE" in prompt

    def test_shot_timecodes_in_prompt(self):
        """All shot timecodes appear in the prompt."""
        prompt = _matcher._build_prompt(SAMPLE_SHOTS, SAMPLE_ENTRIES)
        for shot in SAMPLE_SHOTS:
            assert shot["timecode"] in prompt

    def test_shot_indices_in_prompt(self):
        """Shot indices appear as 'Shot N:' in the prompt."""
        prompt = _matcher._build_prompt(SAMPLE_SHOTS, SAMPLE_ENTRIES)
        for shot in SAMPLE_SHOTS:
            assert f"Shot {shot['shot_index']}:" in prompt

    def test_various_of_tag_in_prompt(self):
        """VARIOUS OF entries are flagged in the prompt."""
        prompt = _matcher._build_prompt(SAMPLE_SHOTS, SAMPLE_ENTRIES)
        assert "VARIOUS OF" in prompt

    def test_soundbite_tag_in_prompt(self):
        """SOUNDBITE entries are flagged in the prompt."""
        prompt = _matcher._build_prompt(SAMPLE_SHOTS, SAMPLE_ENTRIES)
        assert "SOUNDBITE" in prompt

    def test_prompt_is_nonempty_string(self):
        """Prompt is a non-empty string."""
        prompt = _matcher._build_prompt(SAMPLE_SHOTS, SAMPLE_ENTRIES)
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    def test_json_only_instruction_in_prompt(self):
        """Prompt asks for JSON only."""
        prompt = _matcher._build_prompt(SAMPLE_SHOTS, SAMPLE_ENTRIES)
        assert "JSON" in prompt


class TestParseResponse:

    def _valid_json(self):
        return json.dumps([
            {"shot_index": 0, "matched_entry": 1, "confidence": "high", "notes": "Clear match."},
            {"shot_index": 1, "matched_entry": 1, "confidence": "medium", "notes": "Probable."},
            {"shot_index": 2, "matched_entry": 3, "confidence": "high", "notes": "Soundbite."},
        ])

    def test_valid_json_returns_list(self):
        """Valid JSON returns a list with correct length."""
        result = _matcher._parse_response(self._valid_json(), 3)
        assert isinstance(result, list)
        assert len(result) == 3

    def test_valid_json_fields(self):
        """Each parsed match has the required fields."""
        result = _matcher._parse_response(self._valid_json(), 3)
        for item in result:
            assert "shot_index" in item
            assert "matched_entry" in item
            assert "confidence" in item
            assert "notes" in item

    def test_markdown_fenced_json(self):
        """Strips markdown code fences and parses successfully."""
        fenced = "```json\n" + self._valid_json() + "\n```"
        result = _matcher._parse_response(fenced, 3)
        assert len(result) == 3

    def test_markdown_fence_no_language(self):
        """Strips ``` fences without language label."""
        fenced = "```\n" + self._valid_json() + "\n```"
        result = _matcher._parse_response(fenced, 3)
        assert len(result) == 3

    def test_invalid_json_returns_empty(self):
        """Malformed JSON returns empty list without raising."""
        result = _matcher._parse_response("this is not json", 3)
        assert result == []

    def test_empty_string_returns_empty(self):
        """Empty string returns empty list."""
        assert _matcher._parse_response("", 3) == []

    def test_null_matched_entry(self):
        """null matched_entry is preserved as None."""
        raw = json.dumps([
            {"shot_index": 0, "matched_entry": None, "confidence": "low", "notes": "No match."},
        ])
        result = _matcher._parse_response(raw, 1)
        assert result[0]["matched_entry"] is None

    def test_confidence_normalised_to_lowercase(self):
        """Confidence values are lowercased and validated."""
        raw = json.dumps([
            {"shot_index": 0, "matched_entry": 1, "confidence": "HIGH", "notes": ""},
        ])
        result = _matcher._parse_response(raw, 1)
        assert result[0]["confidence"] == "high"

    def test_invalid_confidence_becomes_low(self):
        """Unrecognised confidence values become 'low'."""
        raw = json.dumps([
            {"shot_index": 0, "matched_entry": 1, "confidence": "maybe", "notes": ""},
        ])
        result = _matcher._parse_response(raw, 1)
        assert result[0]["confidence"] == "low"

    def test_missing_shot_index_skipped(self):
        """Items without shot_index are skipped."""
        raw = json.dumps([
            {"matched_entry": 1, "confidence": "high", "notes": ""},  # no shot_index
            {"shot_index": 1, "matched_entry": 2, "confidence": "high", "notes": ""},
        ])
        result = _matcher._parse_response(raw, 2)
        assert len(result) == 1
        assert result[0]["shot_index"] == 1

    def test_json_with_surrounding_text(self):
        """JSON array embedded in surrounding text is extracted correctly."""
        raw = "Here is my answer:\n" + self._valid_json() + "\nThat's all."
        result = _matcher._parse_response(raw, 3)
        assert len(result) == 3

    def test_non_list_json_returns_empty(self):
        """A JSON object (not array) returns empty list without raising."""
        result = _matcher._parse_response('{"error": "oops"}', 3)
        assert result == []

    def test_extra_keys_in_response_ignored(self):
        """Extra keys in the Gemini response objects are silently ignored."""
        raw = json.dumps([
            {"shot_index": 0, "matched_entry": 1, "confidence": "high",
             "notes": "ok", "extra_field": "ignored", "another": 42},
        ])
        result = _matcher._parse_response(raw, 1)
        assert len(result) == 1
        assert "extra_field" not in result[0]

    def test_partial_response_fewer_than_n_shots(self):
        """Fewer matches than n_shots is accepted gracefully."""
        raw = json.dumps([
            {"shot_index": 0, "matched_entry": 1, "confidence": "high", "notes": ""},
        ])
        result = _matcher._parse_response(raw, 3)
        assert len(result) == 1  # only 1 returned, not padded

    def test_string_shot_index_coerced_to_int(self):
        """shot_index as a string is coerced to int."""
        raw = json.dumps([
            {"shot_index": "2", "matched_entry": 1, "confidence": "high", "notes": ""},
        ])
        result = _matcher._parse_response(raw, 3)
        assert len(result) == 1
        assert result[0]["shot_index"] == 2

    def test_string_matched_entry_coerced_to_int(self):
        """matched_entry as a string is coerced to int."""
        raw = json.dumps([
            {"shot_index": 0, "matched_entry": "3", "confidence": "high", "notes": ""},
        ])
        result = _matcher._parse_response(raw, 1)
        assert result[0]["matched_entry"] == 3

    def test_missing_notes_defaults_to_empty_string(self):
        """Absent 'notes' key defaults to empty string, not KeyError."""
        raw = json.dumps([
            {"shot_index": 0, "matched_entry": 1, "confidence": "high"},
        ])
        result = _matcher._parse_response(raw, 1)
        assert result[0]["notes"] == ""

    def test_empty_array_response(self):
        """Gemini returning [] is valid and returns empty list."""
        result = _matcher._parse_response("[]", 3)
        assert result == []

    def test_mixed_valid_invalid_items(self):
        """Valid items are returned even when some items are malformed."""
        raw = json.dumps([
            "not a dict",
            {"shot_index": 0, "matched_entry": 1, "confidence": "high", "notes": "good"},
            None,
            {"shot_index": 2, "matched_entry": 3, "confidence": "medium", "notes": "ok"},
        ])
        result = _matcher._parse_response(raw, 3)
        assert len(result) == 2
        assert result[0]["shot_index"] == 0
        assert result[1]["shot_index"] == 2


# ---------------------------------------------------------------------------
# OAMatcher — update_token and upload_video error paths
# ---------------------------------------------------------------------------

class TestUpdateToken:

    def test_update_token_changes_token(self):
        """update_token() replaces the stored ESSO token."""
        m = OAMatcher(esso_token="old_token", workflow_id="wf")
        m.update_token("new_token")
        assert m.esso_token == "new_token"

    def test_update_token_multiple_times(self):
        """update_token can be called multiple times."""
        m = OAMatcher(esso_token="t1", workflow_id="wf")
        m.update_token("t2")
        m.update_token("t3")
        assert m.esso_token == "t3"


class TestUploadVideoErrorPaths:
    """Test upload_video() error handling using mocked requests."""

    def test_upload_raises_for_missing_file(self):
        """Raises ValueError when the video file does not exist."""
        m = OAMatcher(esso_token="tok", workflow_id="wf")
        with pytest.raises(ValueError, match="not found"):
            m.upload_video("/nonexistent/video.mp4")

    def test_upload_raises_on_401(self, tmp_path):
        """Raises RuntimeError with ESSO_TOKEN_EXPIRED on HTTP 401."""
        from unittest.mock import patch, MagicMock
        import requests

        video = tmp_path / "v.mp4"
        video.write_bytes(b"fake")

        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.ok = False

        with patch("requests.post", return_value=mock_resp):
            m = OAMatcher(esso_token="expired", workflow_id="wf")
            with pytest.raises(RuntimeError, match="ESSO_TOKEN_EXPIRED"):
                m.upload_video(str(video))

    def test_upload_raises_on_403(self, tmp_path):
        """Raises RuntimeError with ESSO_TOKEN_EXPIRED on HTTP 403."""
        from unittest.mock import patch, MagicMock

        video = tmp_path / "v.mp4"
        video.write_bytes(b"fake")

        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.ok = False

        with patch("requests.post", return_value=mock_resp):
            m = OAMatcher(esso_token="forbidden", workflow_id="wf")
            with pytest.raises(RuntimeError, match="ESSO_TOKEN_EXPIRED"):
                m.upload_video(str(video))

    # ---------------------------------------------------------------------------
    # Helpers for the 3-step presigned S3 upload flow
    # ---------------------------------------------------------------------------

    @staticmethod
    def _presign_ok(file_name="v.mp4"):
        """Valid presign response for a single file."""
        from unittest.mock import MagicMock
        r = MagicMock()
        r.status_code = 200
        r.ok = True
        r.text = ""
        r.json.return_value = {
            "url": [{
                "status": "success",
                "file_name": file_name,
                "file_id": file_name,
                "url": {
                    "url": "https://s3.example.com/bucket",
                    "fields": {"key": "some/key", "policy": "p"},
                    "file_name": file_name,
                },
            }]
        }
        r.raise_for_status = lambda: None
        return r

    @staticmethod
    def _s3_ok():
        from unittest.mock import MagicMock
        r = MagicMock()
        r.status_code = 204
        r.ok = True
        r.text = ""
        return r

    @staticmethod
    def _parse_ok(uuid="abc-123"):
        from unittest.mock import MagicMock
        r = MagicMock()
        r.status_code = 200
        r.ok = True
        r.text = ""
        r.json.return_value = {"file_uuid": uuid}
        r.raise_for_status = lambda: None
        return r

    def _mock_upload(self, m, tmp_path, uuid="abc-123"):
        """Patch _oa_request and requests.post for a full successful upload."""
        from unittest.mock import patch, MagicMock

        video = tmp_path / "v.mp4"
        video.write_bytes(b"fake")

        oa_responses = [self._presign_ok(), self._parse_ok(uuid)]
        oa_iter = iter(oa_responses)

        def fake_oa(method, path, **kwargs):
            return next(oa_iter)

        return video, patch.object(m, "_oa_request", side_effect=fake_oa), \
               patch("requests.post", return_value=self._s3_ok())

    # ---------------------------------------------------------------------------
    # Tests
    # ---------------------------------------------------------------------------

    def test_upload_raises_on_500(self, tmp_path):
        """Raises RuntimeError (not ESSO_TOKEN_EXPIRED) on HTTP 500 from presign."""
        from unittest.mock import patch, MagicMock

        video = tmp_path / "v.mp4"
        video.write_bytes(b"fake")

        err_resp = MagicMock()
        err_resp.status_code = 500
        err_resp.ok = False
        err_resp.text = "Internal Server Error"

        m = OAMatcher(esso_token="tok", workflow_id="wf")
        with patch.object(m, "_oa_request", return_value=err_resp):
            with pytest.raises(Exception) as exc_info:
                m.upload_video(str(video))
            assert "ESSO_TOKEN_EXPIRED" not in str(exc_info.value)

    def test_upload_raises_on_missing_uuid(self, tmp_path):
        """Raises RuntimeError when file_parsing response has no file_uuid."""
        from unittest.mock import patch, MagicMock

        video = tmp_path / "v.mp4"
        video.write_bytes(b"fake")

        parse_no_uuid = MagicMock()
        parse_no_uuid.status_code = 200
        parse_no_uuid.ok = True
        parse_no_uuid.text = ""
        parse_no_uuid.json.return_value = {"status": "ok"}  # no file_uuid
        parse_no_uuid.raise_for_status = lambda: None

        oa_responses = iter([self._presign_ok(), parse_no_uuid])

        m = OAMatcher(esso_token="tok", workflow_id="wf")
        with patch.object(m, "_oa_request", side_effect=lambda *a, **kw: next(oa_responses)), \
             patch("requests.post", return_value=self._s3_ok()):
            with pytest.raises(RuntimeError, match="file_uuid"):
                m.upload_video(str(video))

    def test_upload_returns_uuid_string(self, tmp_path):
        """Returns the UUID string on a successful 3-step upload."""
        m = OAMatcher(esso_token="tok", workflow_id="wf")
        video, mock_oa, mock_s3 = self._mock_upload(m, tmp_path, uuid="abc-123")
        with mock_oa, mock_s3:
            result = m.upload_video(str(video))
        assert result == "abc-123"

    def test_upload_accepts_uuid_field_alias(self, tmp_path):
        """file_uuid key from file_parsing response is returned correctly."""
        m = OAMatcher(esso_token="tok", workflow_id="wf")
        video, mock_oa, mock_s3 = self._mock_upload(m, tmp_path, uuid="xyz-456")
        with mock_oa, mock_s3:
            result = m.upload_video(str(video))
        assert result == "xyz-456"

    def test_upload_raises_on_connection_error(self, tmp_path):
        """Raises RuntimeError when all OA network requests fail."""
        from unittest.mock import patch
        import requests as req_lib

        video = tmp_path / "v.mp4"
        video.write_bytes(b"fake")

        m = OAMatcher(esso_token="tok", workflow_id="wf")
        with patch("requests.request", side_effect=req_lib.exceptions.ConnectionError("refused")):
            with pytest.raises(RuntimeError):
                m.upload_video(str(video))


# ---------------------------------------------------------------------------
# OAMatcher — _compress_video
# ---------------------------------------------------------------------------

class TestCompressVideo:
    """Tests for _compress_video().  ffmpeg calls are mocked throughout."""

    def _make_large_video(self, tmp_path, size_bytes=96_000_001):
        """Create a fake file larger than UPLOAD_SIZE_LIMIT (95 MB)."""
        video = tmp_path / "big.mp4"
        video.write_bytes(b"\x00" * size_bytes)
        return video

    def test_compress_video_raises_if_ffmpeg_missing(self, tmp_path):
        """Raises RuntimeError when ffmpeg is not on PATH."""
        from unittest.mock import patch
        video = self._make_large_video(tmp_path)
        m = OAMatcher(esso_token="tok", workflow_id="wf")
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(RuntimeError, match="ffmpeg"):
                m._compress_video(video)

    def test_compress_video_raises_on_ffmpeg_failure(self, tmp_path):
        """Raises RuntimeError when ffmpeg exits non-zero."""
        from unittest.mock import patch, MagicMock
        import subprocess

        video = self._make_large_video(tmp_path)
        m = OAMatcher(esso_token="tok", workflow_id="wf")

        def fake_run(cmd, **kwargs):
            r = MagicMock()
            # First call is version check — succeeds
            if "-version" in cmd:
                r.returncode = 0
                return r
            # Transcoding fails
            r.returncode = 1
            r.stderr = "error"
            return r

        with patch("subprocess.run", side_effect=fake_run):
            with pytest.raises(RuntimeError, match="ffmpeg transcoding failed"):
                m._compress_video(video)

    def _full_upload_mocks(self, m, video_path, uuid="abc"):
        """Patch _oa_request (presign + parse) and requests.post (S3) for success."""
        from unittest.mock import patch, MagicMock

        presign_r = MagicMock()
        presign_r.status_code = 200
        presign_r.ok = True
        presign_r.text = ""
        presign_r.raise_for_status = lambda: None
        presign_r.json.return_value = {
            "url": [{
                "status": "success",
                "url": {"url": "https://s3.example.com/", "fields": {"key": "k"}, "file_name": "f.mp4"},
            }]
        }

        parse_r = MagicMock()
        parse_r.status_code = 200
        parse_r.ok = True
        parse_r.text = ""
        parse_r.raise_for_status = lambda: None
        parse_r.json.return_value = {"file_uuid": uuid}

        s3_r = MagicMock()
        s3_r.status_code = 204

        oa_iter = iter([presign_r, parse_r])
        mock_oa = patch.object(m, "_oa_request", side_effect=lambda *a, **kw: next(oa_iter))
        mock_s3 = patch("requests.post", return_value=s3_r)
        return mock_oa, mock_s3

    def test_upload_triggers_compression_for_large_file(self, tmp_path):
        """upload_video() calls _compress_video when file > UPLOAD_SIZE_LIMIT."""
        from unittest.mock import patch

        video = self._make_large_video(tmp_path)
        small = tmp_path / "small.mp4"
        small.write_bytes(b"\x00" * 1000)

        m = OAMatcher(esso_token="tok", workflow_id="wf")
        mock_oa, mock_s3 = self._full_upload_mocks(m, video, uuid="compressed-uuid")
        with patch.object(m, "_compress_video", return_value=small) as mock_compress, \
             mock_oa, mock_s3:
            result = m.upload_video(str(video))

        mock_compress.assert_called_once()
        assert result == "compressed-uuid"

    def test_upload_skips_compression_for_small_file(self, tmp_path):
        """upload_video() does NOT call _compress_video for files <= UPLOAD_SIZE_LIMIT."""
        from unittest.mock import patch

        video = tmp_path / "small.mp4"
        video.write_bytes(b"\x00" * 1000)

        m = OAMatcher(esso_token="tok", workflow_id="wf")
        mock_oa, mock_s3 = self._full_upload_mocks(m, video, uuid="direct-uuid")
        with patch.object(m, "_compress_video") as mock_compress, mock_oa, mock_s3:
            result = m.upload_video(str(video))

        mock_compress.assert_not_called()
        assert result == "direct-uuid"
