import { useState } from 'react'

export function DigestBody({ digest, compact = false }) {
  const fromBedrock = digest.model !== 'offline'
  return (
    <div>
      {digest.am_snapshot && digest.pm_snapshot && (
        <div className={`grid grid-cols-2 gap-3 ${compact ? 'mb-3' : 'mb-5'}`}>
          {[
            ['Morning', digest.am_snapshot],
            ['Evening', digest.pm_snapshot],
          ].map(([label, src]) => (
            <figure key={label}>
              <img src={src} alt={`${label} camera snapshot`} className="w-full aspect-[16/10] object-cover rounded-sm border border-rule bg-rule" loading="lazy" />
              <figcaption className="mt-1 text-sm text-muted">{label}</figcaption>
            </figure>
          ))}
        </div>
      )}
      <p className={compact ? 'text-[15px] leading-relaxed' : 'text-lg leading-relaxed max-w-prose'}>{digest.summary}</p>
      {digest.changes?.length > 0 && (
        <ul className="mt-3 space-y-1 text-[15px]">
          {digest.changes.map((c, i) => (
            <li key={i} className="flex gap-2"><span className="mt-2 h-1.5 w-3 shrink-0 bg-safety" />{c}</li>
          ))}
        </ul>
      )}
      {digest.concerns?.length > 0 && (
        <ul className="mt-3 space-y-1 text-[15px] text-alarm">
          {digest.concerns.map((c, i) => <li key={i}>Worth checking: {c}</li>)}
        </ul>
      )}
      <p className="mt-3 text-xs text-muted">
        {fromBedrock
          ? `Written by Amazon Bedrock (${digest.model}) from two camera stills. People are never described.`
          : digest.progress === 'none'
            ? 'The morning and evening stills are identical.'
            : 'Based on visit times from your Ring camera.'}
      </p>
    </div>
  )
}

export default function Digest({ digest, canRun, onRun }) {
  const [state, setState] = useState('idle')
  const [error, setError] = useState('')

  async function run() {
    setState('busy')
    setError('')
    try {
      await onRun()
      setState('done')
    } catch (e) {
      setError(e.message)
      setState('idle')
    }
  }

  return (
    <section>
      <div className="flex items-baseline justify-between gap-4">
        <h2 className="font-display text-2xl font-semibold">What changed today</h2>
        {canRun && (
          <button
            onClick={run}
            disabled={state === 'busy'}
            className="shrink-0 min-h-[44px] rounded-sm bg-ink px-4 text-sm font-medium text-paper hover:bg-ink/90 disabled:opacity-60"
          >
            {state === 'busy' ? 'Summarizing…' : digest ? 'Summarize again' : 'Summarize today'}
          </button>
        )}
      </div>
      {error && <p className="mt-2 text-sm text-alarm">{error}</p>}
      <div className="mt-4">
        {digest ? (
          <DigestBody digest={digest} />
        ) : (
          <p className="text-muted max-w-prose">
            {canRun
              ? 'The progress note is written at the end of the work day from a morning and an evening camera still. Summarize now to see it early.'
              : 'A progress note appears here on days the crew works.'}
          </p>
        )}
      </div>
    </section>
  )
}
