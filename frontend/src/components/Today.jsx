import { useState } from 'react'
import Tape from './Tape.jsx'
import Digest from './Digest.jsx'
import { FLAG_LABEL } from './Week.jsx'
import { clock, hours, dayName } from '../format.js'

function statusLine(s, tz, expectedStart) {
  const [h, m] = expectedStart.split(':').map(Number)
  const expected = new Date(2000, 0, 1, h, m).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
  const recent = s.last_departure_ms && Date.now() - s.last_departure_ms < 45 * 60 * 1000
  switch (s.status) {
    case 'worked':
      return recent
        ? { title: 'Crew on site', detail: `Since ${clock(s.first_arrival_ms, tz)}`, tone: 'text-ink' }
        : { title: 'Crew worked today', detail: `${clock(s.first_arrival_ms, tz)} to ${clock(s.last_departure_ms, tz)}`, tone: 'text-ink' }
    case 'pending':
      return { title: 'Waiting for the crew', detail: `Expected by ${expected}`, tone: 'text-ink' }
    case 'no_show':
      return { title: 'Nobody showed up', detail: `Expected by ${expected}`, tone: 'text-alarm' }
    case 'delivery_only':
      return { title: 'Delivery only', detail: 'Something arrived, but no crew', tone: 'text-ink' }
    default:
      return { title: 'Day off', detail: 'No work scheduled today', tone: 'text-muted' }
  }
}

const ROLE_LABEL = { visitor: 'visitor or neighbour', household: 'household' }

// Non-crew visits: shown so the homeowner can see they were filtered out, never counted as work.
function AlsoSeen({ visits, tz }) {
  if (!visits?.length) return null
  return (
    <p className="mt-3 text-sm text-muted max-w-prose">
      <span className="font-medium text-ink">Also seen:</span>{' '}
      {visits.map((v, i) => (
        <span key={v.start_ms}>
          {i > 0 && ', '}
          {ROLE_LABEL[v.role]} at {clock(v.start_ms, tz)}
        </span>
      ))}
      . These don't count as work hours.
    </p>
  )
}

const NOTICE_TITLE = { check_in: 'Checked in', check_out: 'Checked out', day_summary: 'End of day' }
const viaText = (channels) => channels.join(' and ').replace('in_app', 'CrewLog').replace('sns', 'Amazon SNS')

function Alert({ alert, contractor }) {
  const [copied, setCopied] = useState(false)
  const notice = NOTICE_TITLE[alert.kind] // good news: arrival, departure, daily recap
  return (
    <div role="status" className={`glass rounded-md border-l-4 p-5 ${notice ? '!border-l-safety' : '!border-l-alarm'}`}>
      {notice && (
        <p className="mb-1 text-xs font-medium uppercase tracking-wider text-safety">
          {notice}
        </p>
      )}
      <p className="font-medium">{alert.message}</p>
      {alert.drafted_reply ? (
        <>
          <p className="mt-3 text-sm text-muted">Suggested message to {contractor}</p>
          <blockquote className="mt-1 text-[15px] leading-relaxed">{alert.drafted_reply}</blockquote>
          <div className="mt-3 flex items-center gap-4">
            <button
              onClick={async () => {
                await navigator.clipboard?.writeText(alert.drafted_reply)
                setCopied(true)
              }}
              className="min-h-[44px] rounded-sm border border-ink px-4 text-sm font-medium hover:bg-ink hover:text-paper"
            >
              {copied ? 'Copied' : 'Copy message'}
            </button>
            <span className="text-xs text-muted">Sent to you via {viaText(alert.channels)}</span>
          </div>
        </>
      ) : (
        <p className="mt-2 text-xs text-muted">Sent to you via {viaText(alert.channels)}</p>
      )}
    </div>
  )
}

export default function Today({ data, onRunDigest }) {
  const { job, summary, events, digest, alerts, date, flag } = data
  const tz = job.tz
  const line = statusLine(summary, tz, job.expected_start)
  const vehicles = summary.sessions.reduce((a, s) => a + s.vehicle_count, 0)

  const still = digest?.pm_snapshot || digest?.am_snapshot

  return (
    <div>
      <div className={`grid items-center gap-8 ${still ? 'md:grid-cols-[1fr_1.1fr]' : ''}`}>
        <div>
          <p className="flex items-center gap-3 text-muted">
            {dayName(date)}
            {line.title === 'Crew on site' && (
              <span className="inline-flex items-center gap-2 rounded-full border border-safety/40 bg-safety/10 px-2.5 py-0.5 text-xs font-medium uppercase tracking-wider text-safety">
                <span className="relative flex h-2 w-2" aria-hidden="true">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-safety opacity-75" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-safety" />
                </span>
                Live
              </span>
            )}
          </p>
          <h1 className={`mt-2 font-display font-bold uppercase leading-[0.88] tracking-[-0.01em] text-6xl sm:text-7xl lg:text-8xl ${line.tone}`} aria-live="polite">
            {line.title}
          </h1>
          <p className="mt-4 font-display text-3xl sm:text-4xl font-medium tabular-nums">{line.detail}</p>
          {summary.total_min > 0 && <p className="mt-1 text-muted">{hours(summary.total_min)} logged by your Ring camera</p>}
          {summary.sessions.some((s) => s.checked_in) && <p className="mt-2 text-sm font-medium text-safety">Crew checked in at the doorbell</p>}
          <div id="also-seen"><AlsoSeen visits={summary.other_visits} tz={tz} /></div>
          {flag && <p className="mt-2 font-medium text-alarm">{FLAG_LABEL[flag]}{flag === 'no_progress' ? ': the evening still looks the same as the morning' : ''}</p>}
        </div>
        {still && (
          <figure className="relative">
            <img src={still} alt="Latest camera still of the work area" className="w-full aspect-[16/10] object-cover rounded-md ring-1 ring-white/10 shadow-[0_30px_80px_-20px_rgba(0,0,0,.8)]" />
            <figcaption className="mt-2 text-sm text-muted">Latest still from the work area</figcaption>
          </figure>
        )}
      </div>

      <section className="glass mt-12 rounded-md px-4 sm:px-8 py-8">
        <h2 className="font-display text-2xl font-semibold">Time on site</h2>
        <Tape summary={summary} events={events} tz={tz} expectedStart={job.expected_start} isToday />
      </section>

      {alerts.length > 0 && (
        <div id="alerts" className="mt-8 space-y-3">
          {alerts.map((a) => <Alert key={a.id} alert={a} contractor={job.contractor_name} />)}
        </div>
      )}

      <div className="glass mt-8 rounded-md p-5 sm:p-8 grid gap-10 lg:grid-cols-[1fr_260px]">
        <Digest digest={digest} canRun={summary.status === 'worked'} onRun={onRunDigest} />
        <dl className="grid grid-cols-2 lg:grid-cols-1 gap-x-6 gap-y-5 content-start border-t lg:border-t-0 lg:border-l border-rule pt-6 lg:pt-0 lg:pl-8">
          {[
            ['Time on site', summary.total_min ? hours(summary.total_min) : '—'],
            ['First arrival', clock(summary.first_arrival_ms, tz)],
            ['Last seen', clock(summary.last_departure_ms, tz)],
            ['Vehicle sightings', vehicles || '—'],
            ['Deliveries', summary.deliveries || '—'],
          ].map(([k, v]) => (
            <div key={k}>
              <dt className="text-sm text-muted">{k}</dt>
              <dd className="font-display text-3xl font-semibold tabular-nums">{v}</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  )
}
