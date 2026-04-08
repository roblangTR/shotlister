# Shotlist Timecoder — Build Plan

## Overview

A tool that takes a Reuters video file and a plain-text shotlist, detects scene
cuts using PySceneDetect, and uses Gemini (via Open Arena) to match each
detected shot to a shotlist entry — producing a timecoded shotlist.

The system has three independently usable surfaces:
- A FastAPI backend (the core engine)
- An MCP server (for Claude Desktop / chaining with other Reuters MCP tools)
- A React/Node review UI (for editorial QC and export)

---

## Reference Code — Read Before Building

Before writing any code, read these existing files. They contain patterns,
utilities, and logic that must be reused rather than reimplemented.

### Scene detection (reuse directly)

`/Users/lng3369/Documents/Claude/2026/shot_detector/evaluator.py`
- `_detect_scenes()` — the core PySceneDetect wrapper. Copy this function
  verbatim into `scene_detector.py`. Do not rewrite it.
- `match_shots()` — greedy nearest-neighbour timecode matcher. Not needed for
  the primary pipeline but useful for evaluation mode.
- `find_video()`, `VIDEO_EXTENSIONS` — reuse as-is.

`/Users/lng3369/Documents/Claude/2026/shot_detector/timecode_utils.py`
- Copy the entire file into the new project. All timecode conversion functions
  are needed: `detect_framerate`, `parse_frame_timecode`,
  `frame_tc_to_total_frames`, `frames_to_tc`, `tc_to_frames`, `frame_tc_diff`.

`/Users/lng3369/Documents/Claude/2026/shot_cutter/config.yaml`
- Default detection parameters: `threshold: 2.2`, `min_scene_len: 14` (AdaptiveDetector).
- These are the tuned values from the parameter sweep. Use them as defaults.

### Open Arena HTTP client (reuse the pattern)

`/Users/lng3369/Documents/Claude/2026/radio scribe/radioscribe/backend/monitor.py`
- `MonitoringAgent._call_open_arena()` — the exact HTTP pattern to follow for
  calling the Open Arena inference API. Key details:
  - Endpoint: `POST https://aiopenarena.thomsonreuters.com/v3/inference`
  - Internal fallback: `https://aiopenarena.gcs.int.thomsonreuters.com/v3/inference`
  - Try internal first with 3s connect timeout, fall back to external.
  - Auth header: `Authorization: Bearer {esso_token}`
  - Payload fields: `workflow_id`, `query`, `is_persistence_allowed: false`,
    `conversation_id: null`, and `context: {"input_type": "file_uuid", "value": [uuid]}`
    for video context. Do NOT include `api_version` in the body — the internal URL
    (`gcs.int`) rejects it; the fallback to external handles this automatically.
  - Response parsing: `data["result"]["answer"]` — use first non-empty string
    value in the dict (key varies by model, e.g. `"vertexai_gemini-3.1-pro"`).
  - Strip markdown fences from response before JSON parsing.
  - Raise `RuntimeError("ESSO_TOKEN_EXPIRED: ...")` on 401/403.

`/Users/lng3369/Documents/Claude/2026/radio scribe/inference_v3_migration_guide.md`
- Full v3 API reference. The `ChatClientV3.send_message()` pattern is the
  canonical Python HTTP client example to follow.

### Existing scene_detect dependency

`evaluator.py` imports `get_video_info_ffprobe` and `frames_to_timecode` from
a `scene_detect.py` at a relative path:
```
../python scripts/vespa 2.0/Simple Shotlist generator v0.1/standalone_scripts/scene_detect.py
```
The new project must NOT depend on that path. Instead:
- Implement `get_video_info_ffprobe()` directly in `scene_detector.py` using
  `subprocess` + `ffprobe -v quiet -print_format json -show_streams`.
- Implement `frames_to_timecode(frame_num, fps)` directly — it is just
  `HH:MM:SS:FF` arithmetic (same logic as `frames_to_tc` in `timecode_utils.py`).

---

## Target Directory Structure

