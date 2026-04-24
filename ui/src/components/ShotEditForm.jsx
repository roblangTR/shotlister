/**
 * ShotEditForm — detail editing panel for the selected shot.
 *
 * Displays and edits: timecodes, matched entry, description,
 * confidence, notes, and dateline fields.
 */

/**
 * @param {object}   props
 * @param {object}   props.sel             - The currently selected shot object
 * @param {number}   props.selIdx          - Index of the selected shot
 * @param {number}   props.totalShots      - Total shot count
 * @param {any[]}    props.shots           - Full shots array
 * @param {any[]}    props.shotlistEntries - Parsed shotlist entries for the reassign dropdown
 * @param {Function} props.onToggleReview  - Toggle human_reviewed on current shot
 * @param {Function} props.onSplit         - Split at playhead
 * @param {Function} props.onMerge         - Merge with next shot
 * @param {Function} props.onWF            - Open white-flash modal
 * @param {Function} props.onDelete        - Delete current shot
 * @param {Function} props.onFieldChange   - (fieldName, value) => void
 * @param {Function} props.onReassign      - (entryNumber) => void — reassign matched entry
 */
export default function ShotEditForm({
  sel, selIdx, totalShots, shots, shotlistEntries,
  onToggleReview, onSplit, onMerge, onWF, onDelete,
  onFieldChange, onReassign,
}) {
  if (!sel) return null

  return (
    <div className="p-3 flex flex-col gap-3 overflow-y-auto flex-1">

      {/* Header row — shot label + action buttons */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
          Shot {selIdx + 1}
          {sel.is_white_flash && (
            <span className="ml-1 bg-gray-800 text-white px-1 rounded normal-case font-normal">WF</span>
          )}
        </span>
        <div className="flex gap-1 flex-wrap">
          <button onClick={onToggleReview} title="R"
            className={`text-xs px-2 py-0.5 rounded border font-medium ${
              sel.human_reviewed
                ? 'bg-green-100 text-green-800 border-green-300'
                : 'bg-gray-100 text-gray-600 border-gray-300 hover:bg-gray-200'
            }`}>
            {sel.human_reviewed ? '✓' : 'Rev'}
          </button>
          <button onClick={onSplit} title="S — split at playhead"
            className="text-xs px-2 py-0.5 rounded border border-blue-300 text-blue-700 hover:bg-blue-50 font-medium">Split</button>
          <button onClick={onMerge} disabled={selIdx >= totalShots - 1} title="M — merge with next"
            className="text-xs px-2 py-0.5 rounded border border-purple-300 text-purple-700 hover:bg-purple-50 font-medium disabled:opacity-40">Merge</button>
          <button onClick={onWF} title="W"
            className="text-xs px-2 py-0.5 rounded border-2 border-gray-900 font-bold hover:bg-gray-100">WF</button>
          <button onClick={onDelete} title="Del"
            className="text-xs px-2 py-0.5 rounded border border-red-300 text-red-600 hover:bg-red-50">✕</button>
        </div>
      </div>

      {/* IN / OUT timecodes */}
      <div className="grid grid-cols-2 gap-2">
        <label className="flex flex-col gap-0.5">
          <span className="text-xs text-gray-500">IN <kbd className="border border-gray-300 rounded px-0.5 text-gray-400 text-xs">I</kbd></span>
          <input type="text" value={sel.timecode_in || sel.timecode || ''} placeholder="00:00:00:00"
            onChange={e => onFieldChange('timecode_in', e.target.value)}
            className="border border-gray-300 rounded px-2 py-1 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-blue-400" />
        </label>
        <label className="flex flex-col gap-0.5">
          <span className="text-xs text-gray-500">OUT <kbd className="border border-gray-300 rounded px-0.5 text-gray-400 text-xs">O</kbd></span>
          <input type="text" value={sel.timecode_out || ''} placeholder="00:00:00:00"
            onChange={e => onFieldChange('timecode_out', e.target.value)}
            className="border border-gray-300 rounded px-2 py-1 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-blue-400" />
        </label>
      </div>

      {/* Matched entry dropdown */}
      <label className="flex flex-col gap-0.5">
        <span className="text-xs text-gray-500">Matched entry</span>
        <select value={sel.matched_entry ?? ''} onChange={e => onReassign(e.target.value)}
          className="border border-gray-300 rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-400">
          <option value="">— none —</option>
          {shotlistEntries.map(e => (
            <option key={e.entry_number} value={e.entry_number}>
              {e.entry_number}. {e.description.slice(0, 55)}{e.description.length > 55 ? '…' : ''}
            </option>
          ))}
        </select>
      </label>

      {/* Description */}
      <label className="flex flex-col gap-0.5">
        <span className="text-xs text-gray-500">Description</span>
        <textarea value={sel.matched_description || ''} rows={3}
          onChange={e => onFieldChange('matched_description', e.target.value)}
          className="border border-gray-300 rounded px-2 py-1 text-xs font-mono resize-y focus:outline-none focus:ring-1 focus:ring-blue-400" />
      </label>

      {/* Confidence */}
      <label className="flex flex-col gap-0.5">
        <span className="text-xs text-gray-500">Confidence</span>
        <select value={sel.confidence || 'low'} onChange={e => onFieldChange('confidence', e.target.value)}
          className="border border-gray-300 rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-400">
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
      </label>

      {/* Notes */}
      <label className="flex flex-col gap-0.5">
        <span className="text-xs text-gray-500">Notes</span>
        <textarea value={sel.notes || ''} rows={2}
          onChange={e => onFieldChange('notes', e.target.value)}
          className="border border-gray-300 rounded px-2 py-1 text-xs resize-y focus:outline-none focus:ring-1 focus:ring-blue-400" />
      </label>

      {/* Dateline fields */}
      {(sel.location || sel.date || sel.source || sel.restrictions) && (
        <div className="border-t border-gray-100 pt-3 flex flex-col gap-2">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Dateline</span>
          {sel.location && (
            <div className="flex gap-1.5 items-start">
              <span className="text-xs text-gray-400 w-20 shrink-0">Location</span>
              <span className="text-xs text-gray-700">{sel.location}</span>
            </div>
          )}
          {sel.date && (
            <div className="flex gap-1.5 items-start">
              <span className="text-xs text-gray-400 w-20 shrink-0">Date</span>
              <span className="text-xs text-gray-700">{sel.date}</span>
            </div>
          )}
          {sel.source && (
            <div className="flex gap-1.5 items-start">
              <span className="text-xs text-gray-400 w-20 shrink-0">Source</span>
              <span className="text-xs text-gray-700">{sel.source}</span>
            </div>
          )}
          {/* Show split Broadcast/Digital if available, otherwise raw restrictions */}
          {(sel.restrictions_broadcast || sel.restrictions_digital)
            ? <>
                {sel.restrictions_broadcast && (
                  <div className="flex gap-1.5 items-start">
                    <span className="text-xs text-gray-400 w-20 shrink-0">Broadcast</span>
                    <span className="text-xs text-gray-700">{sel.restrictions_broadcast}</span>
                  </div>
                )}
                {sel.restrictions_digital && (
                  <div className="flex gap-1.5 items-start">
                    <span className="text-xs text-gray-400 w-20 shrink-0">Digital</span>
                    <span className="text-xs text-gray-700">{sel.restrictions_digital}</span>
                  </div>
                )}
              </>
            : sel.restrictions && (
                <div className="flex gap-1.5 items-start">
                  <span className="text-xs text-gray-400 w-20 shrink-0">Restrictions</span>
                  <span className="text-xs text-gray-700">{sel.restrictions}</span>
                </div>
              )
          }
        </div>
      )}
    </div>
  )
}