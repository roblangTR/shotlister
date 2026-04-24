/**
 * HelpModal — keyboard shortcuts reference dialog.
 */

/**
 * @param {object}   props
 * @param {boolean}  props.show     - Whether the modal is visible
 * @param {Function} props.onClose  - Close the modal
 */
export default function HelpModal({ show, onClose }) {
  if (!show) return null

  const shortcuts = [
    ['← / →',     'Previous / Next shot'],
    ['Home / End', 'First / Last shot'],
    ['Space',      'Play / Pause'],
    ['I',          'Set IN point from playhead'],
    ['O',          'Set OUT point from playhead'],
    ['R',          'Toggle reviewed'],
    ['S',          'Split shot at playhead'],
    ['M',          'Merge shot with next'],
    ['W',          'White Flash modal'],
    ['Delete',     'Delete selected shot'],
    ['Ctrl+Z',     'Undo'],
    ['Ctrl+Y',     'Redo'],
    ['F1',         'This help'],
  ]

  return (
    <div className="absolute inset-0 bg-black/40 flex items-center justify-center z-40" onClick={onClose}>
      <div className="bg-white rounded-lg shadow-xl p-6 w-[480px] max-h-[80vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold">Keyboard Shortcuts</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-lg leading-none">×</button>
        </div>
        <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs">
          {shortcuts.map(([k, v]) => (
            <div key={k} className="flex items-center gap-2 py-1 border-b border-gray-100">
              <kbd className="bg-gray-100 border border-gray-300 rounded px-1.5 py-0.5 font-mono text-gray-700 shrink-0">{k}</kbd>
              <span className="text-gray-600">{v}</span>
            </div>
          ))}
        </div>
        <p className="text-xs text-gray-400 mt-4">Shortcuts work when not typing in a field.</p>
      </div>
    </div>
  )
}