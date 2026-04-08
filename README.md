# Shotlist Timecoder

Takes a Reuters video file and a plain-text shotlist. Detects scene cuts using PySceneDetect, then uses Gemini (via the Reuters Open Arena API) to match each detected shot to a shotlist entry. Produces a timecoded shotlist for editorial use.

## Overview

Three independently usable surfaces:

- **React UI** — browser-based editorial review, video preview, and CSV export
- **FastAPI backend** — REST API for integration into other tools
- **MCP server** — for Claude Desktop / chaining with other Reuters MCP tools

## Quick Start

```bash
# 1. Create and activate virtual environment
python3.13 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start the API server
cd /path/to/shotlist_timecoder
uvicorn api:app --host 127.0.0.1 --port 8000

# 4. Start the React UI (separate terminal)
cd ui && npm install && npm run dev
# → http://localhost:5173
```

## Installation

**Requirements:**

| Dependency | Version | Notes |
|---|---|---|
| Python | 3.13 | via `python3.13` |
| FFmpeg | any | `brew install ffmpeg` — required for ffprobe (frame rate) and video compression |
| Node.js | 18+ | UI only |

FFmpeg is required for two purposes:
1. **`ffprobe`** — accurate frame rate and duration detection
2. **`ffmpeg`** — automatic compression of videos >9 MB before upload to Open Arena (transcodes to 480p CRF 30–45)

## Configuration

`config.yaml` controls detection defaults and server settings:

```yaml
detection:
  threshold: 2.2        # AdaptiveDetector sensitivity (tuned value)
  min_scene_len: 14     # minimum scene length in frames (~0.56s at 25fps)
  detector: adaptive
  luma_only: false
  merge_frames: 0

server:
  host: 127.0.0.1
  port: 8000
  cors_origins:
    - http://localhost:5173
    - http://localhost:3000

jobs:
  ttl_seconds: 3600     # in-memory job expiry
```

The Open Arena **workflow ID is hardcoded** to the Reuters Gemini workflow (`ee360c20-9f8a-4fcd-95a1-ceacb4224cce`). The ESSO token is never stored in config — it is supplied at runtime.

## Usage

### React UI (recommended)

