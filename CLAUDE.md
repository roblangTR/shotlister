# Shotlist Timecoder — Claude Code Instructions

## What this project does

Takes a Reuters video file and a plain-text shotlist. Detects scene cuts using
PySceneDetect. Uses Gemini (via the Reuters Open Arena API) to match each
detected shot to a shotlist entry. Produces a timecoded shotlist for editorial use.

## Project layout

```
shotlist_timecoder/
├── timecode_utils.py      # copied from shot_detector — do not modify
├── scene_detector.py      # PySceneDetect wrapper
├── shotlist_parser.py     # Reuters shotlist text parser
├── frame_extractor.py     # OpenCV thumbnail extraction
├── oa_matcher.py          # Open Arena / Gemini HTTP client
├── api.py                 # FastAPI server
├── mcp_server.py          # FastMCP MCP server
├── config.yaml            # default parameters
├── requirements.txt
├── tests/
└── ui/                    # Vite + React frontend
```

## Before writing any code — read these files

These are existing Reuters tools that contain patterns and logic to reuse.
Read them fully before implementing anything.

| File | What to take from it |
|------|---------------------|
| `/Users/lng3369/Documents/Claude/2026/shot_detector/evaluator.py` | `_detect_scenes()` — copy verbatim. `VIDEO_EXTENSIONS`. |
| `/Users/lng3369/Documents/Claude/2026/shot_detector/timecode_utils.py` | Copy the entire file unchanged. |
| `/Users/lng3369/Documents/Claude/2026/shot_cutter/config.yaml` | Default params: threshold 2.2, min_scene_len 14. |
| `/Users/lng3369/Documents/Claude/2026/radio scribe/radioscribe/backend/monitor.py` | `_call_open_arena()` — the exact HTTP pattern for Open Arena. |
| `/Users/lng3369/Documents/Claude/2026/radio scribe/inference_v3_migration_guide.md` | Full v3 API reference. `ChatClientV3` is the canonical Python example. |

## Critical patterns — follow exactly

### Open Arena HTTP calls

Mirror `MonitoringAgent._call_open_arena()` from `monitor.py`. Key rules:

1. Try internal URL first with a 3-second connect timeout:
   `https://aiopenarena.gcs.int.thomsonreuters.com/v3/inference`
2. Fall back to external: `https://aiopenarena.thomsonreuters.com/v3/inference`
3. Auth: `Authorization: Bearer {esso_token}` header.
4. Payload must include `"is_persistence_allowed": false`. Do **NOT** include
   `"api_version": "v3"` — the internal URL (`gcs.int`) rejects that key; the
   external fallback handles versioning automatically via the URL path.
5. Response structure: `data["result"]["answer"]["llm_LLM_task"]` — fall back
   to first non-empty string value in the answer dict if that key is absent.
6. Strip markdown fences before JSON parsing.
7. On 401 or 403: raise `RuntimeError("ESSO_TOKEN_EXPIRED: HTTP {status} ...")`.

### ESSO token

Never store the ESSO token on disk or in config. It is a personal daily token.
Pass it at call time — in the request body for the API, as a tool parameter
for the MCP server. `OAMatcher` takes it in `__init__` and has `update_token()`.

### scene_detect dependency

`evaluator.py` imports `get_video_info_ffprobe` and `frames_to_timecode` from
a file at `../../python scripts/vespa 2.0/...`. Do NOT reproduce that import.
Implement both functions directly in `scene_detector.py`:

- `get_video_info(path)` — use `ffprobe -v quiet -print_format json -show_streams`.
  Parse `r_frame_rate` (e.g. `"25/1"`) from `streams[0]`. Fall back to
  `cv2.VideoCapture` if ffprobe is not on PATH.
- `frames_to_timecode(frame_num, fps)` — same arithmetic as `frames_to_tc()` in
  `timecode_utils.py`.

## Reuters shotlist format — example input

```
CAPE CANAVERAL, FLORIDA, UNITED STATES (FILE - NOVEMBER 16, 2022) (NASA - For
editorial use only. Do not obscure logo)

1. VARIOUS OF ARTEMIS I AS IT TAKES OFF WITH SPEAKER COUNTING DOWN AND THEN
SAYING (English): 'And lift-off of Artemis I. We rise together back to the moon
and beyond."

IN SPACE (RECENT) (NASA TV - For editorial use only. Do not obscure logo)
2. VARIOUS OF MOON SURFACE SEEN FROM ORION SPACE CAPSULE

WASHINGTON D.C., UNITED STATES (RECENT - SEPTEMBER 12, 2025) (REUTERS - Access all)
3. (SOUNDBITE) (English) ACTING ADMINISTRATOR, NASA EXPLORATION SYSTEMS
DEVELOPMENT MISSION DIRECTORATE, DR LORI GLAZE, SAYING:
    "The Apollo missions landed near the equator of the moon..."
```

