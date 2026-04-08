"""
frame_extractor.py — OpenCV-based thumbnail extraction for detected shots.

For each detected shot, extracts a representative JPEG frame offset_seconds
after the cut point. If the shot is shorter than offset_seconds, uses the
midpoint of the shot instead.
"""
import logging
import os
from pathlib import Path

import cv2

logger = logging.getLogger(__name__)

_DEFAULT_QUALITY = 85   # JPEG quality (0-100)


def extract_frames(
    video_path: str,
    shots: list[dict],
    output_dir: str,
    offset_seconds: float = 0.5,
) -> list[dict]:
    """
    Extract a representative JPEG frame for each detected shot.

    Opens the video once and seeks to each shot's target frame. Saves images
    as `shot_{index:04d}.jpg` in output_dir. Returns the shots list with a
    'frame_path' key added to each entry (absolute path to the saved JPEG).

    If the video cannot be opened, logs an error and returns the shots list
    unchanged (frame_path will be absent).

    Args:
        video_path: Path to the source video file.
        shots: List of shot dicts from detect_scenes() (modified in-place).
        output_dir: Directory to write JPEG thumbnails into (must exist or
            will be created).
        offset_seconds: How many seconds after the cut point to sample.
            Clamped to the midpoint of the shot if the shot is shorter.

    Returns:
        The shots list with 'frame_path' added to each entry.
    """
    path = str(video_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        logger.error("frame_extractor: cannot open video '%s'", path)
        return shots

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if fps <= 0:
        logger.error("frame_extractor: invalid fps (%s) for '%s'", fps, path)
        cap.release()
        return shots

    offset_frames = int(offset_seconds * fps)

    for i, shot in enumerate(shots):
        start_frame = shot.get("frame_number", 0)

        # Determine the frame number of the next shot (or end of video)
        if i + 1 < len(shots):
            next_frame = shots[i + 1].get("frame_number", total_frames)
        else:
            next_frame = total_frames

        shot_len = next_frame - start_frame

        # Clamp to midpoint if the shot is shorter than offset
        if shot_len > 0 and offset_frames >= shot_len:
            target_frame = start_frame + max(1, shot_len // 2)
        else:
            target_frame = start_frame + offset_frames

        # Clamp to valid range
        target_frame = max(0, min(target_frame, total_frames - 1))

        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        ret, frame = cap.read()

        if not ret or frame is None:
            logger.warning(
                "frame_extractor: could not read frame %d for shot %d — skipping thumbnail",
                target_frame, i,
            )
            continue

        out_path = out_dir / f"shot_{i:04d}.jpg"
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, _DEFAULT_QUALITY]
        cv2.imwrite(str(out_path), frame, encode_params)
        shot["frame_path"] = str(out_path)

    cap.release()
    return shots
