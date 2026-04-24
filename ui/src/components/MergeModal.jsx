/**
 * MergeModal — lets the user pick which shot's description to keep when
 * merging multiple selected shots.
 */

/**
 * @param {object}   props
 * @param {object}   props.mergeModal          - { selected: Shot[], choiceIdx: number }
 * @param {Function} props.onChoiceChange      - (index) => void
 * @param {Function} props.onConfirm           - Confirm the merge
 * @param {Function} props.onCancel            - Cancel / close modal
 */
export default function MergeModal({ mergeModal, onChoiceChange, onConfirm, onCancel }) {
  if (!mergeModal) return null
  const { selected, choiceIdx } = mergeModal

  return (
    <div className="absolute inset-0 bg-black/40 flex items-center justify-center z-40" onClick={onCancel}>
      <div className="bg-white rounded-lg shadow-xl p-6 w-[520px] max-h-[80vh] flex flex-col" onClick={e => e.stopPropagation()}>
        <h2 className="text-sm font-semibold mb-1">Merge {selected.length} shots</h2>
        <p className="text-xs text-gray-500 mb-4">
          Choose which description the merged shot should use.
          Timecode will span {selected[0].timecode_in || selected[0].timecode} → {selected[selected.length - 1].timecode_out}.
        </p>
        <div className="overflow-y-auto flex flex-col gap-2 flex-1 mb-4">
          {selected.map((shot, i) => (
            <label key={shot.shot_index}
              className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                choiceIdx === i
                  ? 'border-blue-500 bg-blue-50'
                  : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
              }`}>
              <input type="radio" name="merge-choice" checked={choiceIdx === i}
                onChange={() => onChoiceChange(i)}
                className="mt-0.5 shrink-0 accent-blue-600" />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-mono text-xs text-gray-500">{shot.timecode_in || shot.timecode}</span>
                  {shot.matched_entry != null && (
                    <span className="text-xs text-gray-400">→ entry {shot.matched_entry}</span>
                  )}
                  <span className={`text-xs px-1.5 py-0.5 rounded border font-medium ${
                    shot.confidence === 'high'   ? 'bg-green-100 text-green-800 border-green-200' :
                    shot.confidence === 'medium' ? 'bg-amber-100 text-amber-800 border-amber-200' :
                                                   'bg-red-100 text-red-800 border-red-200'
                  }`}>{shot.confidence}</span>
                </div>
                <p className="text-xs text-gray-700 font-mono leading-relaxed">
                  {shot.matched_description || <span className="text-gray-400 italic">No description</span>}
                </p>
                {shot.notes && <p className="text-xs text-gray-400 italic mt-1">{shot.notes}</p>}
              </div>
            </label>
          ))}
        </div>
        <div className="flex gap-2 justify-end shrink-0">
          <button onClick={onCancel} className="text-sm px-4 py-1.5 border border-gray-300 rounded hover:bg-gray-50">Cancel</button>
          <button onClick={onConfirm} className="text-sm px-4 py-1.5 bg-purple-600 text-white rounded hover:bg-purple-700 font-medium">
            Merge with this description
          </button>
        </div>
      </div>
    </div>
  )
}