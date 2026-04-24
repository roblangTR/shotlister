/**
 * Tests for EditorPane and ShotList components.
 *
 * Unit tests: secsToTC timecode helper, historyReducer undo/redo logic.
 * Smoke tests: EditorPane and ShotList render without crashing.
 * Interaction tests: review toggle, white flash modal, shot navigation.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { secsToTC } from '../../utils/timecode'
import { historyReducer, MAX_HIST } from '../../utils/historyReducer'

// Local alias so existing test bodies that call reduce(...) keep working unchanged.
const reduce = historyReducer

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
    onSetSelIds: vi.fn(),
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

  it('Merge selected via checkboxes opens description-picker modal', () => {
    render(<EditorPane {...defaultProps} />)
    // Check shots 0 and 1 via checkboxes
    const checkboxes = screen.getAllByRole('checkbox')
    fireEvent.click(checkboxes[0])
    fireEvent.click(checkboxes[1])
    // Click "Merge selected" in the bulk toolbar
    fireEvent.click(screen.getByText('Merge selected'))
    // Modal heading should appear
    expect(screen.getByRole('heading', { name: /Merge 2 shots/ })).toBeInTheDocument()
    // Both descriptions appear in the modal AND in the shot list panel — use getAllByText
    expect(screen.getAllByText('VARIOUS OF ARTEMIS I').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('VARIOUS OF MOON SURFACE').length).toBeGreaterThanOrEqual(1)
  })

  it('confirming merge modal reduces shot count by 1', () => {
    render(<EditorPane {...defaultProps} />)
    const checkboxes = screen.getAllByRole('checkbox')
    fireEvent.click(checkboxes[0])
    fireEvent.click(checkboxes[1])
    fireEvent.click(screen.getByText('Merge selected'))
    // Confirm with the default first option selected
    fireEvent.click(screen.getByText('Merge with this description'))
    expect(screen.getByText(/1 \/ 2/)).toBeInTheDocument()
  })

  // ---------------------------------------------------------------------------
  // Split tests
  // ---------------------------------------------------------------------------

  it('clicking Split with playhead at shot start shows a toast (no split)', () => {
    // jsdom sets video.currentTime = 0, shot[0].seconds = 0 — split guard fires
    render(<EditorPane {...defaultProps} />)
    fireEvent.click(screen.getByText('Split'))
    // Shot count unchanged — guard prevented split
    expect(screen.getByText(/1 \/ 3/)).toBeInTheDocument()
  })

  it('Split keyboard shortcut S does not crash when playhead is at start', () => {
    render(<EditorPane {...defaultProps} />)
    fireEvent.keyDown(window, { key: 's' })
    expect(screen.getByText(/1 \/ 3/)).toBeInTheDocument()
  })

  it('Split with playhead inside shot range creates an extra shot', () => {
    render(<EditorPane {...defaultProps} />)
    const video = document.querySelector('video')
    // Set currentTime to 3s — inside shot[0] which starts at 0s
    Object.defineProperty(video, 'currentTime', { writable: true, value: 3 })
    fireEvent.click(screen.getByText('Split'))
    // selIdx advances to 1 after split, so counter shows "2 / 4"
    expect(screen.getByText(/2 \/ 4/)).toBeInTheDocument()
  })

  it('after split, new shot gets the playhead timecode as its IN', () => {
    render(<EditorPane {...defaultProps} />)
    const video = document.querySelector('video')
    Object.defineProperty(video, 'currentTime', { writable: true, value: 2 })
    fireEvent.click(screen.getByText('Split'))
    // After split selIdx advances to 1 (the new half) — already selected, no Next needed
    const inputs = screen.getAllByPlaceholderText('00:00:00:00')
    // IN of new shot should be 00:00:02:00 (2s at 25fps)
    expect(inputs[0].value).toBe('00:00:02:00')
  })

  // ---------------------------------------------------------------------------
  // White flash tests
  // ---------------------------------------------------------------------------

  it('Add White Flash button in modal inserts a WF shot', () => {
    render(<EditorPane {...defaultProps} />)
    fireEvent.click(screen.getAllByTitle('W')[0])
    fireEvent.click(screen.getByRole('button', { name: 'Add White Flash' }))
    // selIdx advances to the new WF shot at index 1, so counter shows "2 / 4"
    expect(screen.getByText(/2 \/ 4/)).toBeInTheDocument()
  })

  it('WF shot description shows frame count', () => {
    render(<EditorPane {...defaultProps} />)
    fireEvent.click(screen.getAllByTitle('W')[0])
    // wfF defaults to 2; after insert selIdx = 1 (the WF shot) — already selected
    fireEvent.click(screen.getByRole('button', { name: 'Add White Flash' }))
    expect(screen.getByDisplayValue(/White flash \(2f\)/)).toBeInTheDocument()
  })

  it('changing WF frame count updates the description accordingly', () => {
    render(<EditorPane {...defaultProps} />)
    fireEvent.click(screen.getAllByTitle('W')[0])
    const frameInput = screen.getByRole('spinbutton')
    fireEvent.change(frameInput, { target: { value: '5' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add White Flash' }))
    // After insert selIdx = 1 (the WF shot) — already selected
    expect(screen.getByDisplayValue(/White flash \(5f\)/)).toBeInTheDocument()
  })

  it('WF keyboard shortcut W opens the modal', () => {
    render(<EditorPane {...defaultProps} />)
    fireEvent.keyDown(window, { key: 'w' })
    expect(screen.getByRole('heading', { name: 'Add White Flash' })).toBeInTheDocument()
  })

  // ---------------------------------------------------------------------------
  // Dateline display tests
  // ---------------------------------------------------------------------------

  it('shows Dateline section when shot has location/date/source', () => {
    const shotsWithDateline = [
      { ...MOCK_SHOTS[0], location: 'CAPE CANAVERAL', date: 'NOVEMBER 16, 2022',
        source: 'NASA', restrictions: 'Editorial use only',
        restrictions_broadcast: 'Editorial use only', restrictions_digital: 'Editorial use only' },
      ...MOCK_SHOTS.slice(1),
    ]
    render(<EditorPane {...defaultProps} results={shotsWithDateline} />)
    expect(screen.getByText('Dateline')).toBeInTheDocument()
    expect(screen.getByText('CAPE CANAVERAL')).toBeInTheDocument()
    expect(screen.getByText('NOVEMBER 16, 2022')).toBeInTheDocument()
    expect(screen.getByText('NASA')).toBeInTheDocument()
  })

  it('shows split Broadcast/Digital restrictions when both present', () => {
    const shotsWithSplit = [
      { ...MOCK_SHOTS[0], location: 'LONDON', date: 'RECENT',
        source: 'REUTERS', restrictions: 'Broadcast: Access all. Digital: No resales',
        restrictions_broadcast: 'Access all', restrictions_digital: 'No resales' },
      ...MOCK_SHOTS.slice(1),
    ]
    render(<EditorPane {...defaultProps} results={shotsWithSplit} />)
    expect(screen.getByText('Broadcast')).toBeInTheDocument()
    expect(screen.getByText('Digital')).toBeInTheDocument()
    expect(screen.getByText('Access all')).toBeInTheDocument()
    expect(screen.getByText('No resales')).toBeInTheDocument()
  })

  it('shows single Restrictions label when no keyword split', () => {
    const shotsWithRestrictions = [
      { ...MOCK_SHOTS[0], location: 'LONDON', date: 'RECENT',
        source: 'REUTERS', restrictions: 'Access all',
        restrictions_broadcast: 'Access all', restrictions_digital: 'Access all' },
      ...MOCK_SHOTS.slice(1),
    ]
    render(<EditorPane {...defaultProps} results={shotsWithRestrictions} />)
    // restrictions_broadcast and _digital are both set, so "Broadcast" label appears
    expect(screen.getByText('Broadcast')).toBeInTheDocument()
  })

  it('does not show Dateline section when shot has no dateline fields', () => {
    render(<EditorPane {...defaultProps} />)
    // MOCK_SHOTS have no location/date/source — section should be absent
    expect(screen.queryByText('Dateline')).not.toBeInTheDocument()
  })

  // ---------------------------------------------------------------------------
  // Undo/Redo keyboard shortcuts
  // ---------------------------------------------------------------------------

  it('Ctrl+Z undoes a merge', () => {
    render(<EditorPane {...defaultProps} />)
    fireEvent.click(screen.getByText('Merge'))
    expect(screen.getByText(/1 \/ 2/)).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'z', ctrlKey: true })
    expect(screen.getByText(/1 \/ 3/)).toBeInTheDocument()
  })

  it('Ctrl+Y redoes after undo', () => {
    render(<EditorPane {...defaultProps} />)
    fireEvent.click(screen.getByText('Merge'))
    fireEvent.keyDown(window, { key: 'z', ctrlKey: true })
    expect(screen.getByText(/1 \/ 3/)).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'y', ctrlKey: true })
    expect(screen.getByText(/1 \/ 2/)).toBeInTheDocument()
  })

  // ---------------------------------------------------------------------------
  // Delete shot
  // ---------------------------------------------------------------------------

  it('Delete key removes the current shot', () => {
    render(<EditorPane {...defaultProps} />)
    fireEvent.keyDown(window, { key: 'Delete' })
    expect(screen.getByText(/1 \/ 2/)).toBeInTheDocument()
  })

  it('Delete does not remove the last shot', () => {
    const oneShot = [MOCK_SHOTS[0]]
    render(<EditorPane {...defaultProps} results={oneShot} />)
    fireEvent.keyDown(window, { key: 'Delete' })
    expect(screen.getByText(/1 \/ 1/)).toBeInTheDocument()
  })
})