"""
mcp_server.py — FastMCP stdio server for the Shotlist Timecoder.

Exposes two tools to Claude Desktop (and any MCP-compatible client):

  detect_shots     — run PySceneDetect on a local video file
  match_shotlist   — full pipeline: detect + parse + Gemini match

The ESSO token and workflow ID are supplied at call time by the user —
never stored on disk or in config.

Claude Desktop config entry (add to claude_desktop_config.json):
  "shotlist-timecoder": {
    "command": "python",
    "args": ["/Users/lng3369/Documents/Claude/2026/shotlist_timecoder/mcp_server.py"],
    "env": {}
  }
"""
import csv
import io
import logging
import os
import sys
import tempfile

# Ensure the project directory is on the path when invoked via MCP
_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_DIR not in sys.path:
    sys.path.insert(0, _PROJECT_DIR)

from mcp.server.fastmcp import FastMCP

from scene_detector import detect_scenes, get_video_info
from shotlist_parser import parse_shotlist
from oa_matcher import OAMatcher

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

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
    Detect shot cuts in a local video file using PySceneDetect.

    The first shot always starts at 00:00:00:00 (the beginning of the video).
    Subsequent shots represent detected scene cuts.

    Args:
        video_path: Absolute path to the video file on the local filesystem.
        threshold: AdaptiveDetector sensitivity. Lower = more cuts detected.
            Range 1.5–4.0. Default: 2.2 (tuned on Reuters test set).
        min_scene_len: Minimum scene length in frames. Suppresses flash cuts.
            Default: 14 (≈ 0.56 s at 25 fps).
        detector: Detection algorithm — 'adaptive' (default) or 'content'.
        luma_only: Analyse only the luminance channel. Reduces false positives
            from colour-graphic overlays.
        merge_frames: Post-processing: merge cuts within this many frames of
            each other. 0 = disabled.

    Returns:
        dict with:
          shots:      list of {shot_index, timecode, frame_number, seconds}
          video_info: {fps, total_frames, duration_seconds, path}
          shot_count: int
    """
    try:
        shots = detect_scenes(
            video_path,
            threshold=threshold,
            min_scene_len=min_scene_len,
            detector=detector,
            luma_only=luma_only,
            merge_frames=merge_frames,
        )
        total_frames, fps = get_video_info(video_path)
    except ValueError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        logger.exception("detect_shots failed: %s", exc)
        return {"error": f"Scene detection error: {exc}"}

    return {
        "shots": shots,
        "video_info": {
            "path": video_path,
            "fps": fps,
            "total_frames": total_frames,
            "duration_seconds": round(total_frames / fps, 3) if fps else 0,
        },
        "shot_count": len(shots),
    }


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
    Full pipeline: detect shots in a video, parse a Reuters shotlist, and
    use Gemini via Open Arena to match each detected shot to a shotlist entry.

    The ESSO token is your personal daily Reuters authentication token.
    It is used only for this request and is never stored anywhere.

    The workflow_id is the Open Arena UUID for a Gemini video-analysis workflow.

    Args:
        video_path: Absolute path to the video file on the local filesystem.
        shotlist_text: Raw Reuters-format shotlist text (paste directly).
        esso_token: Daily ESSO authentication token (personal, session only).
        workflow_id: Open Arena workflow UUID for Gemini video analysis.
        threshold: Scene detection threshold (default 2.2).
        min_scene_len: Minimum scene length in frames (default 14).

    Returns:
        dict with:
          results:  list of matched shot dicts with timecodes and shotlist entries
          csv:      formatted CSV string ready to paste or save
          summary:  {total_shots, matched, unmatched, high_confidence, low_confidence}
    """
    # --- Detect scenes ---
    try:
        shots = detect_scenes(
            video_path,
            threshold=threshold,
            min_scene_len=min_scene_len,
        )
    except ValueError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        logger.exception("detect_scenes failed in match_shotlist: %s", exc)
        return {"error": f"Scene detection error: {exc}"}

    # --- Parse shotlist ---
    try:
        entries = parse_shotlist(shotlist_text)
    except Exception as exc:
        return {"error": f"Shotlist parse error: {exc}"}

    if not entries:
        return {"error": "No entries found in shotlist."}

    # --- Extract frames (optional — into a temp dir) ---
    thumb_dir = tempfile.mkdtemp(prefix="shotlist_mcp_")
    try:
        from frame_extractor import extract_frames
        shots = extract_frames(video_path, shots, thumb_dir)
    except Exception as exc:
        logger.warning("Frame extraction failed (non-fatal): %s", exc)

    # --- Match via Open Arena ---
    matcher = OAMatcher(esso_token=esso_token, workflow_id=workflow_id)
    try:
        results = matcher.match(video_path, shots, entries)
    except RuntimeError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        logger.exception("OA matching failed: %s", exc)
        return {"error": f"Matching error: {exc}"}

    # --- Build CSV string ---
    buf = io.StringIO()
    fieldnames = ["shot_index", "timecode", "matched_entry", "matched_description", "confidence", "notes"]
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for r in results:
        writer.writerow(r)
    csv_str = buf.getvalue()

    # --- Summary ---
    matched = sum(1 for r in results if r.get("matched_entry") is not None)
    high_conf = sum(1 for r in results if r.get("confidence") == "high")
    low_conf = sum(1 for r in results if r.get("confidence") == "low")

    return {
        "results": results,
        "csv": csv_str,
        "summary": {
            "total_shots": len(results),
            "matched": matched,
            "unmatched": len(results) - matched,
            "high_confidence": high_conf,
            "low_confidence": low_conf,
        },
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
