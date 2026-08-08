/** The API, typed to match the Pydantic schemas it answers with. */

export type Format = 'americano' | 'mexicano'
export type PairingPattern = 'crossover' | 'split' | 'top_heavy'

export interface Player {
  id: string
  name: string
  is_active: boolean
}

export interface Group {
  id: string
  name: string
  player_count: number
}

export interface GroupDetail {
  id: string
  name: string
  players: Player[]
  /** Whether you keep this roster. Controls that would be refused are not shown. */
  is_owner: boolean
}

export interface Match {
  court: number
  team_a: [string, string]
  team_b: [string, string]
  score_a: number | null
  score_b: number | null
}

export interface Round {
  number: number
  matches: Match[]
  complete: boolean
}

export interface Standing {
  rank: number
  player_id: string
  name: string
  played: number
  wins: number
  draws: number
  losses: number
  points_for: number
  points_against: number
  diff: number
}

export interface ProgressPoint {
  round_no: number
  points_for: number
  cumulative_points: number
  rank: number
}

export interface PlayerProgress {
  player_id: string
  name: string
  points: ProgressPoint[]
}

export interface Tournament {
  id: string
  group_id: string
  format: Format
  points_per_match: number
  pairing_pattern: PairingPattern
  total_rounds: number
  rounds_played: number
  finished: boolean
  created_at: string
  finished_at: string | null
  rounds: Round[]
  standings: Standing[]
  progression: PlayerProgress[]
}

export interface TournamentCard {
  id: string
  format: Format
  finished: boolean
  player_count: number
  rounds_played: number
  total_rounds: number
  created_at: string
  winner_name: string | null
}

export interface PlayerProfile {
  id: string
  name: string
  tournaments: number
  matches: number
  wins: number
  points_for: number
  average_points: number
  best_rank: number | null
  podiums: number
  history: TournamentCard[]
}

export interface Me {
  id: string
  display_name: string | null
  groups: Group[]
}

export interface Invitation {
  token: string
  player: Player
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

/** Answers null for 204 — an idle group is not an error, it is just not playing. */
async function request<T>(path: string, body?: unknown): Promise<T | null> {
  const response = await fetch(`/api${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    // The session lives in a cookie the script cannot read, so it has to be sent rather
    // than attached. Same-origin in production; explicit here because the dev server is not.
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  if (response.status === 204) return null

  if (!response.ok) {
    const detail = await response
      .json()
      .then((body: { detail?: string }) => body.detail)
      .catch(() => undefined)
    throw new ApiError(response.status, detail ?? `Запрос не прошёл (${response.status})`)
  }

  return (await response.json()) as T
}

async function required<T>(path: string, body?: unknown): Promise<T> {
  const answer = await request<T>(path, body)
  if (answer === null) throw new ApiError(204, 'Пусто')
  return answer
}

export const api = {
  groups: () => required<Group[]>('/groups'),
  group: (id: string) => required<GroupDetail>(`/groups/${id}`),
  archive: (id: string) => required<TournamentCard[]>(`/groups/${id}/tournaments`),
  active: (id: string) => request<Tournament>(`/groups/${id}/active`),
  tournament: (id: string) => required<Tournament>(`/tournaments/${id}`),
  player: (id: string) => required<PlayerProfile>(`/players/${id}`),

  me: () => required<Me>('/auth/me'),
  askForLink: (email: string) => request<unknown>('/auth/magic-link', { email }),
  enter: (token: string) => required<Me>('/auth/enter', { token }),
  signOut: () => request<unknown>('/auth/sign-out'),

  invitation: (token: string) => required<Player>(`/invites/${token}`),
  acceptInvitation: (token: string) => required<Player>('/invites/redeem', { token }),
  invite: (playerId: string) => required<Invitation>(`/players/${playerId}/invite`),

  createGroup: (name: string) => required<Group>('/groups', { name }),
  addPlayer: (groupId: string, name: string) =>
    required<GroupDetail>(`/groups/${groupId}/players`, { name }),
}

export const FORMAT_LABEL: Record<Format, string> = {
  americano: 'Американо',
  mexicano: 'Мексикано',
}

/** Russian noun agreement, including the teens exception. */
export function plural(count: number, one: string, few: string, many: string): string {
  const lastTwo = count % 100
  const last = count % 10
  if (last === 1 && lastTwo !== 11) return one
  if (last >= 2 && last <= 4 && (lastTwo < 12 || lastTwo > 14)) return few
  return many
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'long',
  })
}
