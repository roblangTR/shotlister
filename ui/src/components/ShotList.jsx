/**
 * ShotList — right panel of the editor.
 * Displays shots grouped by dateline, with thumbnails, confidence badges,
 * review status, checkboxes, and a progress bar.
 */

const CONF = {
  high:   'bg-green-100 text-green-800 border border-green-200',
  medium: 'bg-amber-100 text-amber-800 border border-amber-200',
  low:    'bg-red-100 text-red-800 border border-red-200',
}

export default function ShotList({
  shots, selIdx, shotRefs, selIds, reviewed,
  onSelect, onToggleSel, onBulkRev, onClearSel, onHelp,
}) {
  // Group shots by location_block
  const groups = []
  let cur = null
  shots.forEach((shot, idx) => {
    const block = shot.location_block || ''
    if (!cur || block !== cur.block) { cur = { block, items: [] }; groups.push(cur) }
    cur.items.push({ shot, idx })
  })

  return (
    <div className="flex-1 flex flex-col min-w-0 overflow-hidden">

      {/* Toolbar */}
      <div className="border-b border-gray-200 px-3 py-2 flex items-center gap-3 shrink-0 bg-gray-50">
        <span className="text-xs text-gray-500">
          <span className="font-semibold text-gray-800">{reviewed}</span>/{shots.length} reviewed
        </span>
        <div className="flex-1 h-1.5 bg-gray-200 rounded-full overflow-hidden">
          <div
            className="h-full bg-green-500 rounded-full transition-all"
            style={{ width: shots.length ? `${(reviewed / shots.length) * 100}%` : '0%' }}
          />
        </div>
        {selIds.size > 0 && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-blue-700 font-medium">{selIds.size} selected</span>
            <button onClick={() => onBulkRev(true)}
              className="text-xs bg-green-600 text-white px-2 py-0.5 rounded hover:bg-green-700">
              ✓ Review all
            </button>
            <button onClick={() => onBulkRev(false)}
              className="text-xs bg-gray-200 text-gray-700 px-2 py-0.5 rounded hover:bg-gray-300">
              Unreview all
            </button>
            <button onClick={onClearSel} className="text-xs text-gray-400 hover:text-gray-600">Clear</button>
          </div>
        )}
        <button onClick={onHelp} className="text-xs text-gray-400 hover:text-gray-600 ml-auto" title="F1 — keyboard shortcuts">?</button>
      </div>

      {/* Shot rows */}
      <div className="flex-1 overflow-y-auto">
        {groups.map((group, gi) => (
          <div key={gi}>
            {/* Dateline header */}
            {group.block && (
              <div className="sticky top-0 z-10 px-3 py-1 bg-blue-50 border-b border-blue-100 text-xs text-blue-800 font-medium">
                {group.block}
              </div>
            )}

            {/* Shots in group */}
            {group.items.map(({ shot, idx }) => {
              const isSelected = idx === selIdx
              const isChecked  = selIds.has(shot.shot_index)
              const conf = shot.confidence || 'low'

              return (
                <div
                  key={shot.shot_index}
                  ref={el => { shotRefs.current[shot.shot_index] = el }}
                  onClick={() => onSelect(idx)}
                  className={`flex items-start gap-2 px-3 py-2 cursor-pointer border-b border-gray-100 transition-colors ${
                    isSelected ? 'bg-blue-50 border-l-2 border-l-blue-500' : 'hover:bg-gray-50'
                  } ${shot.is_white_flash ? 'bg-gray-50 opacity-80' : ''}`}
                >
                  {/* Checkbox */}
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={e => { e.stopPropagation(); onToggleSel(shot.shot_index) }}
                    onClick={e => e.stopPropagation()}
                    className="mt-1 shrink-0 accent-blue-600"
                  />

                  {/* Thumbnail */}
                  <div className="shrink-0 w-16 h-10 bg-gray-200 rounded overflow-hidden">
                    {shot.thumbnail_url
                      ? <img src={shot.thumbnail_url} alt="" className="w-full h-full object-cover" />
                      : shot.is_white_flash
                        ? <div className="w-full h-full bg-white border border-gray-300 flex items-center justify-center text-gray-400 text-xs">WF</div>
                        : null
                    }
                  </div>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5 mb-0.5">
                      <span className="font-mono text-xs text-gray-500 shrink-0">{shot.timecode_in || shot.timecode}</span>
                      {shot.matched_entry != null && (
                        <span className="text-xs text-gray-400 shrink-0">→ {shot.matched_entry}</span>
                      )}
                      <span className={`text-xs px-1.5 py-0.5 rounded border font-medium shrink-0 ${CONF[conf] || CONF.low}`}>
                        {conf}
                      </span>
                      {shot.human_reviewed && (
                        <span className="text-xs text-green-600 shrink-0">✓</span>
                      )}
                    </div>
                    <p className="text-xs text-gray-700 truncate">
                      {shot.matched_description || <span className="text-gray-400 italic">No match</span>}
                    </p>
                    {shot.notes && (
                      <p className="text-xs text-gray-400 italic truncate mt-0.5">{shot.notes}</p>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        ))}
      </div>
    </div>
  )
}