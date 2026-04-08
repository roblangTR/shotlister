/**
 * Tests for EditorPane and ShotList components.
 *
 * Unit tests: secsToTC timecode helper, historyReducer undo/redo logic.
 * Smoke tests: EditorPane and ShotList render without crashing.
 * Interaction tests: review toggle, white flash modal, shot navigation.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// ---------------------------------------------------------------------------
// Timecode helper — extracted for testability (mirrors EditorPane internals)
// ---------------------------------------------------------------------------

function secsToTC(s, fps = 25) {
  const f = Math.round(s * fps)
  const hh = Math.floor(f / (3600 * fps))
  const mm = Math.floor((f % (3600 * fps)) / (60 * fps))
  const ss = Math.floor((f % (60 * fps)) / fps)
  const ff = f % fps
  return [hh, mm, ss, ff].map(n => String(n).padStart(2, '0')).join(':')
}

// ---------------------------------------------------------------------------
// History reducer — extracted for testability
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Unit tests — secsToTC
// ---------------------------------------------------------------------------

describe('secsToTC', () => {
  it('converts 0 seconds to 00:00:00:00', () => {
    expect(secsToTC(0)).toBe('00:00:00:00')
  })

  it('converts 1 second to 00:00:01:00 at 25fps', () => {
    expect(secsToTC(1, 25)).toBe('00:00:01:00')
  })

  it('converts 60 seconds to 00:01:00:00', () => {
    expect(secsToTC(60, 25)).toBe('00:01:00:00')
  })

  it('converts 3600 seconds to 01:00:00:00', () => {
    expect(secsToTC(3600, 25)).toBe('01:00:00:00')
  })

  it('handles fractional seconds (0.5s at 25fps)', () => {
    // Math.round(0.5 * 25) = Math.round(12.5) = 13 (banker's rounding in JS rounds up)
    expect(secsToTC(0.5, 25)).toBe('00:00:00:13')
  })

  it('handles 5.48s correctly', () => {
    // 5.48 * 25 = 137 frames → 00:00:05:12
    expect(secsToTC(5.48, 25)).toBe('00:00:05:12')
  })

  it('output is always HH:MM:SS:FF format with zero-padding', () => {
    const tc = secsToTC(3661, 25)   // 1h 1m 1s
    expect(tc).toMatch(/^\d{2}:\d{2}:\d{2}:\d{2}$/)
  })
})

// ---------------------------------------------------------------------------
// Unit tests — historyReducer
// ---------------------------------------------------------------------------

describe('historyReducer', () => {
  const s1 = [{ shot_index: 0 }]
  const s2 = [{ shot_index: 0, confidence: 'high' }]
  const s3 = [{ shot_index: 0, confidence: 'low' }]

  it('INIT sets present and clears past/future', () => {
    const state = reduce({ past: ['x'], present: [], future: ['y'] }, { type: 'INIT', shots: s1 })
    expect(state.present).toEqual(s1)
    expect(state.past).toHaveLength(0)
    expect(state.future).toHaveLength(0)
  })

  it('UPDATE pushes present to past', () => {
    const state0 = reduce({}, { type: 'INIT', shots: s1 })
    const state1 = reduce(state0, { type: 'UPDATE', shots: s2 })
    expect(state1.present).toEqual(s2)
    expect(state1.past[0]).toEqual(s1)
    expect(state1.future).toHaveLength(0)
  })

  it('UNDO restores previous state', () => {
    let s = reduce({}, { type: 'INIT', shots: s1 })
    s = reduce(s, { type: 'UPDATE', shots: s2 })
    s = reduce(s, { type: 'UNDO' })
    expect(s.present).toEqual(s1)
    expect(s.future[0]).toEqual(s2)
  })

  it('REDO re-applies undone state', () => {
    let s = reduce({}, { type: 'INIT', shots: s1 })
    s = reduce(s, { type: 'UPDATE', shots: s2 })
    s = reduce(s, { type: 'UNDO' })
    s = reduce(s, { type: 'REDO' })
    expect(s.present).toEqual(s2)
    expect(s.future).toHaveLength(0)
  })

  it('UNDO at beginning of history returns unchanged state', () => {
    const s = reduce({}, { type: 'INIT', shots: s1 })
    const after = reduce(s, { type: 'UNDO' })
    expect(after).toBe(s)
  })

  it('REDO with empty future returns unchanged state', () => {
    const s = reduce({}, { type: 'INIT', shots: s1 })
    const after = reduce(s, { type: 'REDO' })
    expect(after).toBe(s)
  })

  it('UPDATE clears redo history', () => {
    let s = reduce({}, { type: 'INIT', shots: s1 })
    s = reduce(s, { type: 'UPDATE', shots: s2 })
    s = reduce(s, { type: 'UNDO' })
    // Future has s2 now — doing a new UPDATE should clear it
    s = reduce(s, { type: 'UPDATE', shots: s3 })
    expect(s.future).toHaveLength(0)
    expect(s.present).toEqual(s3)
  })

  it('respects MAX_HIST limit on past states', () => {
    let s = reduce({}, { type: 'INIT', shots: [{ shot_index: 0 }] })
    for (let i = 0; i < MAX_HIST + 5; i++) {
      s = reduce(s, { type: 'UPDATE', shots: [{ shot_index: i }] })
    }
    expect(s.past.length).toBeLessThanOrEqual(MAX_HIST)
  })
})

// ---------------------------------------------------------------------------
// Shared fixtures
// ---------------------------------------------------------------------------

const MOCK_SHOTS = [
  { shot_index: 0, timecode: '00:00:00:00', timecode_in: '00:00:00:00', timecode_out: '00:00:05:00',
    seconds: 0, matched_entry: 1, matched_description: 'VARIOUS OF ARTEMIS I',
    confidence: 'high', notes: 'Clear match.', human_reviewed: false, location_block: 'CAPE CANAVERAL' },
  { shot_index: 1, timecode: '00:00:05:00', timecode_in: '00:00:05:00', timecode_out: '00:00:10:00',
    seconds: 5, matched_entry: 2, matched_description: 'VARIOUS OF MOON SURFACE',
    confidence: 'medium', notes: '', human_reviewed: true, location_block: 'IN SPACE' },
  { shot_index: 2, timecode: '00:00:10:00', timecode_in: '00:00:10:00', timecode_out: '00:00:15:00',
    seconds: 10, matched_entry: 3, matched_description: '(SOUNDBITE) DR GLAZE',
    confidence: 'high', notes: 'Speaker visible.', human_reviewed: false, location_block: 'IN SPACE' },
]

const MOCK_ENTRIES = [
  { entry_number: 1, description: 'VARIOUS OF ARTEMIS I AS IT TAKES OFF' },
  { entry_number: 2, description: 'VARIOUS OF MOON SURFACE' },
  { entry_number: 3, description: '(SOUNDBITE) DR LORI GLAZE SAYING: The Apollo missions...' },
]

// ---------------------------------------------------------------------------
// ShotList smoke + render tests
// ---------------------------------------------------------------------------

import ShotList from '../ShotList'

describe('ShotList', () => {
  const defaultProps = {
    shots: MOCK_SHOTS,
    selIdx: 0,
    shotRefs: { current: {} },
    selIds: new Set(),
    reviewed: 1,
    onSelect: vi.fn(),
    onToggleSel: vi.fn(),
    onBulkRev: vi.fn(),
    onBulkMerge: vi.fn(),
    onClearSel: vi.fn(),
    onHelp: vi.fn(),
  }

  it('renders without crashing', () => {
    render(<ShotList {...defaultProps} />)
  })

  it('shows reviewed count in toolbar', () => {
    render(<ShotList {...defaultProps} reviewed={1} />)
    expect(screen.getByText('1')).toBeInTheDocument()
    expect(screen.getByText(/reviewed/i)).toBeInTheDocument()
  })

  it('renders dateline group headers', () => {
    render(<ShotList {...defaultProps} />)
    expect(screen.getByText('CAPE CANAVERAL')).toBeInTheDocument()
    expect(screen.getByText('IN SPACE')).toBeInTheDocument()
  })

  it('renders all shot timecodes', () => {
    render(<ShotList {...defaultProps} />)
    expect(screen.getByText('00:00:00:00')).toBeInTheDocument()
    expect(screen.getByText('00:00:05:00')).toBeInTheDocument()
    expect(screen.getByText('00:00:10:00')).toBeInTheDocument()
  })

  it('marks reviewed shot with checkmark', () => {
    render(<ShotList {...defaultProps} />)
    // Shot index 1 is human_reviewed: true
    const checks = screen.getAllByText('✓')
    expect(checks.length).toBeGreaterThanOrEqual(1)
  })

  it('highlights selected shot', () => {
    const { container } = render(<ShotList {...defaultProps} selIdx={1} />)
    const rows = container.querySelectorAll('.border-l-blue-500')
    expect(rows.length).toBe(1)
  })

  it('calls onSelect when a shot row is clicked', async () => {
    const onSelect = vi.fn()
    render(<ShotList {...defaultProps} onSelect={onSelect} />)
    // Click the second row (timecode 00:00:05:00)
    fireEvent.click(screen.getByText('00:00:05:00').closest('div[class*="cursor-pointer"]'))
    expect(onSelect).toHaveBeenCalledWith(1)
  })

  it('shows bulk actions when selIds is non-empty', () => {
    render(<ShotList {...defaultProps} selIds={new Set([0, 1])} />)
    expect(screen.getByText('2 selected')).toBeInTheDocument()
    // Button text is "✓ Review all" — use getAllByText and check at least one matches
    expect(screen.getAllByText(/Review all/i).length).toBeGreaterThanOrEqual(1)
  })

  it('calls onBulkRev(true) when Review all is clicked', async () => {
    const onBulkRev = vi.fn()
    render(<ShotList {...defaultProps} selIds={new Set([0])} onBulkRev={onBulkRev} />)
    // The review button contains "✓ Review all" — match the green button specifically
    const reviewBtn = screen.getAllByText(/Review all/i).find(el => el.closest('button')?.className.includes('bg-green-600'))
    fireEvent.click(reviewBtn.closest('button'))
    expect(onBulkRev).toHaveBeenCalledWith(true)
  })

  it('calls onBulkMerge when Merge selected is clicked', () => {
    const onBulkMerge = vi.fn()
    render(<ShotList {...defaultProps} selIds={new Set([0, 1])} onBulkMerge={onBulkMerge} />)
    fireEvent.click(screen.getByText('Merge selected'))
    expect(onBulkMerge).toHaveBeenCalled()
  })

  it('calls onHelp when ? button is clicked', () => {
    const onHelp = vi.fn()
    render(<ShotList {...defaultProps} onHelp={onHelp} />)
    fireEvent.click(screen.getByTitle(/keyboard shortcuts/i))
    expect(onHelp).toHaveBeenCalled()
  })

  it('shows WF badge for white flash shots', () => {
    const shotsWithWF = [
      ...MOCK_SHOTS,
      { shot_index: 3, timecode: '00:00:07:00', timecode_in: '00:00:07:00', timecode_out: '00:00:07:02',
        seconds: 7, matched_entry: null, matched_description: 'White flash (2f)',
        confidence: 'high', notes: 'White flash', human_reviewed: true,
        is_white_flash: true, location_block: '' }
    ]
    render(<ShotList {...defaultProps} shots={shotsWithWF} />)
    expect(screen.getByText('WF')).toBeInTheDocument()
  })

  it('renders shots with no location_block without crashing', () => {
    const noBlock = MOCK_SHOTS.map(s => ({ ...s, location_block: '' }))
    render(<ShotList {...defaultProps} shots={noBlock} />)
    expect(screen.getAllByText(/00:00/).length).toBeGreaterThan(0)
  })
})

// ---------------------------------------------------------------------------
// EditorPane smoke test
// ---------------------------------------------------------------------------

import EditorPane from '../EditorPane'

// Mock HTMLMediaElement — jsdom doesn't support video
Object.defineProperty(window.HTMLMediaElement.prototype, 'play',  { writable: true, value: vi.fn().mockResolvedValue(undefined) })
Object.defineProperty(window.HTMLMediaElement.prototype, 'pause', { writable: true, value: vi.fn() })

describe('EditorPane', () => {
  const defaultProps = {
    results: MOCK_SHOTS,
    shotlistEntries: MOCK_ENTRIES,
    onResultsChange: vi.fn(),
    videoPath: '/test/video.mp4',
  }

  beforeEach(() => { vi.clearAllMocks() })

  it('renders without crashing', () => {
    render(<EditorPane {...defaultProps} />)
  })

  it('shows shot counter', () => {
    render(<EditorPane {...defaultProps} />)
    expect(screen.getByText(/1 \/ 3/)).toBeInTheDocument()
  })

  it('shows IN/OUT timecode inputs', () => {
    render(<EditorPane {...defaultProps} />)
    // Both IN and OUT inputs share the same placeholder — expect exactly 2
    expect(screen.getAllByPlaceholderText('00:00:00:00')).toHaveLength(2)
  })

  it('shows the WF button', () => {
    render(<EditorPane {...defaultProps} />)
    expect(screen.getAllByText('WF')[0]).toBeInTheDocument()
  })

  it('clicking WF button opens the white flash modal', async () => {
    render(<EditorPane {...defaultProps} />)
    fireEvent.click(screen.getAllByTitle('W')[0])
    // Match the h2 heading specifically
    expect(screen.getByRole('heading', { name: 'Add White Flash' })).toBeInTheDocument()
  })

  it('white flash modal cancel closes it', async () => {
    render(<EditorPane {...defaultProps} />)
    fireEvent.click(screen.getAllByTitle('W')[0])
    fireEvent.click(screen.getByText('Cancel'))
    expect(screen.queryByRole('heading', { name: 'Add White Flash' })).not.toBeInTheDocument()
  })

  it('shows confidence select with current value', () => {
    render(<EditorPane {...defaultProps} />)
    const select = screen.getByDisplayValue('High')
    expect(select).toBeInTheDocument()
  })

  it('renders Next button and Prev button', () => {
    render(<EditorPane {...defaultProps} />)
    expect(screen.getByText(/Prev/)).toBeInTheDocument()
    expect(screen.getByText(/Next/)).toBeInTheDocument()
  })

  it('Prev button is disabled on first shot', () => {
    render(<EditorPane {...defaultProps} />)
    expect(screen.getByText(/Prev/).closest('button')).toBeDisabled()
  })

  it('clicking Next advances to shot 2', async () => {
    render(<EditorPane {...defaultProps} />)
    fireEvent.click(screen.getByText(/Next/).closest('button'))
    expect(screen.getByText(/2 \/ 3/)).toBeInTheDocument()
  })

  it('shows description textarea with matched_description', () => {
    render(<EditorPane {...defaultProps} />)
    expect(screen.getByDisplayValue('VARIOUS OF ARTEMIS I')).toBeInTheDocument()
  })

  it('help modal opens with F1 keyboard shortcut', () => {
    render(<EditorPane {...defaultProps} />)
    fireEvent.keyDown(window, { key: 'F1' })
    expect(screen.getByText('Keyboard Shortcuts')).toBeInTheDocument()
  })

  it('renders with empty results without crashing', () => {
    render(<EditorPane {...defaultProps} results={[]} />)
  })

  it('renders without videoPath without crashing', () => {
    render(<EditorPane {...defaultProps} videoPath={null} />)
    expect(screen.getByText(/No video/)).toBeInTheDocument()
  })

  it('shows Split and Merge buttons', () => {
    render(<EditorPane {...defaultProps} />)
    expect(screen.getByText('Split')).toBeInTheDocument()
    expect(screen.getByText('Merge')).toBeInTheDocument()
  })

  it('Merge button is disabled on last shot', () => {
    render(<EditorPane {...defaultProps} />)
    // Navigate to last shot
    fireEvent.click(screen.getByText(/Next/).closest('button'))
    fireEvent.click(screen.getByText(/Next/).closest('button'))
    expect(screen.getByText('Merge').closest('button')).toBeDisabled()
  })

  it('clicking Merge reduces shot count by 1', () => {
    render(<EditorPane {...defaultProps} />)
    // Start on shot 1, merge with shot 2
    fireEvent.click(screen.getByText('Merge'))
    expect(screen.getByText(/1 \/ 2/)).toBeInTheDocument()
  })
})