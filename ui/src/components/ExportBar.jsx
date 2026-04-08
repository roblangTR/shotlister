/**
 * ExportBar — CSV download and clipboard copy.
 *
 * Downloads via GET /export/{job_id}?format=csv.
 * Clipboard copy builds CSV from local state so it reflects any reassignments
 * made in ReviewPane without needing a round-trip to the server.
 */
import { useState } from 'react'

function buildCsv(results) {
  const headers = ['shot_index', 'timecode', 'matched_entry', 'matched_description', 'confidence', 'notes']
  const rows = results.map(r =>
    headers.map(h => {
      const val = r[h] ?? ''
      // Escape fields that contain commas or quotes
      const str = String(val)
      if (str.includes(',') || str.includes('"') || str.includes('\n')) {
        return `"${str.replace(/"/g, '""')}"`
      }
      return str
    }).join(',')
  )
  return [headers.join(','), ...rows].join('\n')
}

export default function ExportBar({ jobId, results }) {
  const [copied, setCopied] = useState(false)

  if (!results || results.length === 0 || !jobId) return null

  function handleDownload() {
    window.location.href = `/export/${jobId}?format=csv`
  }

  async function handleCopy() {
    const csv = buildCsv(results)
    try {
      await navigator.clipboard.writeText(csv)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Fallback: open in new tab as data URI
      const blob = new Blob([csv], { type: 'text/csv' })
      const url = URL.createObjectURL(blob)
      window.open(url)
    }
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 flex items-center gap-3">
      <span className="text-sm font-medium text-gray-700">
        {results.length} shots matched
      </span>
      {/* Job ID — lets the user call /debug/{job_id} directly */}
      <span className="text-xs text-gray-400 font-mono ml-2 mr-auto" title="Use this ID with /debug/{job_id}">
        job: <span
          className="cursor-pointer hover:text-blue-600 hover:underline"
          title="Click to open debug view in new tab"
          onClick={() => window.open(`/debug/${jobId}`, '_blank')}
        >{jobId}</span>
      </span>
      <button
        onClick={handleCopy}
        className="text-sm border border-gray-300 rounded-md px-4 py-2 hover:bg-gray-50 transition-colors"
      >
        {copied ? 'Copied!' : 'Copy to clipboard'}
      </button>
      <button
        onClick={handleDownload}
        className="text-sm bg-blue-600 hover:bg-blue-700 text-white rounded-md px-4 py-2 transition-colors font-medium"
      >
        Export CSV
      </button>
    </div>
  )
}
