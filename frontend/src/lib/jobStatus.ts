// Mirrors JOB_STATUSES in backend/db/models.py (PHASE8.md step 2).
export const JOB_STATUSES = ['none', 'applied', 'interviewing', 'offer', 'rejected'] as const
export type JobStatus = (typeof JOB_STATUSES)[number]

export function statusLabel(status: string): string {
  return status === 'none' ? 'not applied' : status
}