Parser rules:
- Entries are delimited by lines starting with a digit and a period (`1.`, `2.`, etc.).
- Location blocks are ALL-CAPS lines that do NOT start with a digit.
- `is_various` = description starts with "VARIOUS OF" (case-insensitive).
- `is_soundbite` = description contains "(SOUNDBITE)".
- Each entry gets the location block that immediately precedes it.

## Gemini prompt template

The query to Open Arena must be self-contained — do not rely on system prompts
in modelparams (they are not reliably applied, per RadioScribe codebase).

```
You are a video production assistant. You have been given a video and a numbered
shotlist. Your task is to match each detected shot cut in the video to the most
appropriate shotlist entry.

SHOTLIST:
{for each entry: "N. [VARIOUS OF / SOUNDBITE] description"}

DETECTED SHOT CUTS (timecodes where a new shot begins):
{for each shot: "Shot N: HH:MM:SS:FF"}

For each detected shot, watch the video from that timecode and identify which
shotlist entry it corresponds to. Some shotlist entries marked "VARIOUS OF" may
match multiple consecutive shots.

Return a JSON array with one object per detected shot, in order:
[
  {
    "shot_index": 0,
    "matched_entry": 3,
    "confidence": "high",
    "notes": "one sentence reasoning"
  },
  ...
]

Rules:
- shot_index is the 0-based index of the detected shot cut.
- matched_entry is the 1-based entry number from the shotlist. null if no match.
- confidence is "high", "medium", or "low".
- Respond with ONLY the JSON array. No preamble, no markdown.
```

## Detection defaults

From the parameter sweep in `shot_detector/` — use these as defaults:
- Detector: `AdaptiveDetector`
- `adaptive_threshold`: 2.2
- `min_scene_len`: 14 frames
- `luma_only`: False
- `merge_frames`: 0

## API design

```
POST /detect     — run scene detection, return shots list
POST /match      — upload to OA, run Gemini, return timecoded results
GET  /export/{job_id}?format=csv|txt|json  — download results
GET  /thumbnails/{job_id}/{filename}       — serve extracted frames
```

Job state in memory only. No database. 1-hour TTL.

The `/match` body must include `esso_token` and `workflow_id` — both supplied
by the caller at runtime, never from config.

## MCP tools

Two tools:

`detect_shots(video_path, threshold, min_scene_len, detector, luma_only, merge_frames)`
Returns: `{shots: [...], video_info: {...}, shot_count: int}`

`match_shotlist(video_path, shotlist_text, esso_token, workflow_id, threshold, min_scene_len)`
Returns: `{results: [...], csv: str, summary: {...}}`

Run as stdio. Claude Desktop config:
```json
"shotlist-timecoder": {
  "command": "python",
  "args": ["/Users/lng3369/Documents/Claude/2026/shotlist_timecoder/mcp_server.py"]
}
```

## React UI

Vite + React. No TypeScript. Tailwind CSS.

Four components:
1. `VideoUpload` — local file path input → calls `/detect`
2. `ShotlistInput` — textarea + settings panel with ESSO token input (session only, not persisted)
3. `ReviewPane` — two-column: left = video player with seek, right = matched shots list with thumbnails, confidence badges, reassignment dropdowns
4. `ExportBar` — CSV download and clipboard copy

The ESSO token input is in a collapsible settings panel. The token is cached in
`localStorage` using the JWT `exp` claim — it is auto-removed once it expires,
so the user only needs to paste it once per day. The token is **not** persisted
beyond its natural expiry.

## Dependencies

Python:
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

No AI SDKs. All AI calls go through Open Arena HTTP directly.

Node (ui/):
```
react, react-dom, vite, @vitejs/plugin-react, tailwindcss
```

## Build order

1. `timecode_utils.py` (copy), `config.yaml`, `requirements.txt`, venv setup
2. `scene_detector.py` — test with a video from `shot_detector/Test Videos/`
3. `shotlist_parser.py` — test with the example in this file
4. `frame_extractor.py`
5. `oa_matcher.py` — add `--cli` test mode
6. `api.py`
7. `mcp_server.py`
8. `ui/` — Vite scaffold then components

## Do not

- Do not import from `../../python scripts/vespa 2.0/...` or any path outside
  this project directory.
- Do not use any AI SDK (anthropic, google-generativeai, openai). Open Arena
  HTTP only.
- Do not store ESSO tokens in files, config, or environment variables.
- Do not add a database — memory dict is sufficient for v1.
- Do not add TypeScript to the UI — plain React JSX only.
- Do not make the UI upload video files to the server — use local file paths.
