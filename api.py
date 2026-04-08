"""
api.py — FastAPI server for the Shotlist Timecoder.

Endpoints:
  POST /detect     — run scene detection, return shots list
  POST /match      — upload to OA, run Gemini, return timecoded results
  GET  /export/{job_id}?format=csv|txt|json — download results
  GET  /thumbnails/{job_id}/{filename}       — serve extracted frames

Job state is stored in memory (dict keyed on UUID). No database. 1-hour TTL.
The ESSO token and workflow ID are never stored — they come in via the request body.
"""
import csv
import io
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from typing import Optional

import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel

from scene_detector import detect_scenes, get_video_info
from frame_extractor import extract_frames
from shotlist_parser import parse_shotlist
from oa_matcher import OAMatcher

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

# --- Load config ---
_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")
with open(_CONFIG_PATH) as _f:
    _CFG = yaml.safe_load(_f)

_SERVER_CFG = _CFG.get("server", {})
_DET_CFG = _CFG.get("detection", {})
_JOBS_CFG = _CFG.get("jobs", {})
JOB_TTL = _JOBS_CFG.get("ttl_seconds", 3600)

# --- App ---
app = FastAPI(title="Shotlist Timecoder", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_SERVER_CFG.get("cors_origins", ["http://localhost:5173", "http://localhost:3000"]),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- In-memory job store ---
# { job_id: { "created_at": float, "shots": [...], "video_path": str,
#              "results": [...], "thumbnails_dir": str } }
_jobs: dict[str, dict] = {}


def _purge_expired_jobs() -> None:
    """Remove jobs older than JOB_TTL seconds."""
    now = time.time()
    expired = [jid for jid, j in _jobs.items() if now - j["created_at"] > JOB_TTL]
    for jid in expired:
        # Clean up temp thumbnail dir if present
        thumb_dir = _jobs[jid].get("thumbnails_dir")
        if thumb_dir and os.path.isdir(thumb_dir):
            shutil.rmtree(thumb_dir, ignore_errors=True)
        del _jobs[jid]


def _get_job(job_id: str) -> dict:
    """Retrieve a job or raise 404."""
    _purge_expired_jobs()
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found or expired.")
    return _jobs[job_id]


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class DetectRequest(BaseModel):
    """Body for POST /detect."""
    video_path: str
    threshold: float = _DET_CFG.get("threshold", 2.2)
    min_scene_len: int = _DET_CFG.get("min_scene_len", 14)
    detector: str = _DET_CFG.get("detector", "adaptive")
    luma_only: bool = _DET_CFG.get("luma_only", False)
    merge_frames: int = _DET_CFG.get("merge_frames", 0)


class MatchRequest(BaseModel):
    """Body for POST /match."""
    job_id: Optional[str] = None        # reuse detected shots from a prior /detect call
    video_path: str
    shotlist_text: str
    esso_token: str
    workflow_id: str
    # Detection params — only used if job_id is absent or shots not cached
    threshold: float = _DET_CFG.get("threshold", 2.2)
    min_scene_len: int = _DET_CFG.get("min_scene_len", 14)
    detector: str = _DET_CFG.get("detector", "adaptive")
    luma_only: bool = _DET_CFG.get("luma_only", False)
    merge_frames: int = _DET_CFG.get("merge_frames", 0)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/detect")
def detect(req: DetectRequest) -> dict:
    """
    Run scene detection on a video file.

    Creates a new job with the detected shots and returns the job_id.
    The job_id can be passed to /match to avoid re-detecting on the same video.
    """
    _purge_expired_jobs()

    try:
        shots = detect_scenes(
            req.video_path,
            threshold=req.threshold,
            min_scene_len=req.min_scene_len,
            detector=req.detector,
            luma_only=req.luma_only,
            merge_frames=req.merge_frames,
        )
        total_frames, fps = get_video_info(req.video_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Scene detection failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Scene detection error: {exc}")

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "created_at": time.time(),
        "video_path": req.video_path,
        "shots": shots,
        "results": None,
        "thumbnails_dir": None,
    }

    return {
        "job_id": job_id,
        "shots": shots,
        "video_info": {
            "path": req.video_path,
            "fps": fps,
            "total_frames": total_frames,
            "duration_seconds": round(total_frames / fps, 3) if fps else 0,
        },
        "shot_count": len(shots),
    }


@app.post("/match")
def match(req: MatchRequest) -> dict:
    """
    Full pipeline: detect shots → extract frames → parse shotlist → match via Gemini.

    If job_id is provided and the job has cached shots, reuses them.
    Otherwise runs scene detection first.
    """
    _purge_expired_jobs()

    # --- Resolve or create job ---
    if req.job_id and req.job_id in _jobs:
        job = _jobs[req.job_id]
        shots = list(job["shots"])  # copy so we can annotate without mutating the cached version
        job_id = req.job_id
    else:
        # Detect scenes fresh
        try:
            shots = detect_scenes(
                req.video_path,
                threshold=req.threshold,
                min_scene_len=req.min_scene_len,
                detector=req.detector,
                luma_only=req.luma_only,
                merge_frames=req.merge_frames,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:
            logger.exception("Scene detection failed: %s", exc)
            raise HTTPException(status_code=502, detail=f"Scene detection error: {exc}")

        job_id = str(uuid.uuid4())
        _jobs[job_id] = {
            "created_at": time.time(),
            "video_path": req.video_path,
            "shots": shots,
            "results": None,
            "thumbnails_dir": None,
        }
        job = _jobs[job_id]

    # --- Extract frames ---
    thumb_dir = tempfile.mkdtemp(prefix=f"shotlist_{job_id}_")
    job["thumbnails_dir"] = thumb_dir
    shots = extract_frames(req.video_path, shots, thumb_dir)

    # --- Parse shotlist ---
    try:
        entries = parse_shotlist(req.shotlist_text)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Shotlist parse error: {exc}")

    if not entries:
        raise HTTPException(status_code=400, detail="No entries found in shotlist.")

    # --- Match via Open Arena ---
    matcher = OAMatcher(esso_token=req.esso_token, workflow_id=req.workflow_id)
    try:
        results = matcher.match(req.video_path, shots, entries)
    except RuntimeError as exc:
        if "ESSO_TOKEN_EXPIRED" in str(exc):
            raise HTTPException(status_code=401, detail=str(exc))
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        logger.exception("OA matching failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Matching error: {exc}")

    job["results"] = results

    # Return paths relative to the thumbnails endpoint
    results_with_thumb_urls = []
    for r in results:
        row = dict(r)
        fp = row.pop("frame_path", None)
        if fp:
            row["thumbnail_url"] = f"/thumbnails/{job_id}/{os.path.basename(fp)}"
        results_with_thumb_urls.append(row)

    return {
        "job_id": job_id,
        "results": results_with_thumb_urls,
        "shot_count": len(results),
    }


@app.get("/export/{job_id}")
def export(job_id: str, format: str = "csv") -> Response:  # noqa: A002 — shadows built-in intentionally (FastAPI query param)
    """
    Export matched results.

    Supported formats: csv, txt, json (via ?format=… query parameter).
    """
    job = _get_job(job_id)
    results = job.get("results")
    if not results:
        raise HTTPException(status_code=404, detail="No results for this job. Run /match first.")

    if format == "json":
        content = json.dumps(results, indent=2)
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=shotlist_{job_id}.json"},
        )

    if format == "txt":
        lines = []
        for r in results:
            entry = r.get("matched_entry", "?")
            tc = r.get("timecode", "")
            desc = r.get("matched_description", "")
            conf = r.get("confidence", "")
            lines.append(f"{tc}  [{entry}] {desc}  ({conf})")
        content = "\n".join(lines)
        return Response(
            content=content,
            media_type="text/plain",
            headers={"Content-Disposition": f"attachment; filename=shotlist_{job_id}.txt"},
        )

    # Default: CSV
    output = io.StringIO()
    fieldnames = ["shot_index", "timecode", "matched_entry", "matched_description", "confidence", "notes"]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for r in results:
        writer.writerow(r)

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=shotlist_{job_id}.csv"},
    )


