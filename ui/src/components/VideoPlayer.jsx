/**
 * VideoPlayer — video element with timecode overlay and prev/next navigation.
 */

/**
 * @param {object}   props
 * @param {string}   props.videoPath  - Local path streamed via /video?path=…
 * @param {object}   props.videoRef   - Forwarded ref to the <video> element
 * @param {string}   props.tc         - Current timecode string (HH:MM:SS:FF)
 * @param {number}   props.selIdx     - Currently selected shot index (0-based)
 * @param {number}   props.totalShots - Total number of shots
 * @param {Function} props.onPrev     - Go to previous shot
 * @param {Function} props.onNext     - Go to next shot
 */
export default function VideoPlayer({ videoPath, videoRef, tc, selIdx, totalShots, onPrev, onNext }) {
  return (
    <div className="p-3 border-b border-gray-100">
      <div className="relative bg-black rounded overflow-hidden">
        {videoPath
          ? <video ref={videoRef} src={`/video?path=${encodeURIComponent(videoPath)}`} controls className="w-full" />
          : <div className="h-40 flex items-center justify-center text-xs text-gray-400">No video</div>
        }
        <div className="absolute bottom-8 left-2 bg-black/75 text-white font-mono text-xs px-2 py-0.5 rounded pointer-events-none select-none">
          {tc}
        </div>
      </div>
      <div className="flex items-center gap-2 mt-2">
        <button onClick={onPrev} disabled={selIdx === 0}
          className="flex-1 text-xs border border-gray-300 rounded py-1 hover:bg-gray-50 disabled:opacity-40">← Prev</button>
        <span className="text-xs text-gray-400 shrink-0">{selIdx + 1} / {totalShots}</span>
        <button onClick={onNext} disabled={selIdx >= totalShots - 1}
          className="flex-1 text-xs border border-gray-300 rounded py-1 hover:bg-gray-50 disabled:opacity-40">Next →</button>
      </div>
    </div>
  )
}