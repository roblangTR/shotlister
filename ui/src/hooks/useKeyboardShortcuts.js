/**
 * useKeyboardShortcuts — registers global keydown handlers for the editor.
 *
 * All handler functions are passed in as props so this hook has no direct
 * state dependencies — it purely wires keyboard events to callbacks.
 *
 * @param {object} handlers
 * @param {Function} handlers.onPrev          - Navigate to previous shot
 * @param {Function} handlers.onNext          - Navigate to next shot
 * @param {Function} handlers.onFirst         - Navigate to first shot
 * @param {Function} handlers.onLast          - Navigate to last shot
 * @param {Function} handlers.onPlayPause     - Toggle video play/pause
 * @param {Function} handlers.onReview        - Toggle review flag
 * @param {Function} handlers.onSplit         - Split shot at playhead
 * @param {Function} handlers.onMerge         - Merge with next shot
 * @param {Function} handlers.onWF            - Open white-flash modal
 * @param {Function} handlers.onSetIn         - Set IN point from playhead
 * @param {Function} handlers.onSetOut        - Set OUT point from playhead
 * @param {Function} handlers.onDelete        - Delete current shot
 * @param {Function} handlers.onHelp          - Open help modal
 * @param {Function} handlers.onUndo          - Undo
 * @param {Function} handlers.onRedo          - Redo
 * @param {boolean}  handlers.canUndo         - Whether undo is available
 * @param {boolean}  handlers.canRedo         - Whether redo is available
 * @param {any[]}    deps                     - Extra useEffect dependencies
 */
import { useEffect } from 'react'

export function useKeyboardShortcuts(handlers, deps = []) {
  const {
    onPrev, onNext, onFirst, onLast,
    onPlayPause, onReview, onSplit, onMerge,
    onWF, onSetIn, onSetOut, onDelete, onHelp,
    onUndo, onRedo, canUndo, canRedo,
  } = handlers

  useEffect(() => {
    const onKey = e => {
      const inField = ['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)

      // Undo / Redo — work even when typing in a field
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key === 'z') {
        e.preventDefault()
        if (canUndo) onUndo()
        return
      }
      if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || (e.shiftKey && e.key === 'Z'))) {
        e.preventDefault()
        if (canRedo) onRedo()
        return
      }

      if (inField) return

      if      (e.key === 'ArrowLeft')  { e.preventDefault(); onPrev() }
      else if (e.key === 'ArrowRight') { e.preventDefault(); onNext() }
      else if (e.key === 'Home')       { e.preventDefault(); onFirst() }
      else if (e.key === 'End')        { e.preventDefault(); onLast() }
      else if (e.key === ' ')          { e.preventDefault(); onPlayPause() }
      else if (e.key === 'r' || e.key === 'R') onReview()
      else if (e.key === 's' || e.key === 'S') onSplit()
      else if (e.key === 'm' || e.key === 'M') onMerge()
      else if (e.key === 'w' || e.key === 'W') onWF()
      else if (e.key === 'i' || e.key === 'I') onSetIn()
      else if (e.key === 'o' || e.key === 'O') onSetOut()
      else if (e.key === 'Delete')             onDelete()
      else if (e.key === 'F1') { e.preventDefault(); onHelp() }
    }

    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, deps) // eslint-disable-line react-hooks/exhaustive-deps
}