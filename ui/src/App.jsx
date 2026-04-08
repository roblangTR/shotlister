import { useState } from 'react'
import './index.css'
import VideoUpload from './components/VideoUpload'
import ShotlistInput from './components/ShotlistInput'
import ReviewPane from './components/ReviewPane'
import ExportBar from './components/ExportBar'

export default function App() {
  const [jobId, setJobId] = useState(null)
  const [videoPath, setVideoPath] = useState('')
  const [shots, setShots] = useState([])
  const [results, setResults] = useState([])
  const [shotlistEntries, setShotlistEntries] = useState([])

  function handleDetected(data, path) {
    setJobId(data.job_id)
    setShots(data.shots || [])
    setVideoPath(path)
    setResults([])
    setShotlistEntries([])
  }

  function handleMatched(data) {
    setJobId(prev => data.job_id || prev)
    setResults(data.results || [])
  }

  const hasResults = results.length > 0

  return (
    <div className="h-screen flex flex-col bg-gray-50 overflow-hidden">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-4 py-2 flex items-center gap-4 shrink-0">
        <h1 className="text-base font-bold text-gray-900">Shotlist Timecoder</h1>
        {shots.length > 0 && !hasResults && (
          <span className="text-xs text-blue-700 bg-blue-50 border border-blue-200 rounded px-2 py-0.5">
            {shots.length} shots detected — ready to match
          </span>
        )}
        {hasResults && (
          <span className="text-xs text-green-700 bg-green-50 border border-green-200 rounded px-2 py-0.5">
            {results.length} shots matched
          </span>
        )}
      </header>

      {/* Input row — compact once results are in */}
      <div className={`shrink-0 grid grid-cols-2 gap-3 px-4 ${hasResults ? 'pt-2 pb-1' : 'py-3'}`}>
        <VideoUpload onDetected={handleDetected} compact={hasResults} />
        <ShotlistInput
          jobId={jobId}
          videoPath={videoPath}
          shots={shots}
          onMatched={handleMatched}
          onEntriesParsed={setShotlistEntries}
          compact={hasResults}
        />
      </div>

      {/* Review pane — fills remaining space */}
      {hasResults && (
        <div className="flex-1 flex flex-col min-h-0 px-4 pb-2 gap-2">
          <ReviewPane
            results={results}
            shotlistEntries={shotlistEntries}
            onResultsChange={setResults}
            videoPath={videoPath}
          />
          <ExportBar jobId={jobId} results={results} />
        </div>
      )}

      {/* Empty state */}
      {!hasResults && !shots.length && (
        <div className="flex-1 flex items-center justify-center text-sm text-gray-400">
          Enter a video path and detect shots to begin.
        </div>
      )}
    </div>
  )
}
