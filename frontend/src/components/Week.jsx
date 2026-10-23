import { dayName, hours, clock } from '../format.js'
import { DigestBody } from './Digest.jsx'

const MAX_MIN = 10 * 60

export const FLAG_LABEL = { no_progress: 'No visible progress', short_visit: 'Short visit' }

function listDays(dates) {
  const names = dates.map((d) => dayName(d, 'short').split(',')[0])
  return names.length < 2 ? names.join('') : `${names.slice(0, -1).join(', ')} and ${names.at(-1)}`
}

const STAGGER_MS = 70

function Column({ d, tz, i }) {
  const delay = { animationDelay: `${i * STAGGER_MS}ms` }
  const labelDelay = { animationDelay: `${i * STAGGER_MS + 350}ms` }
  const s = d.summary
  const h = Math.min(100, (s.total_min / MAX_MIN) * 100)
  const label = {
    worked: hours(s.total_min),
    no_show: 'No-show',
    off: 'Off',
    pending: 'Waiting',
    delivery_only: 'Delivery',
  }[s.status]
  return (
    <div className="flex flex-col items-center gap-2 min-w-0">
      <div className="glass relative h-40 w-full max-w-[56px] rounded-sm flex items-end overflow-hidden">
        {s.status === 'worked' && <div className={`tape bar-grow w-full ${d.flag === 'no_progress' ? 'opacity-40' : ''}`} style={{ height: `${h}%`, ...delay }} title={`${clock(s.first_arrival_ms, tz)} to ${clock(s.last_departure_ms, tz)}`} />}
        {s.status === 'no_show' && <div className="bar-grow w-full h-full bg-alarm/10 border-t-4 border-alarm" style={delay} />}
      </div>
      <span style={labelDelay} className={`bar-label font-display text-sm sm:text-lg leading-none whitespace-nowrap tabular-nums ${s.status === 'no_show' ? 'text-alarm' : s.status === 'worked' ? 'text-ink' : 'text-muted'}`}>{label}</span>
      <span className="text-xs text-muted text-center">{dayName(d.summary.date, 'short')}</span>
      {d.flag && <span className="text-[11px] leading-tight font-medium text-alarm text-center">{FLAG_LABEL[d.flag]}</span>}
    </div>
  )
}

export default function Week({ week, tz }) {
  const t = week.totals
  const digests = week.days.filter((d) => d.digest).reverse()
  return (
    <div>
      <p className="font-display text-4xl sm:text-5xl font-semibold leading-tight">
        {t.days_worked} of {t.scheduled_days} scheduled days worked, {hours(t.total_min)} on site
      </p>
      {t.no_shows > 0 && <p className="mt-2 text-alarm font-medium">{t.no_shows === 1 ? 'One scheduled day had no crew.' : `${t.no_shows} scheduled days had no crew.`}</p>}
      {t.stalled_days?.length >= 2 && (
        <p className="mt-2 text-alarm font-medium">
          Crew on site {t.stalled_days.length} work days in a row ({listDays(t.stalled_days)}) with no visible change in the work area.
        </p>
      )}
      {t.stalled_days?.length < 2 && t.no_progress_days > 0 && (
        <p className="mt-2 text-muted">{t.no_progress_days === 1 ? 'One work day' : `${t.no_progress_days} work days`} with no visible progress. One quiet day is normal: work behind walls, drying time, inspections.</p>
      )}

      <div className="mt-8 grid grid-cols-7 gap-2 sm:gap-4">
        {week.days.map((d, i) => <Column key={d.summary.date} d={d} tz={tz} i={i} />)}
      </div>

      <h2 id="progress-notes" className="mt-12 font-display text-2xl font-semibold">Progress notes</h2>
      {digests.length === 0 && <p className="mt-2 text-muted">No progress notes this week yet.</p>}
      <ol className="mt-4 space-y-4">
        {digests.map((d) => (
          <li key={d.summary.date} className="glass grid gap-4 sm:grid-cols-[150px_1fr] rounded-md p-5">
            <div>
              <p className="font-display text-xl font-semibold">{dayName(d.summary.date)}</p>
              <p className="text-sm text-muted">{clock(d.summary.first_arrival_ms, tz)} to {clock(d.summary.last_departure_ms, tz)}</p>
              <p className="text-sm text-muted">{hours(d.summary.total_min)} on site</p>
              {d.flag && <p className="mt-1 text-sm font-medium text-alarm">{FLAG_LABEL[d.flag]}</p>}
            </div>
            <DigestBody digest={d.digest} compact />
          </li>
        ))}
      </ol>
    </div>
  )
}
