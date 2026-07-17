import type { RunProgress, RunRequest } from './types'

export async function createJob(request: RunRequest): Promise<RunProgress> {
  const response = await fetch('/api/jobs', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(request),
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    throw new Error(payload.error || `请求失败：HTTP ${response.status}`)
  }
  return response.json()
}

export async function getJob(jobId: string): Promise<RunProgress> {
  const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`)
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    throw new Error(payload.error || `请求失败：HTTP ${response.status}`)
  }
  return response.json()
}