1. Open http://localhost:5173 with both servers running.
2. **Step 1 — Video:** Click **Browse…** to pick a local video file, or type the path. Click **Detect shots**.
3. **Step 2 — Shotlist:** Paste the Reuters plain-text shotlist into the textarea. Open **API settings** and paste your ESSO token (get it at [user-details](https://dataandanalytics.int.thomsonreuters.com/user-details)). Click **Match shotlist**.
4. **Review:** The review pane fills the screen. Click any row to seek the video player. Use the **Reassign** dropdown to correct mismatches.
5. **Export:** Click **Export CSV** or **Copy to clipboard**.

The ESSO token is a JWT — the UI reads its expiry claim and caches it in `localStorage` until it expires, so you only need to paste it once per day.

### Via REST API

```bash
# Step 1: Detect shots
curl -X POST http://localhost:8000/detect \
  -H "Content-Type: application/json" \
  -d '{"video_path": "/path/to/video.mp4"}'

# Step 2: Match to shotlist
curl -X POST http://localhost:8000/match \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": "<job_id from step 1>",
    "video_path": "/path/to/video.mp4",
    "shotlist_text": "1. VARIOUS OF ...",
    "esso_token": "your-daily-esso-token",
    "workflow_id": "ee360c20-9f8a-4fcd-95a1-ceacb4224cce"
  }'

# Step 3: Export
curl "http://localhost:8000/export/<job_id>?format=csv" -o results.csv
```

### Via CLI (direct Gemini test)

```bash
python oa_matcher.py \
  --video /path/to/video.mp4 \
  --shotlist /path/to/shotlist.txt \
  --esso-token YOUR_TOKEN \
  --workflow-id ee360c20-9f8a-4fcd-95a1-ceacb4224cce
```

Pass `--file-uuid <uuid>` to skip the upload step and reuse a previously uploaded file.

### Via MCP (Claude Desktop)

Add to `claude_desktop_config.json`:

```json
"shotlist-timecoder": {
  "command": "python",
  "args": ["/Users/lng3369/Documents/Claude/2026/shotlist_timecoder/mcp_server.py"]
}
```

Tools: `detect_shots`, `match_shotlist`.

## API Reference

### `POST /detect`

Run scene detection on a local video file.

**Body:**
```json
{
  "video_path": "/path/to/video.mp4",
  "threshold": 2.2,
  "min_scene_len": 14,
  "detector": "adaptive",
  "luma_only": false,
  "merge_frames": 0
}
```

**Response:**
```json
{
  "job_id": "uuid",
  "shots": [
    {"shot_index": 0, "timecode": "00:00:00:00", "frame_number": 0, "seconds": 0.0}
  ],
  "video_info": {"fps": 25.0, "total_frames": 1500, "duration_seconds": 60.0},
  "shot_count": 1
}
```

---

### `POST /match`

Full pipeline: detect (or reuse cached) shots → extract thumbnails → parse shotlist → upload video to Open Arena → Gemini matching.

Videos larger than 9 MB are automatically compressed to 480p before upload.

**Body:**
```json
{
  "job_id": "uuid",
  "video_path": "/path/to/video.mp4",
  "shotlist_text": "1. VARIOUS OF ...",
  "esso_token": "your-daily-esso-token",
  "workflow_id": "ee360c20-9f8a-4fcd-95a1-ceacb4224cce"
}
```

`job_id` is optional — if omitted, scene detection runs from scratch.

**Response:**
```json
{
  "job_id": "uuid",
  "results": [
    {
      "shot_index": 0,
      "timecode": "00:00:00:00",
      "seconds": 0.0,
      "matched_entry": 1,
      "matched_description": "VARIOUS OF ARTEMIS I AS IT TAKES OFF",
      "confidence": "high",
      "notes": "Rocket visible on launchpad matches entry 1",
      "thumbnail_url": "/thumbnails/uuid/shot_0000.jpg"
    }
  ],
  "shot_count": 5
}
```

Returns HTTP 401 if the ESSO token is expired.

---

### `GET /export/{job_id}?format=csv|txt|json`

Download matched results. Run `/match` first.

| Format | Content-Type | Notes |
|---|---|---|
| `csv` (default) | `text/csv` | shot_index, timecode, matched_entry, matched_description, confidence, notes |
| `txt` | `text/plain` | Human-readable one line per shot |
| `json` | `application/json` | Full result objects |

---

### `GET /thumbnails/{job_id}/{filename}`

Serve an extracted thumbnail JPEG. Used by the UI's `<img>` tags.

---

### `GET /video?path=/path/to/video.mp4`

Stream a local video file to the browser. Supports HTTP range requests (required for the seek bar). Used internally by the UI's video player.

---

### `GET /browse`

Open a native macOS file picker dialog (via `osascript`) and return the selected path. Returns `{"path": null}` if cancelled.

```json
{"path": "/Users/you/Downloads/video.mp4"}
```

## Open Arena Upload Flow

The upload to Open Arena uses a 3-step presigned S3 flow:

1. `POST /v3/document/file_upload` — request a presigned S3 URL (ESSO Bearer auth)
2. `POST {s3_presigned_url}` — upload the file directly to S3 (pre-authenticated via form fields, no ESSO token)
3. `POST /v1/document/file_parsing` — register the uploaded file and receive a `file_uuid`

The `file_uuid` is then passed to the inference endpoint as:
```json
{"context": {"input_type": "file_uuid", "value": ["<uuid>"]}}
```

## Troubleshooting

**`ffprobe not found` / `ffmpeg not found`**
```bash
brew install ffmpeg
```

**ESSO token expired**
The token is a personal daily JWT. Get a fresh one at [user-details](https://dataandanalytics.int.thomsonreuters.com/user-details). The UI caches it automatically until expiry.

**`RuntimeError: ESSO_TOKEN_EXPIRED`** — the API returns HTTP 401. Paste a new token in the UI settings panel.

**Browse button does nothing** — the macOS file picker opens via `osascript` — it may appear behind other windows. Check the Dock.

**Video player blank** — the player streams via `/video?path=...` through the backend. Ensure the backend is running on port 8000.

**Gemini returns no matches** — check the API logs for the raw response. Common cause: the video was too dark or heavily compressed. Try lowering `threshold` in the detect step.

## Running Tests

```bash
source .venv/bin/activate
python -m pytest tests/ -v
```

131 tests covering scene detection, shotlist parsing, and OA matcher logic.

## License

Internal Reuters tool — not for external distribution.
