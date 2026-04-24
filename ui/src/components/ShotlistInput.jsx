/**
 * ShotlistInput — textarea for pasting a Reuters shotlist, plus a collapsible
 * settings panel for the ESSO token.
 *
 * The ESSO token is a JWT. We decode its `exp` claim client-side and cache
 * the token in localStorage until it expires, so the user only needs to paste
 * it once per day. The token is cleared automatically on expiry.
 *
 * The Gemini workflow ID is hardcoded — users do not need to supply it.
 */
import { useState } from 'react'

const ESSO_CACHE_KEY = 'shotlist_esso_cache'

/** Decode the exp claim from a JWT without verifying the signature. */
function jwtExp(token) {
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
    return payload.exp || null  // unix seconds
  } catch {
    return null
  }
}

/** Return cached token if still valid, otherwise null. */
function loadCachedToken() {
  try {
    const raw = localStorage.getItem(ESSO_CACHE_KEY)
    if (!raw) return ''
    const { token, exp } = JSON.parse(raw)
    if (exp && Date.now() / 1000 < exp) return token
    localStorage.removeItem(ESSO_CACHE_KEY)
  } catch {
    // Parsing the cached token failed — treat as no cached token
  }
  return ''
}

/** Persist token alongside its expiry. */
function persistToken(token) {
  const exp = jwtExp(token)
  if (exp) {
    localStorage.setItem(ESSO_CACHE_KEY, JSON.stringify({ token, exp }))
  }
}

/** Human-readable time remaining, e.g. "expires in 6h 42m". */
function tokenExpiry(token) {
  const exp = jwtExp(token)
  if (!exp) return null
  const secs = Math.floor(exp - Date.now() / 1000)
  if (secs <= 0) return 'expired'
  const h = Math.floor(secs / 3600)
  const m = Math.floor((secs % 3600) / 60)
  return h > 0 ? `expires in ${h}h ${m}m` : `expires in ${m}m`
}

/**
 * Parse a Reuters shotlist text into a minimal list of {entry_number, description}
 * objects for use in the ReviewPane reassignment dropdown.
 * Mirrors the logic in shotlist_parser.py.
 */
function parseShotlistClientSide(text) {
  if (!text) return []
  const parts = text.split(/(?=^\d+\.\s)/m)
  const entries = []
  for (const part of parts) {
    const m = part.match(/^(\d+)\.\s+([\s\S]*)/)
    if (!m) continue
    const entry_number = parseInt(m[1], 10)
    const description = m[2].replace(/\s+/g, ' ').trim()
    entries.push({ entry_number, description })
  }
  return entries
}

export default function ShotlistInput({ jobId, videoPath, shots, onMatched, onEntriesParsed, compact }) {
  const [shotlistText, setShotlistText] = useState('')
  const [essoToken, setEssoToken] = useState(loadCachedToken)
  const WORKFLOW_ID = 'ee360c20-9f8a-4fcd-95a1-ceacb4224cce'
  const [showSettings, setShowSettings] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const canMatch = shots && shots.length > 0 && shotlistText.trim() && essoToken

  async function handleMatch(e) {
    e.preventDefault()
    if (!canMatch) return
    setError('')
    setLoading(true)
    try {
      const resp = await fetch('/match', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          job_id: jobId,
          video_path: videoPath,
          shotlist_text: shotlistText,
          esso_token: essoToken,
          workflow_id: WORKFLOW_ID,
        }),
      })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'Match failed')
      if (onEntriesParsed) onEntriesParsed(parseShotlistClientSide(shotlistText))
      onMatched(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const tokenInput = (
    <input
      type="password"
      value={essoToken}
      onChange={e => {
        const val = e.target.value
        setEssoToken(val)
        if (val) persistToken(val)
        else localStorage.removeItem(ESSO_CACHE_KEY)
      }}
      placeholder="Paste ESSO token — saved until it expires"
      autoComplete="off"
      className="border border-gray-300 rounded px-2 py-1 text-xs font-mono"
    />
  )

  if (compact) {
    return (
      <form onSubmit={handleMatch} className="bg-white border border-gray-200 rounded-md px-3 py-1.5 flex items-center gap-2">
        <span className="text-xs font-medium text-gray-500 shrink-0">Shotlist</span>
        <span className="text-xs text-gray-400 shrink-0">
          {shotlistText.trim() ? `${parseShotlistClientSide(shotlistText).length} entries` : 'none'}
        </span>
        <div className="flex items-center gap-1 ml-auto shrink-0">
          <span className="text-xs text-gray-400">ESSO</span>
          {tokenInput}
          {essoToken && (
            <span className={`text-xs ${tokenExpiry(essoToken) === 'expired' ? 'text-red-500' : 'text-green-600'}`}>
              {tokenExpiry(essoToken)}
            </span>
          )}
        </div>
        <button type="submit" disabled={loading || !canMatch}
          className="text-xs bg-green-600 hover:bg-green-700 disabled:bg-gray-300 text-white px-2 py-1 rounded shrink-0">
          {loading ? 'Matching…' : 'Re-match'}
        </button>
        {error && <span className="text-xs text-red-600 shrink-0">{error}</span>}
      </form>
    )
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4">
      <h2 className="text-sm font-semibold text-gray-900 mb-3">2. Shotlist</h2>
      <form onSubmit={handleMatch} className="space-y-3">
        <textarea
          value={shotlistText}
          onChange={e => setShotlistText(e.target.value)}
          rows={8}
          placeholder="CAPE CANAVERAL, FLORIDA…&#10;&#10;1. VARIOUS OF ARTEMIS I…&#10;2. (SOUNDBITE)…"
          className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y"
        />

        <div className="flex items-center gap-2">
          <button type="button" onClick={() => setShowSettings(v => !v)}
            className="text-xs text-gray-400 hover:text-gray-600">
            {showSettings ? '▲' : '▼'} API settings
          </button>
          {essoToken && (
            <span className={`text-xs ${tokenExpiry(essoToken) === 'expired' ? 'text-red-500' : 'text-green-600'}`}>
              ESSO {tokenExpiry(essoToken)}
            </span>
          )}
        </div>

        {showSettings && (
          <div className="bg-gray-50 border border-gray-200 rounded-md p-3">
            <label className="block text-xs text-gray-600 mb-1">
              ESSO token —{' '}
              <a href="https://dataandanalytics.int.thomsonreuters.com/user-details"
                target="_blank" rel="noreferrer" className="text-blue-600 hover:underline">
                get yours here
              </a>
            </label>
            <input
              type="password"
              value={essoToken}
              onChange={e => {
                const val = e.target.value
                setEssoToken(val)
                if (val) persistToken(val)
                else localStorage.removeItem(ESSO_CACHE_KEY)
              }}
              placeholder="Paste your ESSO token — saved until it expires"
              autoComplete="off"
              className="w-full border border-gray-300 rounded px-2 py-1 text-sm font-mono"
            />
          </div>
        )}

        {(!shots || shots.length === 0) && (
          <p className="text-xs text-amber-600">Detect shots first (step 1) before matching.</p>
        )}
        {error && <p className="text-xs text-red-600">{error}</p>}

        <button type="submit" disabled={loading || !canMatch}
          className="w-full bg-green-600 hover:bg-green-700 disabled:bg-gray-300 text-white font-medium py-1.5 px-4 rounded-md text-sm">
          {loading ? 'Matching (this may take a minute)…' : 'Match shotlist'}
        </button>
      </form>
    </div>
  )
}
