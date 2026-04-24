"""
oa_matcher.py — Open Arena / Gemini HTTP client for shot-to-shotlist matching.

Uploads a video to Open Arena and uses Gemini to match each detected shot cut
to the appropriate shotlist entry.

Auth: ESSO token is passed at construction time. Never stored on disk or in
config. Call update_token() when the user pastes a fresh daily token.

HTTP pattern mirrors MonitoringAgent._call_open_arena() from RadioScribe
(radio scribe/radioscribe/backend/monitor.py) exactly, with the addition of
a file_uuid in the inference payload.
"""
import argparse
import json
import logging
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# --- Open Arena endpoints (internal URL for on-net, external as fallback) ---
OA_BASE_INTERNAL = "https://aiopenarena.gcs.int.thomsonreuters.com"
OA_BASE_EXTERNAL = "https://aiopenarena.thomsonreuters.com"

OPEN_ARENA_INTERNAL = f"{OA_BASE_INTERNAL}/v3/inference"
OPEN_ARENA_EXTERNAL = f"{OA_BASE_EXTERNAL}/v3/inference"

# Upload flow (3-step presigned S3):
#   1. POST /v3/document/file_upload  → get presigned S3 URL
#   2. POST {s3_url} with form fields → upload to S3 (returns 204)
#   3. POST /v1/document/file_parsing → parse S3 file, get file_uuid
PRESIGN_PATH = "/v3/document/file_upload"
PARSE_PATH = "/v1/document/file_parsing"

# Open Arena upload limit is 100 MB. We target 95 MB to leave a safety margin.
UPLOAD_SIZE_LIMIT = 95_000_000  # bytes

# Timeout for the initial connection attempt to the internal URL.
# External users will fail fast (~3 s) rather than waiting the full read timeout.
INTERNAL_CONNECT_TIMEOUT = 3  # seconds

# Gemini video analysis can be slow for long videos.
REQUEST_TIMEOUT = 120  # seconds

# Response key in the Open Arena answer dict (may vary by workflow).
COMPONENT_ID = "llm_LLM_task"

# --- Gemini prompt template ---
# When a system prompt is configured in the Open Arena workflow, this query can
# be data-only (shotlist + cuts). When no system prompt is set, the full
# self-contained version is used as a fallback.
_PROMPT_TEMPLATE_SHORT = """\
SHOTLIST:
{shotlist_lines}

DETECTED SHOT CUTS:
{shot_lines}

Match each shot to a shotlist entry. Return ONLY the JSON array."""

# Full self-contained prompt — used when no system prompt is available in the workflow.
_PROMPT_TEMPLATE_FULL = """\
You are a professional video timecoding assistant for Reuters News Agency. \
You have been given a news video and a numbered shotlist. Match each detected \
scene cut to the most appropriate shotlist entry.

SHOTLIST FORMAT:
- [VARIOUS OF] entries represent multiple physical shots — several consecutive \
cuts may match the same entry.
- [SOUNDBITE] entries are interview clips — match when a speaker is on camera.
- The first shot is often a title card with no match — use null.

SHOTLIST:
{shotlist_lines}

DETECTED SHOT CUTS:
{shot_lines}

Return a JSON array with one object per shot, in order:
[
  {{
    "shot_index": 0,
    "matched_entry": 3,
    "confidence": "high",
    "notes": "one sentence reasoning"
  }},
  ...
]

Rules:
- shot_index: 0-based index of the detected cut.
- matched_entry: 1-based entry number from the shotlist. null if no match.
- confidence: "high" (unambiguous), "medium" (probable), or "low" (uncertain).
- Respond with ONLY the JSON array. No preamble, no markdown."""


