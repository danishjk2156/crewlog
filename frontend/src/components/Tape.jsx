import { clock, minuteOfDay } from '../format.js'

const START = 6 * 60 // 6 am
const END = 21 * 60 // 9 pm
const SPAN = END - START
const pct = (min) => `${Math.min(100, Math.max(0, ((min - START) / SPAN) * 100))}%`

const markClass = (sub, ink, inkBorder) =>
  ({
    human: `${ink} h-3 w-[3px]`,
    vehicle: `bg-transparent border-2 ${inkBorder} h-3 w-3 rounded-full -translate-x-1/2`,
    package_delivery: 'bg-muted h-3 w-3 -translate-x-1/2',
  })[sub]

export default function Tape({ summary, events = [], tz, expectedStart, isToday, dark = false }) {
  const ink = dark ? 'bg-paper' : 'bg-ink'
  const inkBorder = dark ? 'border-paper' : 'border-ink'
  const hoursTicks = []
  for (let m = START; m <= END; m += 60) hoursTicks.push(m)
  const [eh, em] = (expectedStart || '08:00').split(':').map(Number)
  const expected = eh * 60 + em
  const now = isToday ? minuteOfDay(Date.now(), tz) : null

  return (
    <figure className="mt-6" aria-label="Time on site today">
      {/* event marks */}
      <div className="relative h-5">
        {events
          .filter((e) => markClass(e.sub_type, ink, inkBorder))
          .map((e, i) => (
            <span
              key={i}
              title={`${e.sub_type.replace('_', ' ')} at ${clock(e.ts_ms, tz)}`}
              className={`absolute bottom-0 ${markClass(e.sub_type, ink, inkBorder)}`}
              style={{ left: pct(minuteOfDay(e.ts_ms, tz)) }}
            />
          ))}
      </div>

      {/* the tape */}
      <div className={`relative h-14 rounded-sm overflow-hidden ${dark ? 'bg-white/10' : 'bg-black/30 border border-rule'}`}>
        {summary.sessions.map((s, i) => {
          const a = minuteOfDay(s.start_ms, tz)
          const b = minuteOfDay(s.end_ms, tz)
          return (
            <div
              key={`${s.start_ms}-${i}`}
              className="tape tape-grow absolute top-0 bottom-0"
              style={{ left: pct(a), width: `calc(${pct(b)} - ${pct(a)})` }}
              title={`${clock(s.start_ms, tz)} to ${clock(s.end_ms, tz)}`}
            />
          )
        })}
        <div className={`absolute top-0 bottom-0 border-l-2 border-dashed ${dark ? 'border-paper/60' : 'border-ink/50'}`} style={{ left: pct(expected) }} />
        {now != null && now > START && now < END && (
          <div className="absolute top-0 bottom-0 w-[2px] bg-alarm" style={{ left: pct(now) }} />
        )}
      </div>

      {/* ruler */}
      <div className="relative h-8">
        {hoursTicks.map((m) => (
          <div key={m} className="absolute top-0 flex flex-col items-center -translate-x-1/2" style={{ left: pct(m) }}>
            <span className={`h-2 w-px ${dark ? 'bg-paper/60' : 'bg-ink/60'}`} />
            <span className={`mt-1 font-display text-sm tabular-nums ${(m / 60) % 3 ? 'hidden sm:inline' : ''} ${dark ? 'text-paper/70' : 'text-muted'}`}>
              {((m / 60 + 11) % 12) + 1}
              {m < 720 ? 'a' : 'p'}
            </span>
          </div>
        ))}
      </div>

      <figcaption className={`mt-2 flex flex-wrap gap-x-6 gap-y-1 text-sm ${dark ? 'text-paper/70' : 'text-muted'}`}>
        <span className="flex items-center gap-2"><span className="tape inline-block h-3 w-6" /> Crew on site</span>
        <span className="flex items-center gap-2"><span className={`inline-block h-3 w-[3px] ${ink}`} /> Person seen</span>
        <span className="flex items-center gap-2"><span className={`inline-block h-3 w-3 rounded-full border-2 ${inkBorder}`} /> Vehicle</span>
        <span className="flex items-center gap-2"><span className="inline-block h-3 w-3 bg-muted" /> Delivery</span>
        <span className="flex items-center gap-2"><span className={`inline-block h-3 border-l-2 border-dashed ${dark ? 'border-paper/60' : 'border-ink/50'}`} /> Expected start</span>
      </figcaption>
    </figure>
  )
}
