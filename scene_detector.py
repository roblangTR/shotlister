"""
scene_detector.py — self-contained PySceneDetect wrapper.

Does NOT depend on any external path outside this project directory.
Implements get_video_info, frames_to_timecode, and detect_scenes locally.
The detect_scenes() core logic is copied from shot_detector/evaluator.py
(_detect_scenes function), adapted to return structured dicts and always
include the frame-0 entry as the first shot.
"""
import json
import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def get_video_info(video_path: str) -> tuple[int, float]:
    """
    Return (total_frames, fps) for a video file.

    Tries ffprobe first (accurate, handles variable frame rates correctly).
    Falls back to cv2.VideoCapture if ffprobe is not on PATH.

    Args:
        video_path: Path to the video file.

    Returns:
        Tuple of (total_frames: int, fps: float).

    Raises:
        ValueError: If the file cannot be read or frame rate cannot be determined.
    """
    path = str(video_path)

    # --- ffprobe path ---
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_streams",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            info = json.loads(result.stdout)
            streams = info.get("streams", [])
            if streams:
                s = streams[0]
                # r_frame_rate is a fraction string like "25/1" or "30000/1001"
                r_frame_rate = s.get("r_frame_rate", "")
                def _parse_rate(rate_str: str) -> float:
                    """Parse a fraction string like '25/1' or '30000/1001'."""
                    if "/" in rate_str:
                        num, den = rate_str.split("/")
                        n, d = float(num), float(den)
                        return n / d if d != 0 else 0.0
                    return float(rate_str) if rate_str else 0.0

                fps = _parse_rate(r_frame_rate)
                # Fallback to avg_frame_rate if r_frame_rate is 0/0
                if fps <= 0:
                    fps = _parse_rate(s.get("avg_frame_rate", ""))

                # nb_frames may be absent in some containers — fall back to duration
                nb_frames = s.get("nb_frames")
                if nb_frames and nb_frames != "N/A":
                    total_frames = int(nb_frames)
                else:
                    duration = float(s.get("duration", 0))
                    total_frames = int(duration * fps)

                if fps > 0:
                    return total_frames, fps
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError, KeyError, ValueError) as exc:
        logger.debug("ffprobe unavailable or failed (%s) — falling back to cv2.", exc)

    # --- cv2 fallback ---
    try:
        import cv2
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            raise ValueError(f"Cannot open video file: {path}")
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
        if fps <= 0:
            raise ValueError(f"Could not determine frame rate for: {path}")
        return total_frames, fps
    except ImportError:
        pass

    raise ValueError(f"Cannot read video info for: {path}. Install ffprobe or opencv-python.")


def frames_to_timecode(frame_num: int, fps: float) -> str:
    """
    Convert a frame number to a HH:MM:SS:FF timecode string.

    Args:
        frame_num: Zero-based frame number.
        fps: Frames per second (e.g. 25.0).

    Returns:
        Timecode string in HH:MM:SS:FF format.
    """
    total_seconds = frame_num / fps
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)
    frames = int(round((total_seconds - int(total_seconds)) * fps))
    # Guard against rounding frames up to fps value
    if frames >= int(fps):
        frames = int(fps) - 1
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frames:02d}"


def detect_scenes(
    video_path: str,
    threshold: float = 2.2,
    min_scene_len: int = 14,
    detector: str = "adaptive",
    luma_only: bool = False,
    merge_frames: int = 0,
) -> list[dict]:
    """
    Run PySceneDetect on a video and return a list of shot dicts.

    The first entry is always shot 0 at frame 0 / timecode 00:00:00:00.
    Subsequent entries represent detected scene cuts.

    Core detection logic copied verbatim from shot_detector/evaluator.py
    (_detect_scenes function) — only the return type differs (dicts vs strings).

    Args:
        video_path: Path to the video file.
        threshold: AdaptiveDetector adaptive_threshold or ContentDetector threshold.
        min_scene_len: Minimum scene length in frames (suppresses flash cuts).
        detector: 'adaptive' (AdaptiveDetector) or 'content' (ContentDetector).
        luma_only: Analyse only the luminance channel (reduces colour-graphic FPs).
        merge_frames: Post-processing: merge cuts within this many frames. 0 = off.

    Returns:
        List of shot dicts, one per detected cut (including the video start):
        [
          {
            "shot_index": 0,
            "timecode": "00:00:00:00",
            "frame_number": 0,
            "seconds": 0.0,
          },
          ...
        ]

    Raises:
        ValueError: If the video cannot be opened or detection fails.
    """
    from scenedetect import open_video, SceneManager
    from scenedetect.detectors import ContentDetector, AdaptiveDetector

    path = str(video_path)
    if not Path(path).exists():
        raise ValueError(f"Video file not found: {path}")

    _, frame_rate = get_video_info(path)

    try:
        video = open_video(path)
    except Exception as exc:
        raise ValueError(f"PySceneDetect could not open video '{path}': {exc}") from exc

    sm = SceneManager()

    if detector == "adaptive":
        sm.add_detector(AdaptiveDetector(
            adaptive_threshold=threshold,
            min_scene_len=min_scene_len,
            luma_only=luma_only,
        ))
    else:
        sm.add_detector(ContentDetector(
            threshold=threshold,
            min_scene_len=min_scene_len,
            luma_only=luma_only,
        ))

    sm.detect_scenes(video)
    scene_list = sm.get_scene_list()
    frame_numbers = [s[0].get_frames() for s in scene_list]

    # Post-processing: drop any boundary within merge_frames of the previous one.
    # Flash frames produce two boundaries (before + after the flash) — merging
    # collapses these pairs into the first boundary, the true cut.
    if merge_frames > 0 and frame_numbers:
        merged = [frame_numbers[0]]
        for f in frame_numbers[1:]:
            if (f - merged[-1]) > merge_frames:
                merged.append(f)
        frame_numbers = merged

    # PySceneDetect may not include frame 0 as the first cut —
    # always prepend it so the first shot always starts at the beginning.
    if not frame_numbers or frame_numbers[0] != 0:
        frame_numbers = [0] + frame_numbers

    shots = []
    for idx, frame_num in enumerate(frame_numbers):
        tc = frames_to_timecode(frame_num, frame_rate)
        shots.append({
            "shot_index": idx,
            "timecode": tc,
            "frame_number": frame_num,
            "seconds": round(frame_num / frame_rate, 3),
        })

    return shots


if __name__ == "__main__":
    import sys
    import json as _json

    if len(sys.argv) < 2:
        print("Usage: python scene_detector.py <video_path> [threshold] [min_scene_len]")
        sys.exit(1)

    vpath = sys.argv[1]
    thr = float(sys.argv[2]) if len(sys.argv) > 2 else 2.2
    msl = int(sys.argv[3]) if len(sys.argv) > 3 else 14

    shots = detect_scenes(vpath, threshold=thr, min_scene_len=msl)
    total_frames, fps = get_video_info(vpath)
    print(_json.dumps({
        "video": {"path": vpath, "fps": fps, "total_frames": total_frames},
        "shot_count": len(shots),
        "shots": shots,
    }, indent=2))
