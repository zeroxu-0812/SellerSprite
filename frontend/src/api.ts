import type { AdminLoginResponse, RunProgress, RunRequest, UsageResponse } from './types'

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

async function responseError(response: Response): Promise<ApiError> {
  const payload = await response.json().catch(() => ({}))
  return new ApiError(response.status, payload.error || `请求失败：HTTP ${response.status}`)
}

export async function loginAdmin(username: string, password: string): Promise<AdminLoginResponse> {
  const response = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  if (!response.ok) throw await responseError(response)
  return response.json()
}

export async function createJob(request: RunRequest): Promise<RunProgress> {
  const response = await fetch('/api/jobs', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(request),
  })
  if (!response.ok) throw await responseError(response)
  return response.json()
}

export async function getJob(jobId: string): Promise<RunProgress> {
  const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`)
  if (!response.ok) throw await responseError(response)
  return response.json()
}

export async function getUsage(token: string): Promise<UsageResponse> {
  const response = await fetch('/api/usage', {
    headers: { authorization: `Bearer ${token}` },
  })
  if (!response.ok) throw await responseError(response)
  return response.json()
}
