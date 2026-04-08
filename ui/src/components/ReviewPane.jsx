/**
 * ReviewPane — two-column editorial review surface.
 *
 * Left:  video player with seek on shot-row click.
 * Right: matched shots table — timecode, thumb, full match description,
 *        confidence badge, reassignment dropdown.
 */
import { useRef } from 'react'

const CONFIDENCE_STYLES = {
  high:   'bg-green-100 text-green-800',
  medium: 'bg-amber-100 text-amber-800',
  low:    'bg-red-100 text-red-800',
}

export default function ReviewPane({ results, shotlistEntries, onResultsChange, videoPath }) {
  const videoRef = useRef(null)

  function seekTo(seconds) {
    if (videoRef.current) {
      videoRef.current.currentTime = seconds
      videoRef.current.play().catch(() => {})
    }
  }

  function handleReassign(shotIndex, newEntryNumber) {
    const entry = shotlistEntries.find(e => e.entry_number === parseInt(newEntryNumber, 10))
    const updated = results.map(r =>
      r.shot_index === shotIndex
        ? {
            ...r,
            matched_entry: newEntryNumber ? parseInt(newEntryNumber, 10) : null,
            matched_description: entry ? entry.description : '',
            confidence: 'medium',
          }
        : r
    )
    onResultsChange(updated)
  }

  return (
    <div className="flex-1 min-h-0 bg-white rounded-lg border border-gray-200 overflow-hidden flex">
      {/* Left: video player — fixed width */}
      <div className="w-72 shrink-0 border-r border-gray-200 flex flex-col p-3 gap-2">
        <h3 className="text-xs font-semibold text-gray-600 uppercase tracking-wide">Preview</h3>
        {videoPath ? (
          <video
            ref={videoRef}
            src={`/video?path=${encodeURIComponent(videoPath)}`}
            controls
            className="w-full rounded bg-black"
          />
        ) : (
          <div className="flex-1 bg-gray-100 rounded flex items-center justify-center text-xs text-gray-400">
            No video
          </div>
        )}
        <p className="text-xs text-gray-400">Click a row to seek.</p>
      </div>

      {/* Right: shots table — fills remaining width, scrolls vertically */}
      <div className="flex-1 overflow-y-auto">
        <table className="w-full text-sm border-collapse table-fixed">
          <colgroup>
            <col style={{ width: '7rem' }} />
            <col style={{ width: '5rem' }} />
            <col />  {/* Match — takes all remaining width */}
            <col style={{ width: '5rem' }} />
            <col style={{ width: '11rem' }} />
          </colgroup>
          <thead className="bg-gray-50 sticky top-0 z-10">
            <tr>
              <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Timecode</th>
              <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Thumb</th>
              <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Match</th>
              <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Conf</th>
              <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Reassign</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {results.map(shot => (
              <tr
                key={shot.shot_index}
                className="hover:bg-blue-50 cursor-pointer transition-colors"
                onClick={() => seekTo(shot.seconds || 0)}
              >
                <td className="px-3 py-2 font-mono text-xs whitespace-nowrap text-gray-700 align-top pt-3">
                  {shot.timecode}
                </td>
                <td className="px-3 py-2 align-top pt-3">
                  {shot.thumbnail_url ? (
                    <img src={shot.thumbnail_url} alt={`Shot ${shot.shot_index}`}
                      className="w-16 h-10 object-cover rounded" />
                  ) : (
                    <div className="w-16 h-10 bg-gray-200 rounded" />
                  )}
                </td>
                <td className="px-3 py-2 align-top pt-3">
                  {shot.matched_entry !== null && shot.matched_entry !== undefined ? (
                    <div>
                      <span className="font-semibold text-gray-800">{shot.matched_entry}. </span>
                      <span className="text-gray-700">{shot.matched_description || '—'}</span>
                      {shot.notes && (
                        <p className="text-xs text-gray-400 mt-0.5 italic">{shot.notes}</p>
                      )}
                    </div>
                  ) : (
                    <span className="text-gray-400 italic text-xs">No match</span>
                  )}
                </td>
                <td className="px-3 py-2 align-top pt-3">
                  <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${CONFIDENCE_STYLES[shot.confidence] || CONFIDENCE_STYLES.low}`}>
                    {shot.confidence || 'low'}
                  </span>
                </td>
                <td className="px-3 py-2 align-top pt-2" onClick={e => e.stopPropagation()}>
                  <select
                    value={shot.matched_entry ?? ''}
                    onChange={e => handleReassign(shot.shot_index, e.target.value)}
                    className="text-xs border border-gray-300 rounded px-1 py-0.5 w-full"
                  >
                    <option value="">— none —</option>
                    {shotlistEntries.map(entry => (
                      <option key={entry.entry_number} value={entry.entry_number}>
                        {entry.entry_number}. {entry.description.slice(0, 50)}
                        {entry.description.length > 50 ? '…' : ''}
                      </option>
                    ))}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
