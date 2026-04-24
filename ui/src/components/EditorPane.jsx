/**
 * EditorPane — orchestrator for the review/edit panel.
 *
 * Composes: VideoPlayer, ShotEditForm, ShotList, MergeModal,
 *           WhiteFlashModal, HelpModal.
 * Uses:     useHistory, useKeyboardShortcuts.
 *
 * All business logic (split, merge, WF, delete, undo/redo) lives here so
 * that the sub-components remain pure presentational components.
 */
import { useRef, useState, useEffect, useCallback, startTransition } from 'react'
import { secsToTC } from '../utils/timecode'
import { useHistory } from '../hooks/useHistory'
import { useKeyboardShortcuts } from '../hooks/useKeyboardShortcuts'
import VideoPlayer from './VideoPlayer'
import ShotEditForm from './ShotEditForm'
import ShotList from './ShotList'
import MergeModal from './MergeModal'
import WhiteFlashModal from './WhiteFlashModal'
import HelpModal from './HelpModal'

export default function EditorPane({ results, jobId, shotlistEntries, onResultsChange, videoPath }) {
  const videoRef = useRef(null)
  const shotRefs = useRef({})

  // Timecode display
  const [tc, setTc] = useState('00:00:00:00')

  // Selected shot index
  const [selIdx, setSel] = useState(0)

  // Modal visibility
  const [showWF, setShowWF]   = useState(false)
  const [showHelp, setHelp]   = useState(false)
  const [mergeModal, setMergeModal] = useState(null) // { selected, choiceIdx }

  // White-flash frame count
  const [wfF, setWfF] = useState(2)

  // Toast notification
  const [toast, setToast] = useState(null)

  // Bulk selection
  const [selIds, setSelIds] = useState(new Set())

  // Undo/redo history
  const { shots, hist, canUndo, canRedo, init, update, undo, redo } = useHistory(results || [])

  // Re-initialise history and reset selection whenever a new job arrives (issue #13).
  // Using jobId (not results) as the dependency avoids an infinite re-render loop
  // caused by object-identity changes in the results array on each render.
  // startTransition defers the setSel/setSelIds updates so they are not
  // synchronous within the effect body (satisfies react-hooks/set-state-in-effect).
  const didInit = useRef(false)
  useEffect(() => {
    if (results?.length) {
      init(results)
      startTransition(() => {
        setSel(0)
        setSelIds(new Set())
      })
    }
  }, [jobId]) // eslint-disable-line react-hooks/exhaustive-deps

  // Propagate changes to parent
  useEffect(() => {
    if (!didInit.current) { didInit.current = true; return }
    if (shots) onResultsChange(shots)
  }, [shots]) // eslint-disable-line

  const sel = shots[selIdx]

  // -------------------------------------------------------------------------
  // Helpers
  // -------------------------------------------------------------------------

  const toast_ = useCallback((m, ms = 1800) => {
    setToast(m); setTimeout(() => setToast(null), ms)
  }, [])

  const upd = useCallback((s) => update(s), [update])

  // Update video currentTime when selection changes
  useEffect(() => {
    const s = shots[selIdx]
    if (s && videoRef.current) videoRef.current.currentTime = s.seconds || 0
  }, [selIdx]) // eslint-disable-line

  // Scroll selected shot row into view
  useEffect(() => {
    const s = shots[selIdx]; if (!s) return
    const el = shotRefs.current[s.shot_index]
    if (el && typeof el.scrollIntoView === 'function') el.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [selIdx, shots])

  // Track playhead timecode
  useEffect(() => {
    const v = videoRef.current; if (!v) return
    const fn = () => setTc(secsToTC(v.currentTime))
    v.addEventListener('timeupdate', fn)
    return () => v.removeEventListener('timeupdate', fn)
  }, [videoPath])

  const go     = i => { if (i >= 0 && i < shots.length) setSel(i) }
  const setF   = (f, v) => upd(shots.map((s, i) => i === selIdx ? { ...s, [f]: v } : s))
  const togRev = i => upd(shots.map((s, j) => j === i ? { ...s, human_reviewed: !s.human_reviewed } : s))
  const togSel = id => setSelIds(p => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n })
  const clrSel = () => setSelIds(new Set())

  // -------------------------------------------------------------------------
  // Bulk operations
  // -------------------------------------------------------------------------

  const bulkRev = v => {
    const n = selIds.size
    upd(shots.map(s => selIds.has(s.shot_index) ? { ...s, human_reviewed: v } : s))
    clrSel(); toast_(`${n} shots ${v ? 'reviewed' : 'unreviewed'}`)
  }

  const bulkMerge = () => {
    if (selIds.size < 2) return
    const selected = shots.filter(s => selIds.has(s.shot_index))
    selected.sort((a, b) => a.shot_index - b.shot_index)
    for (let i = 1; i < selected.length; i++) {
      if (selected[i].shot_index !== selected[i - 1].shot_index + 1) {
        toast_('Selected shots must be adjacent to merge', 2500); return
      }
    }
    setMergeModal({ selected, choiceIdx: 0 })
  }

  // -------------------------------------------------------------------------
  // Shot operations
  // -------------------------------------------------------------------------

  const confirmMerge = () => {
    if (!mergeModal) return
    const { selected, choiceIdx } = mergeModal
    const first = selected[0]
    const last  = selected[selected.length - 1]
    const chosen = selected[choiceIdx]
    const merged = {
      ...first,
      timecode_out: last.timecode_out || '',
      matched_entry: chosen.matched_entry,
      matched_description: chosen.matched_description,
      confidence: chosen.confidence,
      notes: chosen.notes,
    }
    const startIdx = shots.indexOf(first)
    const endIdx   = shots.indexOf(last)
    const next = [
      ...shots.slice(0, startIdx),
      merged,
      ...shots.slice(endIdx + 1),
    ].map((s, i) => ({ ...s, shot_index: i }))
    upd(next)
    setSel(startIdx); clrSel(); setMergeModal(null)
    toast_(`${selected.length} shots merged`)
  }

  const mergeWithNext = () => {
    if (selIdx >= shots.length - 1) return
    const a = shots[selIdx]
    const b = shots[selIdx + 1]
    const merged = {
      ...a,
      timecode_out: b.timecode_out || '',
      matched_description: a.matched_description
        ? b.matched_description ? `${a.matched_description} / ${b.matched_description}` : a.matched_description
        : b.matched_description,
      notes: [a.notes, b.notes].filter(Boolean).join(' | '),
    }
    const next = [
      ...shots.slice(0, selIdx),
      merged,
      ...shots.slice(selIdx + 2),
    ].map((s, i) => ({ ...s, shot_index: i }))
    upd(next)
    toast_(`Shots ${selIdx + 1} and ${selIdx + 2} merged`)
  }

  const splitAtPlayhead = () => {
    if (!videoRef.current) return
    const secs = videoRef.current.currentTime
    const splitTC = secsToTC(secs)
    const s = shots[selIdx]
    const inSecs = s.seconds || 0
    if (secs <= inSecs + 0.04) { toast_('Playhead must be after shot IN point to split'); return }
    const a = { ...s, timecode_out: splitTC }
    const b = {
      ...s, shot_index: -1,
      timecode: splitTC, timecode_in: splitTC,
      seconds: secs, matched_description: '', notes: '',
      human_reviewed: false, is_white_flash: false,
    }
    const next = [
      ...shots.slice(0, selIdx), a, b, ...shots.slice(selIdx + 1),
    ].map((s, i) => ({ ...s, shot_index: i }))
    upd(next); setSel(selIdx + 1)
    toast_(`Shot split at ${splitTC}`)
  }

  const insertWF = () => {
    const secs = videoRef.current?.currentTime || 0
    const tcIn = secsToTC(secs), tcOut = secsToTC(secs + wfF / 25)
    const wf = {
      shot_index: -1, timecode: tcIn, timecode_in: tcIn, timecode_out: tcOut, seconds: secs,
      matched_entry: null, matched_description: `White flash (${wfF}f)`,
      confidence: 'high', notes: 'White flash', type: 'White Flash',
      human_reviewed: true, is_white_flash: true,
    }
    const at = selIdx + 1
    const next = [...shots.slice(0, at), wf, ...shots.slice(at)].map((s, i) => ({ ...s, shot_index: i }))
    upd(next); setSel(at); setShowWF(false)
    toast_(`WF (${wfF}f) at ${tcIn}`)
  }

  const delShot = i => {
    if (shots.length <= 1) return
    const next = shots.filter((_, j) => j !== i).map((s, j) => ({ ...s, shot_index: j }))
    upd(next); setSel(Math.min(i, next.length - 1)); toast_('Shot deleted')
  }

  const reassign = val => {
    const n = val ? parseInt(val, 10) : null
    const entry = shotlistEntries.find(x => x.entry_number === n)
    upd(shots.map((s, i) => i === selIdx ? { ...s, matched_entry: n, matched_description: entry?.description || '' } : s))
  }

  // -------------------------------------------------------------------------
  // Keyboard shortcuts
  // -------------------------------------------------------------------------

  useKeyboardShortcuts({
    onPrev:      () => go(selIdx - 1),
    onNext:      () => go(selIdx + 1),
    onFirst:     () => go(0),
    onLast:      () => go(shots.length - 1),
    onPlayPause: () => { videoRef.current?.paused ? videoRef.current.play() : videoRef.current?.pause() },
    onReview:    () => togRev(selIdx),
    onSplit:     splitAtPlayhead,
    onMerge:     mergeWithNext,
    onWF:        () => setShowWF(true),
    onSetIn:     () => { const t = secsToTC(videoRef.current?.currentTime || 0); setF('timecode_in', t); toast_(`IN: ${t}`) },
    onSetOut:    () => { const t = secsToTC(videoRef.current?.currentTime || 0); setF('timecode_out', t); toast_(`OUT: ${t}`) },
    onDelete:    () => delShot(selIdx),
    onHelp:      () => setHelp(true),
    onUndo:      () => { undo(); toast_('Undo') },
    onRedo:      () => { redo(); toast_('Redo') },
    canUndo,
    canRedo,
  }, [selIdx, shots, hist])

  const reviewed = shots.filter(s => s.human_reviewed).length

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <div className="flex-1 min-h-0 flex bg-white rounded-lg border border-gray-200 overflow-hidden relative">

      {/* Toast */}
      {toast && (
        <div className="absolute top-4 left-1/2 -translate-x-1/2 z-50 bg-gray-900 text-white text-xs px-4 py-2 rounded-full shadow-lg pointer-events-none">
          {toast}
        </div>
      )}

      {/* LEFT PANEL */}
      <div className="w-96 shrink-0 border-r border-gray-200 flex flex-col overflow-y-auto">
        <VideoPlayer
          videoPath={videoPath}
          videoRef={videoRef}
          tc={tc}
          selIdx={selIdx}
          totalShots={shots.length}
          onPrev={() => go(selIdx - 1)}
          onNext={() => go(selIdx + 1)}
        />
        <ShotEditForm
          sel={sel}
          selIdx={selIdx}
          totalShots={shots.length}
          shotlistEntries={shotlistEntries}
          onToggleReview={() => togRev(selIdx)}
          onSplit={splitAtPlayhead}
          onMerge={mergeWithNext}
          onWF={() => setShowWF(true)}
          onDelete={() => delShot(selIdx)}
          onFieldChange={setF}
          onReassign={reassign}
        />
      </div>

      {/* RIGHT PANEL */}
      <ShotList
        shots={shots} selIdx={selIdx} shotRefs={shotRefs}
        selIds={selIds} reviewed={reviewed}
        onSelect={setSel} onToggleSel={togSel} onSetSelIds={setSelIds}
        onBulkRev={bulkRev} onBulkMerge={bulkMerge} onClearSel={clrSel}
        onHelp={() => setHelp(true)}
      />

      {/* Modals */}
      <MergeModal
        mergeModal={mergeModal}
        onChoiceChange={i => setMergeModal(m => ({ ...m, choiceIdx: i }))}
        onConfirm={confirmMerge}
        onCancel={() => setMergeModal(null)}
      />
      <WhiteFlashModal
        show={showWF}
        tc={tc}
        wfF={wfF}
        onFrameChange={setWfF}
        onConfirm={insertWF}
        onCancel={() => setShowWF(false)}
      />
      <HelpModal
        show={showHelp}
        onClose={() => setHelp(false)}
      />
    </div>
  )
}