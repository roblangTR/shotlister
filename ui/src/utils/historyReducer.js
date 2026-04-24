/**
 * historyReducer.js — undo/redo history reducer for the shot list editor.
 *
 * Extracted from EditorPane.jsx so that both the component and its tests
 * import the same production code rather than maintaining separate copies.
 */

/** Maximum number of past states to keep in the undo stack. */
export const MAX_HIST = 50

/**
 * Reducer for undo/redo history state.
 *
 * State shape: { past: Shot[][], present: Shot[], future: Shot[][] }
 *
 * Actions:
 *   INIT   — replace present with action.shots, clear past/future
 *   UPDATE — push present onto past (capped at MAX_HIST), replace with action.shots
 *   UNDO   — pop from past, push present onto future
 *   REDO   — shift from future, push present onto past
 *
 * @param {{ past: any[], present: any[], future: any[] }} state
 * @param {{ type: string, shots?: any[] }} action
 * @returns {{ past: any[], present: any[], future: any[] }}
 */
export function historyReducer(state, action) {
  switch (action.type) {
    case 'INIT':
      return { past: [], present: action.shots, future: [] }
    case 'UPDATE':
      return {
        past: [...state.past, state.present].slice(-MAX_HIST),
        present: action.shots,
        future: [],
      }
    case 'UNDO':
      return state.past.length
        ? {
            past: state.past.slice(0, -1),
            present: state.past[state.past.length - 1],
            future: [state.present, ...state.future],
          }
        : state
    case 'REDO':
      return state.future.length
        ? {
            past: [...state.past, state.present],
            present: state.future[0],
            future: state.future.slice(1),
          }
        : state
    default:
      return state
  }
}