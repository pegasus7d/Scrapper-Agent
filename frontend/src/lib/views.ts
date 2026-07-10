export const VIEWS = ['dashboard', 'jobs', 'questions', 'resume', 'companies'] as const
export type View = (typeof VIEWS)[number]