```
/Users/lng3369/Documents/Claude/2026/shotlist_timecoder/
├── PLAN.md                  # this file
├── CLAUDE.md                # Claude Code instructions
├── README.md                # user-facing docs
├── config.yaml              # default detection parameters
├── requirements.txt         # Python deps
├── timecode_utils.py        # copied from shot_detector (unchanged)
├── scene_detector.py        # PySceneDetect wrapper (extracted from evaluator.py)
├── oa_matcher.py            # Open Arena / Gemini matching client
├── shotlist_parser.py       # shotlist text parser
├── api.py                   # FastAPI server
├── mcp_server.py            # FastMCP MCP server
├── frame_extractor.py       # OpenCV frame extraction for thumbnails
├── tests/
│   ├── test_scene_detector.py
│   ├── test_shotlist_parser.py
│   └── test_oa_matcher.py
└── ui/                      # React frontend (separate npm project)
    ├── package.json
    ├── vite.config.js
    └── src/
        ├── main.jsx
        ├── App.jsx
        └── components/
            ├── VideoUpload.jsx
            ├── ShotlistInput.jsx
            ├── ReviewPane.jsx
            └── ExportBar.jsx
```

---

## Module Specifications

### `timecode_utils.py`

Copy verbatim from
`/Users/lng3369/Documents/Claude/2026/shot_detector/timecode_utils.py`.
No changes.

---

### `scene_detector.py`

Self-contained PySceneDetect wrapper. No external path dependencies.

```python
def get_video_info(video_path: str) -> tuple[int, float]:
    """Return (total_frames, fps) using ffprobe. Fallback to OpenCV if ffprobe absent."""

def frames_to_timecode(frame_num: int, fps: float) -> str:
    """Convert frame number to HH:MM:SS:FF string."""

def detect_scenes(
    video_path: str,
    threshold: float = 2.2,
    min_scene_len: int = 14,
    detector: str = "adaptive",   # "adaptive" | "content"
    luma_only: bool = False,
    merge_frames: int = 0,
) -> list[dict]:
    """
    Run PySceneDetect and return a list of shot dicts:
    [
      {
        "shot_index": 0,          # 0-based
        "timecode": "00:00:00:00",
        "frame_number": 0,
        "seconds": 0.0,
      },
      ...
    ]
    First entry is always frame 0 / 00:00:00:00 (start of video).
    """
```

Implementation notes:
- Copy `_detect_scenes()` logic from `evaluator.py` exactly, but add the
  first-frame entry (frame 0) manually if PySceneDetect does not include it —
  the first shot always starts at the beginning.
- `get_video_info()` must use `ffprobe` via subprocess. The JSON output from
  `ffprobe -v quiet -print_format json -show_streams {path}` contains
  `streams[0].r_frame_rate` (a fraction like `"25/1"`) and
  `streams[0].nb_frames`. Parse `r_frame_rate` by splitting on `/` and
  dividing.
- If ffprobe is not available, fall back to `cv2.VideoCapture` to read
  `CAP_PROP_FPS` and `CAP_PROP_FRAME_COUNT`.

---

### `frame_extractor.py`

Extracts a representative JPEG frame for each detected shot.

```python
def extract_frames(
    video_path: str,
    shots: list[dict],
    output_dir: str,
    offset_seconds: float = 0.5,
) -> list[dict]:
    """
    For each shot, extract a frame offset_seconds after the cut point.
    Saves as {output_dir}/shot_{index:04d}.jpg.
    Returns the shots list with a 'frame_path' key added to each entry.
    If the shot is shorter than offset_seconds, uses the midpoint instead.
    Uses cv2.VideoCapture. Opens the video once and seeks per shot.
    """
```

---

### `shotlist_parser.py`

Parses Reuters plain-text shotlist format into structured entries.

Reuters shotlist format (from the example in this conversation):
```
LOCATION (DATE) (SOURCE - rights)
SHOT_NUMBER. DESCRIPTION
  (SOUNDBITE) (Language) SPEAKER, SAYING:
      "Quote text"
```

"VARIOUS OF" entries represent multiple physical shots under one description.

```python
def parse_shotlist(text: str) -> list[dict]:
    """
    Parse a Reuters-format shotlist into a list of entry dicts:
    [
      {
        "entry_number": 1,          # shot number from shotlist (1-based)
        "description": str,         # full description text
        "is_soundbite": bool,       # True if this is a (SOUNDBITE) entry
        "is_various": bool,         # True if description starts with "VARIOUS OF"
        "location_block": str,      # the preceding location/date/source line
        "raw": str,                 # original text of this entry
      },
      ...
    ]
    """
```

