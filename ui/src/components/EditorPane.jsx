/**
 * EditorPane — left panel (video + detail form) + orchestration.
 * Imports ShotList for the right panel.
 */
import { useRef, useState, useEffect, useCallback, useReducer } from 'react'
import ShotList from './ShotList'

function secsToTC(s, fps = 25) {
  const f = Math.round(s * fps)
  const hh = Math.floor(f / (3600 * fps))
  const mm = Math.floor((f % (3600 * fps)) / (60 * fps))
  const ss = Math.floor((f % (60 * fps)) / fps)
  const ff = f % fps
  return [hh, mm, ss, ff].map(n => String(n).padStart(2, '0')).join(':')
}

const MAX_HIST = 50
function reduce(state, action) {
  switch (action.type) {
    case 'INIT':   return { past: [], present: action.shots, future: [] }
    case 'UPDATE': return { past: [...state.past, state.present].slice(-MAX_HIST), present: action.shots, future: [] }
    case 'UNDO':   return state.past.length ? { past: state.past.slice(0,-1), present: state.past[state.past.length-1], future: [state.present,...state.future] } : state
    case 'REDO':   return state.future.length ? { past: [...state.past,state.present], present: state.future[0], future: state.future.slice(1) } : state
    default:       return state
  }
}

export default function EditorPane({ results, shotlistEntries, onResultsChange, videoPath }) {
  const videoRef = useRef(null)
  const shotRefs = useRef({})
  const [tc, setTc]         = useState('00:00:00:00')
  const [selIdx, setSel]    = useState(0)
  const [showWF, setShowWF]         = useState(false)
  const [wfF, setWfF]               = useState(2)
  const [showHelp, setHelp]         = useState(false)
  const [mergeModal, setMergeModal] = useState(null) // { selected: Shot[], choiceIdx: number }
  const [toast, setToast]   = useState(null)
  const [selIds, setSelIds] = useState(new Set())
  const [hist, dispatch]    = useReducer(reduce, { past:[], present: results||[], future:[] })

  useEffect(() => { if (results?.length) dispatch({ type:'INIT', shots:results }) }, []) // eslint-disable-line
  useEffect(() => { if (hist.present) onResultsChange(hist.present) }, [hist.present]) // eslint-disable-line

  const shots = hist.present || []
  const sel   = shots[selIdx]

  const toast_ = useCallback((m, ms=1800) => { setToast(m); setTimeout(()=>setToast(null),ms) }, [])
  const upd    = useCallback((s,d) => dispatch({ type:'UPDATE', shots:s, description:d }), [])

  useEffect(() => {
    const v = videoRef.current; if(!v) return
    const fn = () => setTc(secsToTC(v.currentTime))
    v.addEventListener('timeupdate', fn)
    return () => v.removeEventListener('timeupdate', fn)
  }, [videoPath])

  useEffect(() => {
    const s = shots[selIdx]
    if (s && videoRef.current) videoRef.current.currentTime = s.seconds || 0
  }, [selIdx]) // eslint-disable-line

  useEffect(() => {
    const s = shots[selIdx]; if(!s) return
    const el = shotRefs.current[s.shot_index]
    if (el && typeof el.scrollIntoView === 'function') el.scrollIntoView({ block:'nearest', behavior:'smooth' })
  }, [selIdx, shots])

  const go      = i => { if(i>=0 && i<shots.length) setSel(i) }
  const setF    = (f,v) => upd(shots.map((s,i)=>i===selIdx?{...s,[f]:v}:s), `Edit ${f}`)
  const togRev  = i => upd(shots.map((s,j)=>j===i?{...s,human_reviewed:!s.human_reviewed}:s), 'Review')
  const togSel  = id => setSelIds(p => { const n=new Set(p); n.has(id)?n.delete(id):n.add(id); return n })
  const clrSel  = () => setSelIds(new Set())

  const bulkRev = v => {
    const n = selIds.size
    upd(shots.map(s => selIds.has(s.shot_index)?{...s,human_reviewed:v}:s), v?'Bulk review':'Bulk unreview')
    clrSel(); toast_(`${n} shots ${v?'reviewed':'unreviewed'}`)
  }

  const bulkMerge = () => {
    if (selIds.size < 2) return
    const selected = shots.filter(s => selIds.has(s.shot_index))
    selected.sort((a, b) => a.shot_index - b.shot_index)
    for (let i = 1; i < selected.length; i++) {
      if (selected[i].shot_index !== selected[i-1].shot_index + 1) {
        toast_('Selected shots must be adjacent to merge', 2500); return
      }
    }
    // Open modal to let user choose which description to keep
    setMergeModal({ selected, choiceIdx: 0 })
  }

  const confirmMerge = () => {
    if (!mergeModal) return
    const { selected, choiceIdx } = mergeModal
    const first = selected[0]
    const last  = selected[selected.length - 1]
    const chosenShot = selected[choiceIdx]
    const merged = {
      ...first,
      timecode_out: last.timecode_out || '',
      matched_entry: chosenShot.matched_entry,
      matched_description: chosenShot.matched_description,
      confidence: chosenShot.confidence,
      notes: chosenShot.notes,
    }
    const startIdx = shots.indexOf(first)
    const endIdx   = shots.indexOf(last)
    const next = [
      ...shots.slice(0, startIdx),
      merged,
      ...shots.slice(endIdx + 1),
    ].map((s, i) => ({ ...s, shot_index: i }))
    upd(next, `Merge ${selected.length} shots`)
    setSel(startIdx)
    clrSel()
    setMergeModal(null)
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
        ? b.matched_description
          ? `${a.matched_description} / ${b.matched_description}`
          : a.matched_description
        : b.matched_description,
      notes: [a.notes, b.notes].filter(Boolean).join(' | '),
    }
    const next = [
      ...shots.slice(0, selIdx),
      merged,
      ...shots.slice(selIdx + 2),
    ].map((s, i) => ({ ...s, shot_index: i }))
    upd(next, `Merge shots ${selIdx + 1} + ${selIdx + 2}`)
    toast_(`Shots ${selIdx + 1} and ${selIdx + 2} merged`)
  }

  const splitAtPlayhead = () => {
    if (!videoRef.current) return
    const secs = videoRef.current.currentTime
    const splitTC = secsToTC(secs)
    const s = shots[selIdx]
    // Don't split if playhead is outside the shot's range (or at the start)
    const inSecs = s.seconds || 0
    if (secs <= inSecs + 0.04) { toast_('Playhead must be after shot IN point to split'); return }
    const a = { ...s, timecode_out: splitTC }
    const b = {
      ...s,
      shot_index: -1,
      timecode: splitTC, timecode_in: splitTC,
      seconds: secs,
      matched_description: '',
      notes: '',
      human_reviewed: false,
      is_white_flash: false,
    }
    const next = [
      ...shots.slice(0, selIdx),
      a, b,
      ...shots.slice(selIdx + 1),
    ].map((s, i) => ({ ...s, shot_index: i }))
    upd(next, `Split shot ${selIdx + 1} at ${splitTC}`)
    setSelIdx(selIdx + 1)
    toast_(`Shot split at ${splitTC}`)
  }

  const insertWF = () => {
    const secs = videoRef.current?.currentTime || 0
    const tcIn = secsToTC(secs), tcOut = secsToTC(secs + wfF/25)
    const wf = { shot_index:-1, timecode:tcIn, timecode_in:tcIn, timecode_out:tcOut, seconds:secs,
      matched_entry:null, matched_description:`White flash (${wfF}f)`,
      confidence:'high', notes:'White flash', type:'White Flash', human_reviewed:true, is_white_flash:true }
    const at = selIdx+1
    const next = [...shots.slice(0,at), wf, ...shots.slice(at)].map((s,i)=>({...s,shot_index:i}))
    upd(next, `WF ${wfF}f at ${tcIn}`)
    setSel(at); setShowWF(false); toast_(`WF (${wfF}f) at ${tcIn}`)
  }

  const delShot = i => {
    if(shots.length<=1) return
    const next = shots.filter((_,j)=>j!==i).map((s,j)=>({...s,shot_index:j}))
    upd(next, `Delete shot ${i+1}`); setSel(Math.min(i,next.length-1)); toast_('Shot deleted')
  }

  useEffect(() => {
    const onKey = e => {
      const inF = ['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName)
      if ((e.ctrlKey||e.metaKey) && !e.shiftKey && e.key==='z') {
        e.preventDefault(); if(hist.past.length){dispatch({type:'UNDO'}); toast_('Undo')}; return
      }
      if ((e.ctrlKey||e.metaKey) && (e.key==='y'||(e.shiftKey&&e.key==='Z'))) {
        e.preventDefault(); if(hist.future.length){dispatch({type:'REDO'}); toast_('Redo')}; return
      }
      if (inF) return
      if      (e.key==='ArrowLeft')  { e.preventDefault(); go(selIdx-1) }
      else if (e.key==='ArrowRight') { e.preventDefault(); go(selIdx+1) }
      else if (e.key==='Home')       { e.preventDefault(); go(0) }
      else if (e.key==='End')        { e.preventDefault(); go(shots.length-1) }
      else if (e.key===' ')         { e.preventDefault(); videoRef.current?.paused?videoRef.current.play():videoRef.current?.pause() }
      else if (e.key==='r'||e.key==='R') togRev(selIdx)
      else if (e.key==='s'||e.key==='S') splitAtPlayhead()
      else if (e.key==='m'||e.key==='M') mergeWithNext()
      else if (e.key==='w'||e.key==='W') setShowWF(true)
      else if (e.key==='i'||e.key==='I') { const t=secsToTC(videoRef.current?.currentTime||0); setF('timecode_in',t); toast_(`IN: ${t}`) }
      else if (e.key==='o'||e.key==='O') { const t=secsToTC(videoRef.current?.currentTime||0); setF('timecode_out',t); toast_(`OUT: ${t}`) }
      else if (e.key==='Delete')    delShot(selIdx)
      else if (e.key==='F1')        { e.preventDefault(); setHelp(true) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [selIdx, shots, hist]) // eslint-disable-line

  const reviewed = shots.filter(s=>s.human_reviewed).length

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

        {/* Video */}
        <div className="p-3 border-b border-gray-100">
          <div className="relative bg-black rounded overflow-hidden">
            {videoPath
              ? <video ref={videoRef} src={`/video?path=${encodeURIComponent(videoPath)}`} controls className="w-full" />
              : <div className="h-40 flex items-center justify-center text-xs text-gray-400">No video</div>
            }
            <div className="absolute bottom-8 left-2 bg-black/75 text-white font-mono text-xs px-2 py-0.5 rounded pointer-events-none select-none">
              {tc}
            </div>
          </div>
          <div className="flex items-center gap-2 mt-2">
            <button onClick={()=>go(selIdx-1)} disabled={selIdx===0}
              className="flex-1 text-xs border border-gray-300 rounded py-1 hover:bg-gray-50 disabled:opacity-40">← Prev</button>
            <span className="text-xs text-gray-400 shrink-0">{selIdx+1} / {shots.length}</span>
            <button onClick={()=>go(selIdx+1)} disabled={selIdx>=shots.length-1}
              className="flex-1 text-xs border border-gray-300 rounded py-1 hover:bg-gray-50 disabled:opacity-40">Next →</button>
          </div>
        </div>

        {/* Detail form */}
        {sel && (
          <div className="p-3 flex flex-col gap-3 overflow-y-auto flex-1">

            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                Shot {selIdx+1}
                {sel.is_white_flash && <span className="ml-1 bg-gray-800 text-white px-1 rounded normal-case font-normal">WF</span>}
              </span>
              <div className="flex gap-1 flex-wrap">
                <button onClick={()=>togRev(selIdx)} title="R"
                  className={`text-xs px-2 py-0.5 rounded border font-medium ${sel.human_reviewed?'bg-green-100 text-green-800 border-green-300':'bg-gray-100 text-gray-600 border-gray-300 hover:bg-gray-200'}`}>
                  {sel.human_reviewed ? '✓' : 'Rev'}
                </button>
                <button onClick={splitAtPlayhead} title="S — split at playhead"
                  className="text-xs px-2 py-0.5 rounded border border-blue-300 text-blue-700 hover:bg-blue-50 font-medium">Split</button>
                <button onClick={mergeWithNext} disabled={selIdx >= shots.length - 1} title="M — merge with next"
                  className="text-xs px-2 py-0.5 rounded border border-purple-300 text-purple-700 hover:bg-purple-50 font-medium disabled:opacity-40">Merge</button>
                <button onClick={()=>setShowWF(true)} title="W"
                  className="text-xs px-2 py-0.5 rounded border-2 border-gray-900 font-bold hover:bg-gray-100">WF</button>
                <button onClick={()=>delShot(selIdx)} title="Del"
                  className="text-xs px-2 py-0.5 rounded border border-red-300 text-red-600 hover:bg-red-50">✕</button>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <label className="flex flex-col gap-0.5">
                <span className="text-xs text-gray-500">IN <kbd className="border border-gray-300 rounded px-0.5 text-gray-400 text-xs">I</kbd></span>
                <input type="text" value={sel.timecode_in||sel.timecode||''} onChange={e=>setF('timecode_in',e.target.value)}
                  className="border border-gray-300 rounded px-2 py-1 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-blue-400" placeholder="00:00:00:00" />
              </label>
              <label className="flex flex-col gap-0.5">
                <span className="text-xs text-gray-500">OUT <kbd className="border border-gray-300 rounded px-0.5 text-gray-400 text-xs">O</kbd></span>
                <input type="text" value={sel.timecode_out||''} onChange={e=>setF('timecode_out',e.target.value)}
                  className="border border-gray-300 rounded px-2 py-1 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-blue-400" placeholder="00:00:00:00" />
              </label>
            </div>

            <label className="flex flex-col gap-0.5">
              <span className="text-xs text-gray-500">Matched entry</span>
              <select value={sel.matched_entry??''} className="border border-gray-300 rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-400"
                onChange={e => {
                  const n = e.target.value ? parseInt(e.target.value,10) : null
                  const entry = shotlistEntries.find(x=>x.entry_number===n)
                  upd(shots.map((s,i)=>i===selIdx?{...s,matched_entry:n,matched_description:entry?.description||''}:s),'Reassign')
                }}>
                <option value="">— none —</option>
                {shotlistEntries.map(e=>(
                  <option key={e.entry_number} value={e.entry_number}>
                    {e.entry_number}. {e.description.slice(0,55)}{e.description.length>55?'…':''}
                  </option>
                ))}
              </select>
            </label>

            <label className="flex flex-col gap-0.5">
              <span className="text-xs text-gray-500">Description</span>
              <textarea value={sel.matched_description||''} rows={3} onChange={e=>setF('matched_description',e.target.value)}
                className="border border-gray-300 rounded px-2 py-1 text-xs font-mono resize-y focus:outline-none focus:ring-1 focus:ring-blue-400" />
            </label>

            <label className="flex flex-col gap-0.5">
              <span className="text-xs text-gray-500">Confidence</span>
              <select value={sel.confidence||'low'} onChange={e=>setF('confidence',e.target.value)}
                className="border border-gray-300 rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-400">
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
              </select>
            </label>

            <label className="flex flex-col gap-0.5">
              <span className="text-xs text-gray-500">Notes</span>
              <textarea value={sel.notes||''} rows={2} onChange={e=>setF('notes',e.target.value)}
                className="border border-gray-300 rounded px-2 py-1 text-xs resize-y focus:outline-none focus:ring-1 focus:ring-blue-400" />
            </label>
          </div>
        )}
      </div>

      {/* RIGHT PANEL */}
      <ShotList
        shots={shots} selIdx={selIdx} shotRefs={shotRefs}
        selIds={selIds} reviewed={reviewed}
        onSelect={setSel} onToggleSel={togSel}
        onBulkRev={bulkRev} onBulkMerge={bulkMerge} onClearSel={clrSel}
        onHelp={()=>setHelp(true)}
      />

      {/* Merge Description Modal */}
      {mergeModal && (
        <div className="absolute inset-0 bg-black/40 flex items-center justify-center z-40" onClick={()=>setMergeModal(null)}>
          <div className="bg-white rounded-lg shadow-xl p-6 w-[520px] max-h-[80vh] flex flex-col" onClick={e=>e.stopPropagation()}>
            <h2 className="text-sm font-semibold mb-1">Merge {mergeModal.selected.length} shots</h2>
            <p className="text-xs text-gray-500 mb-4">
              Choose which description the merged shot should use.
              Timecode will span {mergeModal.selected[0].timecode_in || mergeModal.selected[0].timecode} → {mergeModal.selected[mergeModal.selected.length-1].timecode_out}.
            </p>
            <div className="overflow-y-auto flex flex-col gap-2 flex-1 mb-4">
              {mergeModal.selected.map((shot, i) => (
                <label key={shot.shot_index}
                  className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                    mergeModal.choiceIdx === i
                      ? 'border-blue-500 bg-blue-50'
                      : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                  }`}>
                  <input type="radio" name="merge-choice" checked={mergeModal.choiceIdx === i}
                    onChange={() => setMergeModal(m => ({ ...m, choiceIdx: i }))}
                    className="mt-0.5 shrink-0 accent-blue-600" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-mono text-xs text-gray-500">{shot.timecode_in || shot.timecode}</span>
                      {shot.matched_entry != null && (
                        <span className="text-xs text-gray-400">→ entry {shot.matched_entry}</span>
                      )}
                      <span className={`text-xs px-1.5 py-0.5 rounded border font-medium ${
                        shot.confidence === 'high' ? 'bg-green-100 text-green-800 border-green-200' :
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
              <button onClick={()=>setMergeModal(null)} className="text-sm px-4 py-1.5 border border-gray-300 rounded hover:bg-gray-50">Cancel</button>
              <button onClick={confirmMerge} className="text-sm px-4 py-1.5 bg-purple-600 text-white rounded hover:bg-purple-700 font-medium">
                Merge with this description
              </button>
            </div>
          </div>
        </div>
      )}

      {/* White Flash Modal */}
      {showWF && (
        <div className="absolute inset-0 bg-black/40 flex items-center justify-center z-40" onClick={()=>setShowWF(false)}>
          <div className="bg-white rounded-lg shadow-xl p-6 w-80" onClick={e=>e.stopPropagation()}>
            <h2 className="text-sm font-semibold mb-1">Add White Flash</h2>
            <p className="text-xs text-gray-500 mb-4">Inserts a white flash at the current playhead position ({tc}).</p>
            <label className="flex items-center gap-3 mb-4">
              <span className="text-xs text-gray-600">Duration (frames)</span>
              <input type="number" min={1} max={10} value={wfF} onChange={e=>setWfF(Number(e.target.value))}
                className="w-16 border border-gray-300 rounded px-2 py-1 text-sm text-center focus:outline-none focus:ring-1 focus:ring-blue-400" />
            </label>
            <p className="text-xs text-gray-400 mb-4">White flashes are used between soundbites in video editing.</p>
            <div className="flex gap-2 justify-end">
              <button onClick={()=>setShowWF(false)} className="text-sm px-4 py-1.5 border border-gray-300 rounded hover:bg-gray-50">Cancel</button>
              <button onClick={insertWF} className="text-sm px-4 py-1.5 bg-gray-900 text-white rounded hover:bg-gray-700 font-medium">Add White Flash</button>
            </div>
          </div>
        </div>
      )}

      {/* Help Modal */}
      {showHelp && (
        <div className="absolute inset-0 bg-black/40 flex items-center justify-center z-40" onClick={()=>setHelp(false)}>
          <div className="bg-white rounded-lg shadow-xl p-6 w-[480px] max-h-[80vh] overflow-y-auto" onClick={e=>e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold">Keyboard Shortcuts</h2>
              <button onClick={()=>setHelp(false)} className="text-gray-400 hover:text-gray-600 text-lg leading-none">×</button>
            </div>
            <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs">
              {[
                ['← / →',        'Previous / Next shot'],
                ['Home / End',    'First / Last shot'],
                ['Space',         'Play / Pause'],
                ['I',             'Set IN point from playhead'],
                ['O',             'Set OUT point from playhead'],
                ['R',             'Toggle reviewed'],
                ['S',             'Split shot at playhead'],
                ['M',             'Merge shot with next'],
                ['W',             'White Flash modal'],
                ['Delete',        'Delete selected shot'],
                ['Ctrl+Z',        'Undo'],
                ['Ctrl+Y',        'Redo'],
                ['F1',            'This help'],
              ].map(([k, v]) => (
                <div key={k} className="flex items-center gap-2 py-1 border-b border-gray-100">
                  <kbd className="bg-gray-100 border border-gray-300 rounded px-1.5 py-0.5 font-mono text-gray-700 shrink-0">{k}</kbd>
                  <span className="text-gray-600">{v}</span>
                </div>
              ))}
            </div>
            <p className="text-xs text-gray-400 mt-4">Shortcuts work when not typing in a field.</p>
          </div>
        </div>
      )}
    </div>
  )
}
