export const VIEWS = [
  'dashboard',
  'jobs',
  'questions',
  'resume',
  'companies',
  'profile',
  'applications',
] as const
export type View = (typeof VIEWS)[number]