class OAMatcher:
    """
    Uploads a video to Open Arena and uses Gemini to match shots to a shotlist.

    Args:
        esso_token: Daily ESSO authentication token (personal, never stored on disk).
        workflow_id: Open Arena workflow UUID for the Gemini video-analysis workflow.
    """

    def __init__(self, esso_token: str, workflow_id: str, system_prompt: str = "") -> None:
        """Initialise with an ESSO token, workflow ID, and optional system prompt.

        Args:
            esso_token: Daily ESSO authentication token.
            workflow_id: Open Arena workflow UUID.
            system_prompt: System prompt to include in the inference payload.
                When non-empty, a short data-only user query is used. When
                empty, the full self-contained prompt is used instead.
        """
        self.esso_token = esso_token
        self.workflow_id = workflow_id
        self.system_prompt = system_prompt

    def update_token(self, esso_token: str) -> None:
        """Update the ESSO token (called when the user pastes a fresh daily token)."""
        self.esso_token = esso_token
        logger.info("ESSO token updated.")

    def _compress_video(self, source: Path) -> Path:
        """
        Transcode *source* to a temporary MP4 file small enough for Open Arena.

        Uses ffmpeg with scale-to-480p and CRF 30 for a first pass.  If the
        result still exceeds UPLOAD_SIZE_LIMIT, a second pass uses CRF 38 (half
        the bitrate again).  Caller is responsible for deleting the returned
        temp file after use.

        Raises:
            RuntimeError: If ffmpeg is not on PATH or transcoding fails.
        """
        # Verify ffmpeg is available
        try:
            subprocess.run(
                ["ffmpeg", "-version"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            raise RuntimeError(
                "ffmpeg is not installed or not on PATH. "
                "Install ffmpeg to compress videos before upload."
            )

        for crf in (30, 38, 45):
            tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            tmp.close()
            tmp_path = Path(tmp.name)

            cmd = [
                "ffmpeg", "-y",
                "-i", str(source),
                "-vf", "scale=-2:480",
                "-c:v", "libx264",
                "-crf", str(crf),
                "-preset", "fast",
                "-c:a", "aac",
                "-b:a", "96k",
                str(tmp_path),
            ]
            logger.info("Compressing video with CRF %d → %s", crf, tmp_path.name)
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                tmp_path.unlink(missing_ok=True)
                raise RuntimeError(
                    f"ffmpeg transcoding failed (CRF {crf}):\n{result.stderr[-500:]}"
                )

            size = tmp_path.stat().st_size
            logger.info("Compressed size: %d bytes (limit %d)", size, UPLOAD_SIZE_LIMIT)
            if size <= UPLOAD_SIZE_LIMIT:
                return tmp_path

            # Too large — discard and try higher CRF
            tmp_path.unlink(missing_ok=True)

        raise RuntimeError(
            f"Could not compress video below {UPLOAD_SIZE_LIMIT} bytes even at CRF 45. "
            "The video may be too long for Open Arena's upload limit."
        )

    def _oa_request(
        self,
        method: str,
        path: str,
        try_internal: bool = True,
        **kwargs,
    ) -> requests.Response:
        """
        Make an authenticated request to Open Arena, trying internal URL first.

        Args:
            method: HTTP method ("GET", "POST", etc.).
            path: URL path (e.g. "/v3/document/file_upload").
            try_internal: Whether to attempt the internal base URL first.
            **kwargs: Passed directly to requests.request().

        Returns:
            Response object (caller checks status).

        Raises:
            RuntimeError: If all URLs are unreachable.
        """
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.esso_token}"

        bases = [OA_BASE_INTERNAL, OA_BASE_EXTERNAL] if try_internal else [OA_BASE_EXTERNAL]
        response = None

        # Compute timeout once before the loop — popping inside would lose the
        # value on the second iteration (fallback URL).
        caller_timeout = kwargs.pop("timeout", None)

        for base in bases:
            url = base + path
            if caller_timeout is not None:
                req_timeout = caller_timeout
            else:
                connect_timeout = INTERNAL_CONNECT_TIMEOUT if base == OA_BASE_INTERNAL else REQUEST_TIMEOUT
                req_timeout = (connect_timeout, REQUEST_TIMEOUT)
            try:
                response = requests.request(method, url, headers=headers, timeout=req_timeout, **kwargs)
                if response.status_code >= 500 or (
                    response.status_code == 400
                    and base == OA_BASE_INTERNAL
                    and "Unexpected keys" in response.text
                ):
                    logger.warning("Error %d from %s — trying fallback.", response.status_code, url)
                    response = None
                    continue
                break
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                logger.warning("Connection failed to %s — trying fallback.", url)

        if response is None:
            raise RuntimeError("Could not reach Open Arena API on any URL.")

        if response.status_code in (401, 403):
            raise RuntimeError(
                f"ESSO_TOKEN_EXPIRED: HTTP {response.status_code} from Open Arena. "
                "Paste a fresh ESSO token."
            )

        return response

    def upload_video(self, video_path: str) -> str:
        """
        Upload a video file to Open Arena using the 3-step presigned S3 flow.

        Steps:
          1. POST /v3/document/file_upload → get presigned S3 URL + fields
          2. POST to S3 presigned URL → upload bytes (returns 204)
          3. POST /v1/document/file_parsing → register with Open Arena, get file_uuid

        If the file exceeds UPLOAD_SIZE_LIMIT (95 MB) it is first transcoded to
        480p with ffmpeg.  The original file is never modified.

        Args:
            video_path: Local path to the video file.

        Returns:
            File UUID string for use in subsequent inference calls.

        Raises:
            ValueError: If the video file is not found.
            RuntimeError: On any upload/parse failure or auth error.
        """
        path = Path(video_path)
        if not path.exists():
            raise ValueError(f"Video file not found: {video_path}")

        upload_path = path
        tmp_path: Optional[Path] = None

        if path.stat().st_size > UPLOAD_SIZE_LIMIT:
            logger.info(
                "Video is %d bytes (> %d MB limit) — compressing before upload.",
                path.stat().st_size,
                UPLOAD_SIZE_LIMIT // 1_000_000,
            )
            tmp_path = self._compress_video(path)
            upload_path = tmp_path

        try:
            file_name = upload_path.name

            # --- Step 1: get presigned S3 URL ---
            logger.info("Requesting presigned S3 URL for %s…", file_name)
            presign_resp = self._oa_request(
                "POST",
                PRESIGN_PATH,
                json={
                    "files_names": [{"file_name": file_name, "file_id": file_name}],
                    "is_rag_storage_request": False,
                    "workflow_id": self.workflow_id,
                },
            )
            presign_resp.raise_for_status()
            presign_data = presign_resp.json()

            file_info = presign_data["url"][0]
            if file_info.get("status") != "success":
                raise RuntimeError(
                    f"Presign failed: {file_info.get('file_upload_message', str(file_info))}"
                )
            upload_info = file_info["url"]          # nested url object
            s3_url = upload_info["url"]
            s3_fields = upload_info["fields"]
            s3_file_name = upload_info["file_name"]  # may include timestamp suffix

            # --- Step 2: upload to S3 ---
            logger.info(
                "Uploading %s (%d bytes) to S3…",
                file_name,
                upload_path.stat().st_size,
            )
            with open(upload_path, "rb") as f:
                s3_resp = requests.post(
                    s3_url,
                    data=s3_fields,
                    files={"file": f},
                    timeout=REQUEST_TIMEOUT,
                )
            if s3_resp.status_code not in (200, 204):
                raise RuntimeError(
                    f"S3 upload failed with HTTP {s3_resp.status_code}: {s3_resp.text[:300]}"
                )
            logger.info("S3 upload complete (HTTP %d).", s3_resp.status_code)

            # --- Step 3: parse / register with Open Arena ---
            logger.info("Registering file with Open Arena (file_parsing)…")
            parse_resp = self._oa_request(
                "POST",
                PARSE_PATH,
                json={
                    "workflow_id": self.workflow_id,
                    "presigned_url": {
                        "url": s3_url,
                        "fields": s3_fields,
                        "file_name": s3_file_name,
                    },
                },
            )
            parse_resp.raise_for_status()
            parse_data = parse_resp.json()

            file_uuid = parse_data.get("file_uuid")
            if not file_uuid:
                raise RuntimeError(
                    f"file_parsing response missing file_uuid: {str(parse_data)[:300]}"
                )

            logger.info("Video registered. File UUID: %s", file_uuid)
            return str(file_uuid)

        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)
                logger.info("Deleted compressed temp file: %s", tmp_path.name)

    def match(
        self,
        video_path: str,
        shots: list[dict],
        shotlist_entries: list[dict],
        file_uuid: Optional[str] = None,
    ) -> list[dict]:
        """
        Call Gemini via Open Arena to match shots to shotlist entries.

        If *file_uuid* is provided the upload step is skipped — useful when the
        video has already been uploaded via the Open Arena MCP tool or another
        channel.  When omitted the video is uploaded automatically (requires
        the upload endpoint to accept the caller's ESSO token; on internal
        Reuters network this works natively, externally use the MCP tool).

        Args:
            video_path: Local path to the video file.
            shots: List of shot dicts from scene_detector.detect_scenes().
            shotlist_entries: List of entry dicts from shotlist_parser.parse_shotlist().
            file_uuid: Pre-uploaded file UUID. When provided, upload_video() is
                not called.

        Returns:
            The shots list with matching fields added to each entry:
            [
              {
                ...original shot fields...,
                "matched_entry": 3,
                "matched_description": "VARIOUS OF ...",
                "confidence": "high"|"medium"|"low",
                "notes": "Gemini reasoning sentence",
              },
              ...
            ]
        """
        if file_uuid is None:
            file_uuid = self.upload_video(video_path)
        query = self._build_prompt(shots, shotlist_entries)
        raw = self._call_open_arena(file_uuid, query)
        matches = self._parse_response(raw, len(shots))

        # Attach debug info so callers can inspect what was sent / received.
        self.last_prompt = query
        self.last_raw_response = raw

        # Raise if the model returned nothing parseable — surfacing the failure
        # is far better than silently producing a full set of low-confidence
        # no-match results (issue #17).
        if not matches:
            raise RuntimeError(
                f"Gemini returned no parseable matches. "
                f"Raw response ({len(raw)} chars): {raw[:300]!r}"
            )
        if len(matches) < len(shots) * 0.5:
            logger.warning(
                "Only %d/%d shots matched — possible partial parse. "
                "Raw response: %s…",
                len(matches), len(shots), raw[:200],
            )

        # Build lookup: entry_number -> description
        entry_lookup: dict[int, str] = {
            e["entry_number"]: e["description"] for e in shotlist_entries
        }

        # Build full entry lookup (entry_number -> entry dict)
        full_entry_lookup: dict[int, dict] = {
            e["entry_number"]: e for e in shotlist_entries
        }

        # Merge match data into shots list
        for shot in shots:
            idx = shot["shot_index"]
            # Find the match for this shot index (may be missing if parse failed)
            match = next((m for m in matches if m.get("shot_index") == idx), {})
            shot["matched_entry"] = match.get("matched_entry")
            _entry_num = match.get("matched_entry")
            matched_entry_dict = full_entry_lookup.get(_entry_num) if _entry_num is not None else None
            shot["matched_description"] = matched_entry_dict["description"] if matched_entry_dict else ""
            shot["confidence"] = match.get("confidence", "low")
            shot["notes"] = match.get("notes", "")
            # Dateline fields — from the matched shotlist entry
            if matched_entry_dict:
                shot["location"] = matched_entry_dict.get("location", "")
                shot["date"] = matched_entry_dict.get("date", "")
                shot["source"] = matched_entry_dict.get("source", "")
                shot["restrictions"] = matched_entry_dict.get("restrictions", "")
                shot["restrictions_broadcast"] = matched_entry_dict.get("restrictions_broadcast", "")
                shot["restrictions_digital"] = matched_entry_dict.get("restrictions_digital", "")
                shot["location_block"] = matched_entry_dict.get("location_block", "")
            else:
                shot.setdefault("location", "")
                shot.setdefault("date", "")
                shot.setdefault("source", "")
                shot.setdefault("restrictions", "")
                shot.setdefault("restrictions_broadcast", "")
                shot.setdefault("restrictions_digital", "")
                shot.setdefault("location_block", "")

        return shots

    def _build_prompt(self, shots: list[dict], shotlist_entries: list[dict]) -> str:
        """
        Build the self-contained Gemini query string.

        Formats the shotlist and detected shot cuts into the prompt template.
        Flags VARIOUS OF entries and SOUNDBITE entries explicitly so Gemini
        can reason about multi-shot entries correctly.

        Args:
            shots: Shot dicts with shot_index and timecode.
            shotlist_entries: Parsed shotlist entry dicts.

        Returns:
            Formatted query string.
        """
        shotlist_lines = []
        for entry in shotlist_entries:
            num = entry["entry_number"]
            desc = entry["description"]
            tags = []
            if entry.get("is_various"):
                tags.append("VARIOUS OF")
            if entry.get("is_soundbite"):
                tags.append("SOUNDBITE")
            prefix = f"[{'/'.join(tags)}] " if tags else ""
            shotlist_lines.append(f"{num}. {prefix}{desc}")

        shot_lines = []
        for shot in shots:
            shot_lines.append(f"Shot {shot['shot_index']}: {shot['timecode']}")

        template = _PROMPT_TEMPLATE_SHORT if self.system_prompt else _PROMPT_TEMPLATE_FULL
        return template.format(
            shotlist_lines="\n".join(shotlist_lines),
            shot_lines="\n".join(shot_lines),
        )

    def _call_open_arena(self, file_uuid: str, query: str) -> str:
        """
        POST to Open Arena /v3/inference with a file UUID and query.

        Mirrors MonitoringAgent._call_open_arena() from RadioScribe exactly:
        - Try internal URL first with a 3s connect timeout (fast fail for external users).
        - Fall back to external URL on connection errors or 5xx responses.
        - Raise RuntimeError("ESSO_TOKEN_EXPIRED: ...") on 401/403.

        Args:
            file_uuid: UUID returned by upload_video().
            query: Self-contained prompt string for Gemini.

        Returns:
            Raw answer string from the LLM.

        Raises:
            RuntimeError: On auth failure or when all URLs are unreachable.
        """
        payload = {
            "workflow_id": self.workflow_id,
            "query": query,
            "is_persistence_allowed": False,
            "conversation_id": None,
            # File context uses the 'context' envelope, not a top-level file key.
            "context": {"input_type": "file_uuid", "value": [file_uuid]},
        }

        logger.info(
            "Calling Open Arena inference (workflow=%s, file=%s)…",
            self.workflow_id, file_uuid,
        )
        # Log the full prompt so it can be inspected in the server console.
        logger.info("=== FULL PROMPT SENT TO GEMINI ===\n%s\n=== END PROMPT ===", query)
        response = self._oa_request(
            "POST",
            "/v3/inference",
            json=payload,
            headers={"Content-Type": "application/json"},
        )

        if not response.ok:
            logger.error(
                "Open Arena %d response body: %s",
                response.status_code,
                response.text[:500],
            )
        response.raise_for_status()

        data = response.json()

        # Extract answer text. Key varies by workflow — try COMPONENT_ID first,
        # then fall back to the first non-empty string value in the answer dict.
        result = data.get("result", {})
        answer_block = result.get("answer", {})

        if isinstance(answer_block, str):
            raw_answer = answer_block
        elif isinstance(answer_block, dict):
            raw_answer = answer_block.get(COMPONENT_ID, "")
            if not raw_answer:
                raw_answer = next(
                    (v for v in answer_block.values() if isinstance(v, str) and v.strip()),
                    "",
                )
                if raw_answer:
                    logger.info(
                        "Answer key '%s' not found; used fallback key from answer dict.",
                        COMPONENT_ID,
                    )
        else:
            raw_answer = ""

        if not raw_answer:
            logger.info("Open Arena returned empty answer. Full response: %s", str(data)[:500])
            return ""

        logger.info("Open Arena raw answer (%d chars): %s…", len(raw_answer), raw_answer[:200])
        return raw_answer

    def _parse_response(self, raw: str, n_shots: int) -> list[dict]:
        """
        Parse Gemini's JSON response into a list of match dicts.

        Strips markdown code fences if present. Finds the JSON array boundaries.
        Returns an empty / partial list rather than raising on parse failure.

        Args:
            raw: Raw string from _call_open_arena().
            n_shots: Expected number of matches (one per shot).

        Returns:
            List of match dicts with keys: shot_index, matched_entry, confidence, notes.
        """
        if not raw:
            return []

        # Strip markdown code fences
        text = raw.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()

        # Find JSON array boundaries
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1:
            logger.warning("_parse_response: no JSON array found in response: %s", text[:200])
            return []

        json_text = text[start: end + 1]

        try:
            matches = json.loads(json_text)
        except json.JSONDecodeError as exc:
            logger.warning(
                "_parse_response: JSON decode failed: %s | text: %s", exc, json_text[:300]
            )
            return []

        if not isinstance(matches, list):
            logger.warning("_parse_response: expected list, got %s", type(matches).__name__)
            return []

        valid = []
        valid_confidences = {"high", "medium", "low"}
        for item in matches:
            if not isinstance(item, dict):
                continue
            # Validate and normalise fields
            shot_idx = item.get("shot_index")
            if shot_idx is None:
                continue
            try:
                shot_idx = int(shot_idx)
            except (TypeError, ValueError):
                continue

            matched_entry = item.get("matched_entry")
            if matched_entry is not None:
                try:
                    matched_entry = int(matched_entry)
                except (TypeError, ValueError):
                    matched_entry = None

            confidence = str(item.get("confidence", "low")).lower()
            if confidence not in valid_confidences:
                confidence = "low"

            valid.append({
                "shot_index": shot_idx,
                "matched_entry": matched_entry,
                "confidence": confidence,
                "notes": str(item.get("notes", "")),
            })

        return valid


