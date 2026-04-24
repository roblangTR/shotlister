/**
 * useHistory — undo/redo history management hook.
 *
 * Wraps useReducer with historyReducer and exposes a clean API:
 *   shots      — the current (present) shot list
 *   canUndo    — whether there is history to undo
 *   canRedo    — whether there is future to redo
 *   init(s)    — initialise history with a fresh shot list
 *   update(s)  — push a new state (supports undo)
 *   undo()     — step back
 *   redo()     — step forward
 *   dispatch   — raw reducer dispatch (for UNDO/REDO from keyboard handler)
 *   hist       — full history state (past/present/future)
 */
import { useReducer } from 'react'
import { historyReducer } from '../utils/historyReducer'

/**
 * @param {any[]} initialShots - Starting shot list (used as initial present).
 * @returns {{ shots: any[], hist: object, canUndo: boolean, canRedo: boolean,
 *             init: Function, update: Function, undo: Function, redo: Function,
 *             dispatch: Function }}
 */
export function useHistory(initialShots) {
  const [hist, dispatch] = useReducer(historyReducer, {
    past: [],
    present: initialShots || [],
    future: [],
  })

  const shots   = hist.present || []
  const canUndo = hist.past.length > 0
  const canRedo = hist.future.length > 0

  const init   = shots => dispatch({ type: 'INIT',   shots })
  const update = shots => dispatch({ type: 'UPDATE', shots })
  const undo   = ()    => dispatch({ type: 'UNDO' })
  const redo   = ()    => dispatch({ type: 'REDO' })

  return { shots, hist, canUndo, canRedo, init, update, undo, redo, dispatch }
}