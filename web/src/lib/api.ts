/** The API, typed to match the Pydantic schemas it answers with. */

export type Format = 'americano' | 'mexicano'
export type PairingPattern = 'crossover' | 'split' | 'top_heavy'

export interface Player {
  id: string
  name: string
  is_active: boolean
  /** Whether a real account holds this name. Unclaimed players are the normal case. */
  is_claimed: boolean
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
  /** The same four by id. Names cannot answer "am I on this court" — namesakes are legal. */
  team_a_ids: [string, string]
  team_b_ids: [string, string]
}

/**
 * Where you stand in one tournament.
 *
 * The inputs to the server's rule rather than its verdict, so the screen can apply the same
 * rule instead of keeping a second copy of it that drifts. See `canScore` below.
 */
export interface Viewer {
  is_member: boolean
  is_organiser: boolean
  /** The player you are in this tournament, if you have claimed one. */
  plays_as: string | null
  /** Nobody organises it, so the group scores it between them. */
  anyone_may_score: boolean
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
  viewer: Viewer
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
  /** Which group, filled in only for lists that span more than one. */
  group_name: string | null
  /** Where you finished. Only on your own history, and null if it is unplayed. */
  my_rank: number | null
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
    /** The server's machine-readable name for this refusal. Empty if it did not say. */
    readonly code = '',
    /** The values its sentence was built from, so a translation can place them itself. */
    readonly params: Record<string, unknown> = {},
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

type Method = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

interface ErrorBody {
  detail?: string
  code?: string
  params?: Record<string, unknown>
}

/** Answers null for 204 — an idle group is not an error, it is just not playing. */
/**
 * One request, with the verb inferred when it is not given.
 *
 * That inference is a trap and has sprung twice: a POST that needs no body arrives as a GET
 * and the server answers 405. `invite` and `signOut` were both wrong this way, and three
 * other calls pass `{}` as a body they do not have purely to force the verb. Pass `method`
 * explicitly for anything that writes — `tests/api/test_client_contract.py` checks every
 * call here against the routes the API actually declares.
 */
async function request<T>(path: string, body?: unknown, method?: Method): Promise<T | null> {
  const response = await fetch(`/api${path}`, {
    method: method ?? (body === undefined ? 'GET' : 'POST'),
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
    // The body is the interesting part of a refusal, and it may not be there at all — a
    // gateway timing out answers HTML, or nothing.
    const body = await response
      .json()
      .then((parsed: ErrorBody) => parsed)
      .catch(() => ({}) as ErrorBody)
    throw new ApiError(
      response.status,
      body.detail ?? `request failed (${response.status})`,
      body.code ?? '',
      body.params ?? {},
    )
  }

  return (await response.json()) as T
}

async function required<T>(path: string, body?: unknown, method?: Method): Promise<T> {
  const answer = await request<T>(path, body, method)
  if (answer === null) throw new ApiError(204, 'empty response')
  return answer
}

export interface Draw {
  player_ids: string[]
  format: Format
  points_per_match: number
  pairing_pattern: PairingPattern
  rounds: number | null
}

export const api = {
  groups: () => required<Group[]>('/groups'),
  group: (id: string) => required<GroupDetail>(`/groups/${id}`),
  archive: (id: string) => required<TournamentCard[]>(`/groups/${id}/tournaments`),
  active: (id: string) => request<Tournament>(`/groups/${id}/active`),
  tournament: (id: string) => required<Tournament>(`/tournaments/${id}`),
  player: (id: string) => required<PlayerProfile>(`/players/${id}`),

  me: () => required<Me>('/auth/me'),
  myTournaments: () => required<TournamentCard[]>('/me/tournaments'),
  askForLink: (email: string) => request<unknown>('/auth/magic-link', { email }),
  enter: (token: string) => required<Me>('/auth/enter', { token }),
  enterFromTelegram: (initData: string) =>
    required<Me>('/auth/telegram', { init_data: initData }),
  signOut: () => request<unknown>('/auth/sign-out', undefined, 'POST'),

  invitation: (token: string) => required<Player>(`/invites/${token}`),
  acceptInvitation: (token: string) => required<Player>('/invites/redeem', { token }),
  invite: (playerId: string) =>
    required<Invitation>(`/players/${playerId}/invite`, undefined, 'POST'),

  createGroup: (name: string) => required<Group>('/groups', { name }),
  addPlayer: (groupId: string, name: string) =>
    required<GroupDetail>(`/groups/${groupId}/players`, { name }),
  renamePlayer: (playerId: string, name: string) =>
    required<Player>(`/players/${playerId}`, { name }, 'PATCH'),
  removePlayer: (playerId: string) => request<null>(`/players/${playerId}`, undefined, 'DELETE'),

  draw: (groupId: string, body: Draw) =>
    required<Tournament>(`/groups/${groupId}/tournaments`, body),
  reroll: (id: string) => required<Tournament>(`/tournaments/${id}/reroll`, {}),
  putScore: (id: string, round: number, court: number, scoreA: number, scoreB: number) =>
    required<Tournament>(
      `/tournaments/${id}/rounds/${round}/courts/${court}`,
      { score_a: scoreA, score_b: scoreB },
      'PUT',
    ),
  nextRound: (id: string) => required<Tournament>(`/tournaments/${id}/next-round`, {}),
  finish: (id: string) => required<Tournament>(`/tournaments/${id}/finish`, {}),
}

/**
 * May this viewer enter the score for this match?
 *
 * Deliberately the same shape as `require_can_score` on the server, read in the same order.
 * The last branch is the subtle one: an account that has claimed no player here cannot be
 * told apart from a bystander, and refusing everyone would lock out a group where nobody
 * has accepted an invitation yet.
 */
export function canScore(viewer: Viewer, match: Match): boolean {
  if (!viewer.is_member) return false
  if (viewer.is_organiser || viewer.anyone_may_score) return true
  if (viewer.plays_as === null) return true
  return [...match.team_a_ids, ...match.team_b_ids].includes(viewer.plays_as)
}