Implementation notes:
- Split on numbered entries (`^\d+\.` at start of line).
- Detect location blocks as lines in ALL-CAPS that don't start with a number.
- `is_various` = description starts with "VARIOUS OF" (case-insensitive).
- `is_soundbite` = description contains "(SOUNDBITE)".
- Strip leading/trailing whitespace from all fields.

---

### `oa_matcher.py`

Open Arena HTTP client for Gemini-based shot matching.

```python
OPEN_ARENA_EXTERNAL = "https://aiopenarena.thomsonreuters.com/v3/inference"
OPEN_ARENA_INTERNAL = "https://aiopenarena.gcs.int.thomsonreuters.com/v3/inference"
INTERNAL_CONNECT_TIMEOUT = 3   # seconds — fail fast if not on VPN/internal
REQUEST_TIMEOUT = 120          # seconds — Gemini video analysis can be slow

class OAMatcher:
    """
    Uploads a video to Open Arena and uses Gemini to match shots to a shotlist.

    Auth: ESSO token passed at construction. Call update_token() for refresh.
    The token is daily and personal — never stored on disk.
    """

    def __init__(self, esso_token: str, workflow_id: str) -> None:
        ...

    def update_token(self, esso_token: str) -> None:
        ...

    def upload_video(self, video_path: str) -> str:
        """
        Upload a video file to Open Arena.

        POST https://aiopenarena.thomsonreuters.com/v1/files/upload
        multipart/form-data with the video file.
        Returns the file UUID string.

        Raises RuntimeError on upload failure or 401/403.
        """

    def match(
        self,
        video_path: str,
        shots: list[dict],
        shotlist_entries: list[dict],
    ) -> list[dict]:
        """
        Upload video, call Gemini via Open Arena, parse and return matches.

        Returns the shots list with matching fields added:
        [
          {
            ...original shot fields...,
            "matched_entry": 3,           # entry_number from shotlist (1-based), or None
            "matched_description": str,
            "confidence": "high"|"medium"|"low",
            "notes": str,                 # Gemini's reasoning, if any
          },
          ...
        ]
        """

    def _build_prompt(self, shots: list[dict], shotlist_entries: list[dict]) -> str:
        """
        Build the query string for Gemini.

        The prompt must:
        1. Present the full shotlist as numbered entries.
        2. Present the detected cut timecodes as a numbered list.
        3. Ask Gemini to return a JSON array mapping each shot index to a
           shotlist entry number.
        4. Handle "VARIOUS OF" entries (multiple shots map to one entry).
        5. Ask for confidence (high/medium/low) and brief notes per match.

        See PROMPT DESIGN section below for the exact prompt template.
        """

    def _call_open_arena(self, file_uuid: str, query: str) -> str:
        """
        POST to /v3/inference with file_uuid in the payload.
        Returns raw answer string.
        Mirrors MonitoringAgent._call_open_arena() from RadioScribe exactly,
        with the addition of file_uuid in the payload.
        Try internal URL first (3s connect timeout), fall back to external.
        Raise RuntimeError("ESSO_TOKEN_EXPIRED: ...") on 401/403.
        """

    def _parse_response(self, raw: str, n_shots: int) -> list[dict]:
        """
        Parse Gemini's JSON response.
        Strip markdown fences. Find [...] boundaries. json.loads().
        Validate: list of dicts, one per shot, with required keys.
        Return empty/partial list rather than raising on parse failure.
        """
```

#### File upload API — 3-step presigned S3 flow

**Note:** The `v1/files/upload` endpoint uses AWS-style credentials, not ESSO Bearer tokens.
The correct upload flow (discovered from `/videofy_minimal/OA API docs/`) is:

**Step 1 — Request presigned S3 URL:**
```
POST https://aiopenarena.thomsonreuters.com/v3/document/file_upload
Authorization: Bearer {esso_token}
Content-Type: application/json
Body: {
  "files_names": [{"file_name": "video.mp4", "file_id": "video.mp4"}],
  "is_rag_storage_request": false,
  "workflow_id": "..."
}
Response: {"url": [{"url": {"url": "https://s3...", "fields": {...}, "file_name": "..."}}]}
```

