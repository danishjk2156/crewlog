async function req(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`)
  return data
}

export const api = {
  jobs: () => req('GET', '/api/jobs'),
  createJob: (body) => req('POST', '/api/jobs', body),
  patchJob: (id, body) => req('PATCH', `/api/jobs/${id}`, body),
  day: (id, date) => req('GET', `/api/jobs/${id}/day${date ? `?date=${date}` : ''}`),
  week: (id) => req('GET', `/api/jobs/${id}/week`),
  runDigest: (id, date) => req('POST', `/api/jobs/${id}/digest/run${date ? `?date=${date}` : ''}`),
  report: (token) => req('GET', `/api/report/${token}`),
  devices: () => req('GET', '/api/ring/devices'),
}
