/**
 * timecode.js — shared timecode utility functions.
 *
 * Extracted from EditorPane.jsx so that both the component and its tests
 * import the same production code rather than maintaining separate copies.
 */

/**
 * Convert a time in seconds to a HH:MM:SS:FF timecode string.
 *
 * @param {number} s   - Time in seconds.
 * @param {number} fps - Frames per second (default 25).
 * @returns {string}   Timecode in HH:MM:SS:FF format, zero-padded.
 */
export function secsToTC(s, fps = 25) {
  const f = Math.round(s * fps)
  const hh = Math.floor(f / (3600 * fps))
  const mm = Math.floor((f % (3600 * fps)) / (60 * fps))
  const ss = Math.floor((f % (60 * fps)) / fps)
  const ff = f % fps
  return [hh, mm, ss, ff].map(n => String(n).padStart(2, '0')).join(':')
}