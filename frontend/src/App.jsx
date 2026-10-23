import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { api } from './api.js'
import Today from './components/Today.jsx'
import Week from './components/Week.jsx'
import Setup from './components/Setup.jsx'
import { dayName } from './format.js'

const POLL_MS = 3000
const TABS = [['today', 'Today'], ['week', 'This week'], ['setup', 'Settings']]
const SWIPE_PX = 70

// Underline that glides to the active tab.
function useIndicator(tab) {
  const navRef = useRef(null)
  const [box, setBox] = useState(null)
  useLayoutEffect(() => {
    const measure = () => {
      const el = navRef.current?.querySelector('[aria-selected="true"]')
      if (el) setBox({ left: el.offsetLeft, width: el.offsetWidth })
    }
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [tab])
  return [navRef, box]
}

function Mark() {
  return (
    <a href="/" className="flex min-h-[44px] items-center gap-2 font-display text-2xl font-bold tracking-tight">
      <span className="tape inline-block h-4 w-8 rounded-[2px]" aria-hidden="true" />
      CrewLog
    </a>
  )
}

function Report({ token }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => { api.report(token).then(setData).catch((e) => setError(e.message)) }, [token])
  return (
    <div className="mx-auto max-w-5xl px-4 sm:px-8 py-8">
      <header className="flex items-center justify-between border-b border-rule pb-4"><Mark /></header>
      <main className="py-10 page-rise">
        {error && <p className="text-alarm">This report link isn't valid. Ask the homeowner for a new one.</p>}
        {data && (
          <>
            <p className="text-muted">
              Weekly site report for {data.job.name}, {dayName(data.start, 'short')} to {dayName(data.end, 'short')}. Work by {data.job.contractor_name}.
            </p>
            <div className="mt-2"><Week week={data} tz={data.job.tz} /></div>
            <p className="mt-12 text-xs text-muted max-w-prose">
              Visit times come from motion events on the homeowner's Ring camera. Progress notes are written by AI from one morning and one evening still and never describe people.
            </p>
          </>
        )}
      </main>
    </div>
  )
}

export default function App() {
  const path = window.location.pathname
  const reportMatch = path.match(/^\/report\/([^/]+)/)
  const [tab, setTabState] = useState('today')
  const [dir, setDir] = useState('next')
  const touch = useRef(null)

  const setTab = useCallback((next) => {
    setTabState((cur) => {
      const a = TABS.findIndex(([k]) => k === cur)
      const b = TABS.findIndex(([k]) => k === next)
      if (a !== b) setDir(b > a ? 'next' : 'prev')
      return next
    })
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    window.scrollTo({ top: 0, behavior: reduce ? 'auto' : 'smooth' })
  }, [])

  const step = useCallback((delta) => {
    const i = TABS.findIndex(([k]) => k === tab)
    const next = TABS[(i + delta + TABS.length) % TABS.length][0]
    setTab(next)
    return next
  }, [tab, setTab])
  const [job, setJob] = useState(undefined)
  const [day, setDay] = useState(null)
  const [week, setWeek] = useState(null)
  const [error, setError] = useState('')
  const [navRef, indicator] = useIndicator(job ? tab : '')

  useEffect(() => {
    if (reportMatch) return
    api.jobs().then((r) => setJob(r.jobs.at(-1) || null)).catch((e) => setError(e.message))
  }, [])

  const refresh = useCallback(async () => {
    if (!job) return
    try {
      if (tab === 'today') setDay(await api.day(job.id))
      if (tab === 'week') setWeek(await api.week(job.id))
      setError('')
    } catch (e) {
      setError(e.message)
    }
  }, [job, tab])

  useEffect(() => {
    refresh()
    if (tab !== 'today') return
    const t = setInterval(refresh, POLL_MS)
    return () => clearInterval(t)
  }, [refresh, tab])

  if (reportMatch) return <Report token={reportMatch[1]} />

  const index = TABS.findIndex(([k]) => k === tab)

  // Tabs pattern: Left/Right/Home/End move between pages and keep focus on the tab.
  function onTabKey(e) {
    const moves = { ArrowRight: 1, ArrowLeft: -1 }
    let next
    if (e.key in moves) next = step(moves[e.key])
    else if (e.key === 'Home') setTab((next = TABS[0][0]))
    else if (e.key === 'End') setTab((next = TABS.at(-1)[0]))
    else return
    e.preventDefault()
    document.getElementById(`tab-${next}`)?.focus()
  }

  // Horizontal swipe on touch screens moves to the neighbouring page.
  const swipe = {
    onTouchStart: (e) => { touch.current = { x: e.touches[0].clientX, y: e.touches[0].clientY } },
    onTouchEnd: (e) => {
      const t = touch.current
      touch.current = null
      if (!t || !job || e.target.closest('input, select, textarea')) return
      const dx = e.changedTouches[0].clientX - t.x
      const dy = e.changedTouches[0].clientY - t.y
      if (Math.abs(dx) > SWIPE_PX && Math.abs(dx) > 2 * Math.abs(dy)) step(dx < 0 ? 1 : -1)
    },
  }

  return (
    <div className="mx-auto max-w-5xl px-4 sm:px-8 py-8">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-sm focus:bg-safety focus:px-3 focus:py-2 focus:text-paper">Skip to content</a>
      <header className="sticky top-0 z-30 -mx-4 sm:-mx-8 -mt-8 px-4 sm:px-8 py-4 flex flex-wrap items-center justify-between gap-4 border-b border-rule bg-paper/70 backdrop-blur-md">
        <div className="flex items-baseline gap-4">
          <Mark />
          {job && <span className="text-muted hidden sm:inline">{job.name} with {job.contractor_name}</span>}
        </div>
        {job && (
          <div className="flex items-center gap-4">
            <span className="hidden md:inline font-display text-sm tracking-[0.2em] text-muted tabular-nums" aria-hidden="true">
              <span className="text-ink">{String(index + 1).padStart(2, '0')}</span> / {String(TABS.length).padStart(2, '0')}
            </span>
            <div ref={navRef} role="tablist" aria-label="Views" className="relative flex gap-1" onKeyDown={onTabKey}>
              {TABS.map(([k, label]) => (
                <button
                  key={k}
                  id={`tab-${k}`}
                  role="tab"
                  aria-selected={tab === k}
                  aria-controls="main"
                  tabIndex={tab === k ? 0 : -1}
                  onClick={() => setTab(k)}
                  className={`min-h-[44px] px-3 text-sm font-medium transition-colors ${tab === k ? 'text-ink' : 'text-muted hover:text-ink'}`}
                >
                  {label}
                </button>
              ))}
              {indicator && (
                <span
                  aria-hidden="true"
                  className="pointer-events-none absolute bottom-0 h-1 rounded-full bg-safety transition-all duration-300 ease-out"
                  style={{ left: indicator.left, width: indicator.width }}
                />
              )}
            </div>
          </div>
        )}
      </header>

      <main
        id="main"
        role={job ? 'tabpanel' : undefined}
        aria-labelledby={job ? `tab-${tab}` : undefined}
        tabIndex={-1}
        className="py-10 overflow-x-clip focus:outline-none"
        {...swipe}
      >
        {error && <p role="alert" className="mb-6 text-alarm">Can't reach the CrewLog server: {error}. Check that the backend is running on port 8000.</p>}
        {job === null && <div className="page-rise"><Setup job={null} onSaved={(j) => { setJob(j); setTab('today') }} /></div>}
        {job && (
          <div key={tab} className={dir === 'next' ? 'page-next' : 'page-prev'}>
            {tab === 'today' && day && <Today data={day} onRunDigest={async () => { await api.runDigest(job.id); await refresh() }} />}
            {tab === 'week' && week && <Week week={week} tz={job.tz} />}
            {tab === 'setup' && <Setup job={job} onSaved={setJob} />}
          </div>
        )}
      </main>
    </div>
  )
}