**Step 2 — Upload to S3 directly (no ESSO token — pre-authenticated via fields):**
```
POST {s3_presigned_url}
Content-Type: multipart/form-data
Body: data=fields (from step 1), files={"file": <binary>}
Response: 204 No Content
```

**Step 3 — Register with Open Arena:**
```
POST https://aiopenarena.thomsonreuters.com/v1/document/file_parsing
Authorization: Bearer {esso_token}
Content-Type: application/json
Body: {
  "workflow_id": "...",
  "presigned_url": {"url": "...", "fields": {...}, "file_name": "..."}
}
Response: {"file_uuid": "..."}
```

The `file_uuid` from step 3 is passed to the inference endpoint as:
```json
{"context": {"input_type": "file_uuid", "value": ["<uuid>"]}}
```

**Large video compression:** Videos >9 MB are transcoded to 480p (CRF 30/38/45) using
ffmpeg before upload. The `_compress_video()` method handles this.

#### Prompt design

The query sent to Gemini must be self-contained (system prompts in `modelparams`
are not reliably applied — embed all instructions in the query, per the
RadioScribe pattern).

```
You are a video production assistant. You have been given a video and a numbered
shotlist. Your task is to match each detected shot cut in the video to the most
appropriate shotlist entry.

SHOTLIST:
{formatted shotlist — entry number, description, one per line}

DETECTED SHOT CUTS (timecodes where a new shot begins):
{list of shot_index: timecode pairs}

For each detected shot, watch the video from that timecode and identify which
shotlist entry it corresponds to. Some shotlist entries marked "VARIOUS OF" may
match multiple consecutive shots.

Return a JSON array with one object per detected shot, in order:
[
  {
    "shot_index": 0,
    "matched_entry": 3,
    "confidence": "high",
    "notes": "Clear match — tight shot of speaker at podium matches entry 3 description"
  },
  ...
]

Rules:
- shot_index is the 0-based index of the detected shot cut.
- matched_entry is the 1-based entry number from the shotlist above.
- confidence is "high" (unambiguous), "medium" (probable), or "low" (uncertain).
- notes is one sentence explaining your reasoning.
- If a shot does not match any entry, use matched_entry: null.
- Respond with ONLY the JSON array. No other text.
```

---

### `api.py`

FastAPI server. Three endpoints.

```python
POST /detect
  Body: { "video_path": str, "threshold": float, "min_scene_len": int,
          "detector": str, "luma_only": bool, "merge_frames": int }
  Returns: { "job_id": str, "shots": list[ShotDict], "video_info": dict }

POST /match
  Body: { "job_id": str, "video_path": str, "shotlist_text": str,
          "esso_token": str, "workflow_id": str }
  Headers: none required (esso_token in body for simplicity)
  Returns: { "job_id": str, "results": list[MatchedShotDict],
             "thumbnails_dir": str }

GET /export/{job_id}
  Query params: format=csv|txt|json (default csv)
  Returns: file download
```

Job state is stored in memory (dict keyed on job_id = uuid4 string).
No database required for v1. Jobs expire after 1 hour.

CORS: allow localhost:5173 (Vite dev) and localhost:3000.

The `/match` endpoint:
1. Calls `detect_scenes()` if shots not already cached for job_id, or uses
   cached shots.
2. Calls `extract_frames()` into a temp dir.
3. Calls `parse_shotlist()`.
4. Calls `OAMatcher.match()`.
5. Stores result in job store.
6. Returns matched results with thumbnail paths relative to the server.

Add a `GET /thumbnails/{job_id}/{filename}` static file route to serve
extracted frames to the UI.

---

### `mcp_server.py`

FastMCP server. Expose two tools.

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("shotlist-timecoder")

@mcp.tool()
def detect_shots(
    video_path: str,
    threshold: float = 2.2,
    min_scene_len: int = 14,
    detector: str = "adaptive",
    luma_only: bool = False,
    merge_frames: int = 0,
) -> dict:
    """
    Detect shot cuts in a video file using PySceneDetect.

    Returns a dict with:
    - shots: list of {shot_index, timecode, frame_number, seconds}
    - video_info: {fps, total_frames, duration_seconds, path}
    - shot_count: int
    """