_ALLOWED_VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".avi", ".mkv", ".mxf", ".m4v", ".mts", ".m2ts",
}

@app.get("/thumbnails/{job_id}/{filename}")
def thumbnail(job_id: str, filename: str) -> FileResponse:
    """Serve an extracted thumbnail frame."""
    job = _get_job(job_id)
    thumb_dir = job.get("thumbnails_dir")
    if not thumb_dir:
        raise HTTPException(status_code=404, detail="No thumbnails for this job.")
    # Sanitise filename to prevent path traversal
    safe_name = os.path.basename(filename)
    path = os.path.join(thumb_dir, safe_name)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"Thumbnail '{safe_name}' not found.")
    return FileResponse(path, media_type="image/jpeg")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

@app.get("/video")
def stream_video(path: str, request: Request) -> Response:
    """
    Stream a local video file to the browser with HTTP range support.

    The UI passes the local file path as a query parameter. Range requests are
    required for the HTML5 video player's seek bar to work.
    """
    # Guard against path traversal / non-video files
    ext = os.path.splitext(path)[1].lower()
    if ext not in _ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext!r}")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"Video file not found: {path}")

    file_size = os.path.getsize(path)
    range_header = request.headers.get("range")

    # Determine content type from extension
    ext = os.path.splitext(path)[1].lower()
    content_type = {
        ".mp4": "video/mp4", ".mov": "video/quicktime",
        ".avi": "video/x-msvideo", ".mkv": "video/x-matroska",
        ".mxf": "application/mxf", ".m4v": "video/mp4",
        ".mts": "video/mp2t", ".m2ts": "video/mp2t",
    }.get(ext, "video/mp4")

    if range_header:
        m = re.match(r"bytes=(\d+)-(\d*)", range_header)
        start = int(m.group(1)) if m else 0
        end = int(m.group(2)) if m and m.group(2) else file_size - 1
        end = min(end, file_size - 1)
        length = end - start + 1

        def _iter():
            with open(path, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining:
                    chunk = f.read(min(65536, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return StreamingResponse(
            _iter(),
            status_code=206,
            media_type=content_type,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(length),
            },
        )

    def _iter_full():
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                yield chunk

    return StreamingResponse(
        _iter_full(),
        media_type=content_type,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
        },
    )


@app.get("/browse")
def browse() -> dict:
    """
    Open a native macOS file-picker dialog and return the chosen path.

    Calls osascript so the dialog appears on the user's desktop.
    Returns {"path": "/absolute/path/to/file"} or {"path": null} if cancelled.
    """
    script = (
        'POSIX path of (choose file '
        'with prompt "Select video file" '
        'of type {"mp4", "mov", "avi", "mxf", "mkv", "m4v", "mts", "m2ts"})'
    )
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # User cancelled — osascript exits non-zero
        return {"path": None}
    return {"path": result.stdout.strip()}


if __name__ == "__main__":
    import uvicorn
    host = _SERVER_CFG.get("host", "127.0.0.1")
    port = _SERVER_CFG.get("port", 8000)
    uvicorn.run("api:app", host=host, port=port, reload=True)
