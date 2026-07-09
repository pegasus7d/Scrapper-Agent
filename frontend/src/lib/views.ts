export const VIEWS = ['dashboard', 'jobs', 'questions'] as const
export type View = (typeof VIEWS)[number]