@mcp.tool()
def match_shotlist(
    video_path: str,
    shotlist_text: str,
    esso_token: str,
    workflow_id: str,
    threshold: float = 2.2,
    min_scene_len: int = 14,
) -> dict:
    """
    Full pipeline: detect shots, parse shotlist, match via Gemini/Open Arena.

    Returns a dict with:
    - results: list of matched shots with timecodes and shotlist entries
    - csv: formatted CSV string ready to paste or save
    - summary: {total_shots, matched, unmatched, high_confidence, low_confidence}
    """
```

Run as stdio transport:
```python
if __name__ == "__main__":
    mcp.run(transport="stdio")
```

Claude Desktop config entry to add to `claude_desktop_config.json`:
```json
"shotlist-timecoder": {
  "command": "python",
  "args": ["/Users/lng3369/Documents/Claude/2026/shotlist_timecoder/mcp_server.py"],
  "env": {}
}
```

---

### `ui/` — React Review Frontend

Vite + React. No TypeScript (keep it simple). Tailwind CSS.

#### Components

`VideoUpload.jsx`
- File picker or path text input (path input preferred — avoids large upload).
- On submit, calls `POST /detect` and stores `job_id` + `shots` in app state.
- Shows shot count and video duration once detected.

`ShotlistInput.jsx`
- Large textarea for pasting raw shotlist text.
- "Match shots" button — calls `POST /match` with `job_id`, `shotlist_text`,
  `esso_token` (from a settings panel), and `workflow_id`.
- ESSO token input in a collapsible settings panel — never persisted to
  localStorage, session only.

`ReviewPane.jsx`
- Main editing surface. Two-column layout.
- Left: video player (using `<video>` tag) with timecode display, click to seek.
- Right: list of matched shots. Each row shows:
  - Timecode (monospace)
  - Thumbnail image (from `/thumbnails/{job_id}/shot_NNNN.jpg`)
  - Matched shotlist entry number + description (truncated, full on hover)
  - Confidence badge (green/amber/red)
  - Dropdown to reassign to a different entry (shows all entries)
- Clicking a row seeks the video to that timecode.
- Edits update local state only.

`ExportBar.jsx`
- "Export CSV" button — calls `GET /export/{job_id}?format=csv` and triggers download.
- "Copy to clipboard" button — copies formatted plain text.
- Format of CSV output:
  ```
  shot_index,timecode,entry_number,description,confidence
  0,00:00:00:00,1,VARIOUS OF ARTEMIS I AS IT TAKES OFF,high
  ...
  ```

---

## Python Dependencies (`requirements.txt`)

```
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
python-multipart>=0.0.9
scenedetect[opencv]>=0.6.7
opencv-python>=4.9.0
requests>=2.31.0
pyyaml>=6.0
mcp[cli]>=1.0.0
fastmcp>=0.1.0
```

Do not add any AI SDK (Anthropic, Google, OpenAI) — all AI calls go through
Open Arena HTTP directly, exactly as in RadioScribe.

---

## config.yaml

```yaml
# Detection parameters (AdaptiveDetector tuned values from parameter sweep)
detection:
  threshold: 2.2
  min_scene_len: 14
  detector: adaptive
  luma_only: false
  merge_frames: 0

# Open Arena
open_arena:
  external_url: https://aiopenarena.thomsonreuters.com/v3/inference
  internal_url: https://aiopenarena.gcs.int.thomsonreuters.com/v3/inference
  internal_connect_timeout: 3
  request_timeout: 120
  # workflow_id: set at runtime — pass via API or MCP tool parameter

# API server
server:
  host: 127.0.0.1
  port: 8000
  cors_origins:
    - http://localhost:5173
    - http://localhost:3000
```

---

## Build Order

Build in this exact order. Each step should be functional before starting the next.

**Step 1 — Foundation**
- Create `timecode_utils.py` (copy from shot_detector)
- Create `config.yaml`
- Create `requirements.txt`
- Set up `.venv`: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`

**Step 2 — Scene detector**
- Create `scene_detector.py` with `get_video_info()`, `frames_to_timecode()`, `detect_scenes()`
- Verify with a quick CLI test: `python -c "from scene_detector import detect_scenes; print(detect_scenes('/path/to/test.mp4'))"`
- Test with a video from `/Users/lng3369/Documents/Claude/2026/shot_detector/Test Videos/`

