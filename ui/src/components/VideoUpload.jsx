import { useState } from 'react'

export default function VideoUpload({ onDetected, compact }) {
  const [videoPath, setVideoPath] = useState('')
  const [threshold, setThreshold] = useState(2.2)
  const [minSceneLen, setMinSceneLen] = useState(14)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleDetect(e) {
    e.preventDefault()
    if (!videoPath.trim()) return
    setError('')
    setLoading(true)
    try {
      const resp = await fetch('/detect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          video_path: videoPath.trim(),
          threshold: parseFloat(threshold),
          min_scene_len: parseInt(minSceneLen, 10),
        }),
      })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'Detection failed')
      onDetected(data, videoPath.trim())
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleBrowse() {
    try {
      const resp = await fetch('/browse')
      const data = await resp.json()
      if (data.path) setVideoPath(data.path)
    } catch {}
  }

  if (compact) {
    return (
      <form onSubmit={handleDetect} className="bg-white border border-gray-200 rounded-md px-3 py-1.5 flex items-center gap-2">
        <span className="text-xs font-medium text-gray-500 shrink-0">Video</span>
        <input
          type="text"
          value={videoPath}
          onChange={e => setVideoPath(e.target.value)}
          placeholder="/path/to/video.mp4"
          className="flex-1 text-xs font-mono border-0 focus:outline-none text-gray-700 min-w-0"
        />
        <button type="button" onClick={handleBrowse}
          className="text-xs text-gray-500 hover:text-gray-800 shrink-0">Browse…</button>
        <button type="submit" disabled={loading || !videoPath.trim()}
          className="text-xs bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 text-white px-2 py-1 rounded shrink-0">
          {loading ? 'Detecting…' : 'Re-detect'}
        </button>
        {error && <span className="text-xs text-red-600 shrink-0">{error}</span>}
      </form>
    )
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4">
      <h2 className="text-sm font-semibold text-gray-900 mb-3">1. Video File</h2>
      <form onSubmit={handleDetect} className="space-y-3">
        <div className="flex gap-2">
          <input
            type="text"
            value={videoPath}
            onChange={e => setVideoPath(e.target.value)}
            placeholder="/path/to/video.mp4"
            className="flex-1 border border-gray-300 rounded-md px-3 py-1.5 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button type="button" onClick={handleBrowse}
            className="px-3 py-1.5 text-sm bg-gray-100 hover:bg-gray-200 border border-gray-300 rounded-md text-gray-700 whitespace-nowrap">
            Browse…
          </button>
        </div>

        <button type="button" onClick={() => setShowAdvanced(v => !v)}
          className="text-xs text-gray-400 hover:text-gray-600">
          {showAdvanced ? '▲' : '▼'} Advanced
        </button>

        {showAdvanced && (
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-500 mb-1">Threshold</label>
              <input type="number" step="0.1" min="0.5" max="10" value={threshold}
                onChange={e => setThreshold(e.target.value)}
                className="w-full border border-gray-300 rounded px-2 py-1 text-sm" />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Min scene len (frames)</label>
              <input type="number" min="1" value={minSceneLen}
                onChange={e => setMinSceneLen(e.target.value)}
                className="w-full border border-gray-300 rounded px-2 py-1 text-sm" />
            </div>
          </div>
        )}

        {error && <p className="text-xs text-red-600">{error}</p>}

        <button type="submit" disabled={loading || !videoPath.trim()}
          className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 text-white font-medium py-1.5 px-4 rounded-md text-sm">
          {loading ? 'Detecting…' : 'Detect shots'}
        </button>
      </form>
    </div>
  )
}
