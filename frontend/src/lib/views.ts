export const VIEWS = ['dashboard', 'jobs', 'questions', 'resume'] as const
export type View = (typeof VIEWS)[number]