# ---------------------------------------------------------------------------
# CLI test mode
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        description="Test OAMatcher from the command line.",
        epilog=(
            "UPLOAD NOTE: The Open Arena upload endpoint uses service-level auth "
            "that differs from ESSO Bearer tokens. On the internal Reuters network "
            "this works automatically. Externally, upload the video via the Open Arena "
            "MCP tool in Claude Code and pass the resulting UUID with --file-uuid."
        ),
    )
    parser.add_argument("--video", required=True, help="Path to video file")
    parser.add_argument("--shotlist", required=True, help="Path to plain-text shotlist file")
    parser.add_argument("--esso-token", required=True, help="Daily ESSO token")
    parser.add_argument("--workflow-id", required=True, help="Open Arena workflow UUID")
    parser.add_argument(
        "--file-uuid",
        default=None,
        help=(
            "Skip upload — use a pre-uploaded file UUID. "
            "Obtain via the Open Arena MCP upload tool in Claude Code."
        ),
    )
    parser.add_argument("--threshold", type=float, default=2.2)
    parser.add_argument("--min-scene-len", type=int, default=14)
    args = parser.parse_args()

    from scene_detector import detect_scenes
    from shotlist_parser import parse_shotlist

    with open(args.shotlist, encoding="utf-8") as f:
        shotlist_text = f.read()

    print("Detecting scenes…")
    shots = detect_scenes(
        args.video,
        threshold=args.threshold,
        min_scene_len=args.min_scene_len,
    )
    print(f"Detected {len(shots)} shots.")

    entries = parse_shotlist(shotlist_text)
    print(f"Parsed {len(entries)} shotlist entries.")

    matcher = OAMatcher(esso_token=args.esso_token, workflow_id=args.workflow_id)
    results = matcher.match(args.video, shots, entries, file_uuid=args.file_uuid)

    print(json.dumps(results, indent=2))
