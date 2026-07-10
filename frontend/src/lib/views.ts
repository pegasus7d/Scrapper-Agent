export const VIEWS = ['dashboard', 'jobs', 'questions', 'resume', 'companies', 'profile'] as const
export type View = (typeof VIEWS)[number]
