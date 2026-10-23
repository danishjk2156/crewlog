import { useEffect, useState } from 'react'
import { api } from '../api.js'

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

const field = 'mt-1 w-full min-h-[44px] rounded-sm border border-muted/60 bg-black/30 px-3 py-2 text-ink placeholder:text-muted/70 focus:border-safety'

export default function Setup({ job, onSaved }) {
  const [form, setForm] = useState(
    job || {
      name: 'Kitchen renovation',
      contractor_name: '',
      contractor_contact: '',
      device_id: '',
      work_days: [0, 1, 2, 3, 4],
      expected_start: '08:00',
      grace_min: 60,
      digest_time: '18:00',
    },
  )
  const [devices, setDevices] = useState([])
  const [deviceError, setDeviceError] = useState('')
  const [status, setStatus] = useState('')
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    api.devices().then((r) => setDevices(r.devices)).catch((e) => setDeviceError(e.message))
  }, [])

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })
  const toggleDay = (i) =>
    setForm({ ...form, work_days: form.work_days.includes(i) ? form.work_days.filter((d) => d !== i) : [...form.work_days, i].sort() })

  async function save(e) {
    e.preventDefault()
    setStatus('saving')
    const body = { ...form, grace_min: Number(form.grace_min), device_id: form.device_id || null }
    try {
      const saved = job ? await api.patchJob(job.id, body) : await api.createJob(body)
      setStatus('saved')
      onSaved(saved)
    } catch (err) {
      setStatus(err.message)
    }
  }

  const shareUrl = job ? `${window.location.origin}/report/${job.share_token}` : ''

  return (
    <form onSubmit={save} className="glass max-w-xl rounded-md p-5 sm:p-8">
      <h1 className="font-display text-5xl font-semibold">{job ? 'Job settings' : 'Set up your job'}</h1>
      <p className="mt-2 text-muted">CrewLog watches your Ring camera for arrivals and departures on the days you expect work.</p>

      <div className="mt-8 space-y-5">
        <label className="block">Project name<input className={field} value={form.name} onChange={set('name')} required /></label>
        <label className="block">Contractor<input className={field} value={form.contractor_name} onChange={set('contractor_name')} placeholder="Mike's Remodeling" required /></label>
        <label className="block">Contractor phone or email <span className="text-muted">(never shown on the shared report)</span><input className={field} value={form.contractor_contact} onChange={set('contractor_contact')} /></label>

        <label className="block">
          Ring camera facing the work entrance
          <select className={field} value={form.device_id || ''} onChange={set('device_id')}>
            <option value="">Use the first camera that sees motion</option>
            {devices.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
          {deviceError && <span className="mt-1 block text-sm text-alarm">Couldn't reach Ring: {deviceError}</span>}
        </label>

        <fieldset>
          <legend>Work days</legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {DAYS.map((d, i) => (
              <button
                type="button"
                key={d}
                aria-pressed={form.work_days.includes(i)}
                onClick={() => toggleDay(i)}
                className={`min-h-[44px] min-w-[44px] rounded-sm border px-3 text-sm ${form.work_days.includes(i) ? 'border-ink bg-ink text-paper' : 'border-muted/60 bg-black/30 hover:border-muted'}`}
              >
                {d}
              </button>
            ))}
          </div>
        </fieldset>

        <div className="grid grid-cols-3 gap-4">
          <label className="block">Crew expected by<input type="time" className={field} value={form.expected_start} onChange={set('expected_start')} /></label>
          <label className="block">Alert after (min)<input type="number" min="0" className={field} value={form.grace_min} onChange={set('grace_min')} /></label>
          <label className="block">Daily note at<input type="time" className={field} value={form.digest_time} onChange={set('digest_time')} /></label>
        </div>
      </div>

      <div className="mt-8 flex items-center gap-4">
        <button className="min-h-[44px] rounded-sm bg-ink px-5 font-medium text-paper hover:bg-ink/90">{job ? 'Save changes' : 'Start logging'}</button>
        {status === 'saved' && <span className="text-sm text-muted">Saved</span>}
        {status && !['saved', 'saving'].includes(status) && <span className="text-sm text-alarm">{status}</span>}
      </div>

      {job && (
        <div className="mt-12 border-t border-rule pt-6">
          <h2 className="font-display text-2xl font-semibold">Share the weekly report</h2>
          <p className="mt-1 text-muted">Send this link to your contractor so you both see the same facts. It shows visit times and progress notes only.</p>
          <div className="mt-3 flex gap-2">
            <input readOnly value={shareUrl} className={`${field} mt-0 text-sm`} onFocus={(e) => e.target.select()} />
            <button
              type="button"
              onClick={async () => { await navigator.clipboard?.writeText(shareUrl); setCopied(true) }}
              className="shrink-0 min-h-[44px] rounded-sm border border-ink px-4 text-sm font-medium hover:bg-ink hover:text-paper"
            >
              {copied ? 'Copied' : 'Copy link'}
            </button>
          </div>
        </div>
      )}
    </form>
  )
}
