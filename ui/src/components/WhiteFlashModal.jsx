/**
 * WhiteFlashModal — dialog for inserting a white-flash shot at the playhead.
 */

/**
 * @param {object}   props
 * @param {boolean}  props.show       - Whether the modal is visible
 * @param {string}   props.tc         - Current playhead timecode (display only)
 * @param {number}   props.wfF        - White-flash duration in frames
 * @param {Function} props.onFrameChange - (frames: number) => void
 * @param {Function} props.onConfirm  - Insert the white flash
 * @param {Function} props.onCancel   - Close without inserting
 */
export default function WhiteFlashModal({ show, tc, wfF, onFrameChange, onConfirm, onCancel }) {
  if (!show) return null

  return (
    <div className="absolute inset-0 bg-black/40 flex items-center justify-center z-40" onClick={onCancel}>
      <div className="bg-white rounded-lg shadow-xl p-6 w-80" onClick={e => e.stopPropagation()}>
        <h2 className="text-sm font-semibold mb-1">Add White Flash</h2>
        <p className="text-xs text-gray-500 mb-4">Inserts a white flash at the current playhead position ({tc}).</p>
        <label className="flex items-center gap-3 mb-4">
          <span className="text-xs text-gray-600">Duration (frames)</span>
          <input type="number" min={1} max={10} value={wfF}
            onChange={e => onFrameChange(Number(e.target.value))}
            className="w-16 border border-gray-300 rounded px-2 py-1 text-sm text-center focus:outline-none focus:ring-1 focus:ring-blue-400" />
        </label>
        <p className="text-xs text-gray-400 mb-4">White flashes are used between soundbites in video editing.</p>
        <div className="flex gap-2 justify-end">
          <button onClick={onCancel} className="text-sm px-4 py-1.5 border border-gray-300 rounded hover:bg-gray-50">Cancel</button>
          <button onClick={onConfirm} className="text-sm px-4 py-1.5 bg-gray-900 text-white rounded hover:bg-gray-700 font-medium">Add White Flash</button>
        </div>
      </div>
    </div>
  )
}