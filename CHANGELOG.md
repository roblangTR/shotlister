# Changelog

All notable changes to Shotlist Timecoder are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)

---

## [Unreleased]

---

## [1.0.0] — 2026-04-08

Initial working release. Full end-to-end pipeline verified against a 176 MB Reuters
video (Pope Leo at Castel Gandolfo, 5 shots, 5/5 matched at high confidence).

### Added

**Core pipeline**
- `scene_detector.py` — PySceneDetect AdaptiveDetector wrapper with ffprobe/cv2 fallback for frame rate detection
- `shotlist_parser.py` — Reuters plain-text shotlist parser (entry numbers, location blocks, SOUNDBITE/VARIOUS OF flags)
- `frame_extractor.py` — OpenCV thumbnail extraction (one JPEG per shot, 0.5s offset)
- `oa_matcher.py` — Open Arena / Gemini HTTP client with 3-step presigned S3 upload flow
- `timecode_utils.py` — timecode arithmetic utilities (copied from shot_detector)

**Open Arena integration**
- 3-step presigned S3 upload: `/v3/document/file_upload` → S3 → `/v1/document/file_parsing`
- Automatic video compression for files >9 MB (ffmpeg, 480p, CRF 30/38/45)
- Internal URL tried first (3s timeout), external fallback on failure or 5xx
- Targeted fallback to external on `400 Unexpected keys` from internal (v2-only deployment)
- Inference payload: `context: {input_type: "file_uuid", value: [uuid]}`
- Response parsing: uses first non-empty value in answer dict (key varies by model)
- `--file-uuid` CLI flag to skip upload and reuse an existing file UUID

**API server (`api.py`)**
- `POST /detect` — scene detection, returns job_id + shots
- `POST /match` — full pipeline, returns matched results with thumbnail URLs
- `GET /export/{job_id}?format=csv|txt|json` — result download
- `GET /thumbnails/{job_id}/{filename}` — thumbnail serving
- `GET /video?path=...` — local video streaming with HTTP range support (for UI player seek)
- `GET /browse` — native macOS file picker via osascript, returns selected path
- In-memory job store with 1-hour TTL

**MCP server (`mcp_server.py`)**
- `detect_shots` tool — scene detection
- `match_shotlist` tool — full pipeline including CSV output
- stdio transport for Claude Desktop

**React UI (`ui/`)**
- Full-screen layout: input row collapses to compact bar after matching
- `VideoUpload` — path input with **Browse…** button (native macOS file picker)
- `ShotlistInput` — shotlist textarea, collapsible ESSO settings panel
- `ReviewPane` — two-column: fixed video player sidebar + full-width match table
  - Match column shows complete description + Gemini notes
  - Click row to seek video
  - Reassignment dropdown per shot
- `ExportBar` — CSV download + clipboard copy
- Gemini workflow ID hardcoded (`ee360c20-9f8a-4fcd-95a1-ceacb4224cce`)
- ESSO token cached in `localStorage` using JWT `exp` claim; auto-expires; shows countdown

**Tests**
- 131 tests covering scene detection, shotlist parsing, and OA matcher
- `TestUploadVideoErrorPaths` — covers presign failure, S3 failure, parse failure
- `TestCompressVideo` — covers compression trigger and CRF escalation

**Infrastructure**
- `config.yaml` — detection defaults, server config, CORS origins
- `requirements.txt` — pinned Python dependencies
- `.venv` via Python 3.13

### Fixed
- Video path race condition in UI: `handleDetected` was resetting `videoPath` to `''`, causing `/match` to receive an empty path (resolved to `.`). Fixed by passing path as second argument to callback.
- Inference payload: corrected from `file_uuid: [uuid]` to `context: {input_type: "file_uuid", value: [uuid]}` (discovered from videofy_minimal codebase).
- Internal URL rejection of v3-specific keys: added fallback to external on `400 Unexpected keys`.