**Step 3 — Shotlist parser**
- Create `shotlist_parser.py`
- Test with the example shotlist in CLAUDE.md

**Step 4 — Frame extractor**
- Create `frame_extractor.py`
- Verify thumbnails are written to temp dir and readable

**Step 5 — Open Arena matcher**
- Create `oa_matcher.py`
- Implement upload and inference, following RadioScribe `monitor.py` exactly
- Add a CLI test mode: `python oa_matcher.py --video /path/to/video.mp4 --shotlist /path/to/shotlist.txt --esso-token TOKEN --workflow-id UUID`

**Step 6 — FastAPI server**
- Create `api.py`
- Test all three endpoints with `curl` or httpie

**Step 7 — MCP server**
- Create `mcp_server.py`
- Test locally: `python mcp_server.py` (stdio)
- Add to Claude Desktop config

**Step 8 — React UI**
- `cd ui && npm create vite@latest . -- --template react && npm install`
- Build components in order: VideoUpload → ShotlistInput → ReviewPane → ExportBar
- `npm run dev` — verify against running FastAPI server

---

## Open Arena Workflow Setup

Before running the matcher, a Gemini workflow must be created in Open Arena.

Recommended workflow configuration:
- Model: Gemini 2.0 Flash (or Flash 1.5 — whichever is available as a
  single-step passthrough)
- System prompt: minimal — `"You are a video analysis assistant. Analyse the provided video and answer questions about its visual content accurately and concisely."`
- No custom code step
- `is_persistence_allowed`: false

Once created, set the workflow UUID in the API/MCP call at runtime. The
workflow ID is not stored in config because it may differ between environments.

---

## Key Design Decisions

**ESSO token handling** — token is passed at call time, never stored on disk.
Pattern from RadioScribe: pass in request body / MCP parameter. `OAMatcher`
takes it at construction and exposes `update_token()` for refresh.

**No file uploads to the API server** — the UI sends a local file path, not
binary data. The backend reads the file directly. This is correct for a local
desktop tool on Reuters infrastructure.

**Job state in memory** — no database, no Redis. A dict with a 1-hour TTL is
sufficient for single-user local use. If this scales to multi-user, add Redis.

**Single Gemini call per video** — upload the video once, send all shots and
the full shotlist in one prompt. This is cheaper and more accurate than one
call per shot (Gemini can reason about shot sequence and context).

**MCP and API share the same core functions** — `detect_scenes()`,
`parse_shotlist()`, `OAMatcher.match()` are plain Python functions. Both
`api.py` and `mcp_server.py` import and call them directly. No duplication.

---

## Error Handling Requirements

- `detect_scenes()` — catch PySceneDetect exceptions, raise `ValueError` with
  a clear message. Never return partial results silently.
- `OAMatcher._call_open_arena()` — raise `RuntimeError("ESSO_TOKEN_EXPIRED: ...")`
  on 401/403, propagate to API/MCP caller. All other HTTP errors log and
  re-raise as `RuntimeError`.
- `_parse_response()` — never raise on malformed JSON. Log a warning, return
  empty matches with `confidence: "low"` for all shots.
- API endpoints — return structured error JSON with `{"error": "..."}` and
  appropriate HTTP status codes (400 for bad input, 502 for upstream failures).

---

## Testing

Minimal test suite — enough to catch regressions, not exhaustive.

`tests/test_scene_detector.py`
- Test `frames_to_timecode()` with known values (0 frames, 25 frames, 37560 frames at 25fps)
- Test `detect_scenes()` against a short test video — verify it returns a list
  of dicts with required keys. Use a video from the Test Videos folder.

`tests/test_shotlist_parser.py`
- Test `parse_shotlist()` with the Reuters example shotlist (copy from CLAUDE.md).
- Assert: correct entry count, `is_various` flags, `is_soundbite` flags,
  location blocks parsed correctly.

`tests/test_oa_matcher.py`
- Test `_build_prompt()` — assert shotlist entries and shot timecodes appear in output.
- Test `_parse_response()` — test with valid JSON, markdown-fenced JSON,
  invalid JSON (should return empty without raising), missing keys.
- Do NOT test `_call_open_arena()` in unit tests (requires live ESSO token).

Run with: `python -m pytest tests/ -v`
