"""
Timecode conversion utilities for comparing frame-based timecodes.

Supported frame rates
---------------------
* 25 fps — the standard Reuters broadcast rate. All arithmetic is exact.
* 30 fps — exact integer arithmetic, no drift.

NOT supported
-------------
* 29.97 fps drop-frame (DF) — the SMPTE DF formula (skip frame counts 0 and 1
  at the start of each minute except every 10th minute) is NOT implemented.
  If a 29.97 DF timecode is passed, the ``;`` separator is detected and
  ``detect_framerate()`` returns 29.97, but ``frames_to_tc()`` /
  ``tc_to_frames()`` round 29.97 to 30 and use simple integer division.
  This produces timecodes that drift by ~2 frames/minute (~18 frames/hour),
  which is the exact problem DF notation was designed to correct.

  For Reuters editorial use all source videos are 25 fps so this limitation
  has no practical impact.  If 29.97 DF support is required in the future,
  adopt the ``timecode`` PyPI package (SMPTE-correct implementation).

Adapted from ../structured shotlists/timecode_utils.py
"""
import math


def _is_na(value) -> bool:
    """Return True if value is None, float NaN, or pandas NA (if pandas is present)."""
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    # Support pandas NA without importing pandas as a hard dependency
    try:
        import pandas as pd  # noqa: F401 — optional dependency
        if pd.isna(value):
            return True
    except (ImportError, TypeError, ValueError):
        pass
    return False


def detect_framerate(tc_string):
    """
    Detect framerate from timecode format.
    Semicolon (;) before frame number indicates 29.97fps drop frame.
    Colon (:) indicates 25fps.
    """
    if not tc_string or _is_na(tc_string):
        return 25.0
    return 29.97 if ';' in str(tc_string) else 25.0


def parse_frame_timecode(tc_string):
    """
    Parse timecode in HH:MM:SS:FF or HH:MM:SS;FF format.
    Returns dict with hours, minutes, seconds, frames, or None if invalid.
    """
    if not tc_string:
        return None
    if _is_na(tc_string):
        return None

    try:
        tc_str = str(tc_string).strip().replace(';', ':')
        parts = tc_str.split(':')
        if len(parts) != 4:
            return None
        return {
            'hours': int(parts[0]),
            'minutes': int(parts[1]),
            'seconds': int(parts[2]),
            'frames': int(parts[3])
        }
    except (ValueError, AttributeError):
        return None


def frame_tc_to_total_frames(tc_dict, fps=25.0):
    """Convert parsed frame timecode dict to total frame count."""
    if not tc_dict:
        return None
    total = tc_dict['frames']
    total += tc_dict['seconds'] * fps
    total += tc_dict['minutes'] * 60 * fps
    total += tc_dict['hours'] * 3600 * fps
    return int(total)


def tc_to_frames(tc_string):
    """Convert a HH:MM:SS:FF timecode string to total frames (auto-detects fps)."""
    fps = detect_framerate(tc_string)
    parsed = parse_frame_timecode(tc_string)
    return frame_tc_to_total_frames(parsed, fps)


def frame_tc_diff(tc_a, tc_b):
    """
    Frame difference between two HH:MM:SS:FF timecodes.
    Auto-detects fps from tc_a. Returns None if either is invalid.
    """
    fps = detect_framerate(tc_a)
    a = frame_tc_to_total_frames(parse_frame_timecode(tc_a), fps)
    b = frame_tc_to_total_frames(parse_frame_timecode(tc_b), fps)
    if a is None or b is None:
        return None
    return abs(a - b)


def frames_to_tc(total_frames, fps=25.0):
    """Convert total frame count back to HH:MM:SS:FF string.

    Uses integer modulo arithmetic to avoid float-rounding edge cases where
    ``round((frac_secs * fps))`` could equal ``fps`` (e.g. 0.9999... * 25 = 25),
    which would produce an invalid timecode such as 00:00:00:25 at 25 fps.

    .. warning::
        29.97 fps drop-frame timecodes are NOT produced correctly.  The fps
        value is rounded to 30 and simple integer division is used, which
        drifts ~18 frames per hour.  For Reuters 25 fps content this function
        is exact.  See module docstring for details.
    """
    fps_int = round(fps)
    total_frames_int = int(total_frames)
    ff = total_frames_int % fps_int
    total_secs = total_frames_int // fps_int
    hours = total_secs // 3600
    minutes = (total_secs % 3600) // 60
    seconds = total_secs % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{ff:02d}"


def categorize_accuracy(frame_diff):
    """Categorize frame difference into accuracy tiers."""
    if frame_diff is None:
        return 'Unknown'
    if frame_diff == 0:
        return 'Perfect'
    elif frame_diff <= 2:
        return 'Excellent'
    elif frame_diff <= 5:
        return 'Good'
    elif frame_diff <= 10:
        return 'Fair'
    else:
        return 'Poor'
