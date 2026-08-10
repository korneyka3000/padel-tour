/**
 * The page, when it is running inside Telegram.
 *
 * A Mini App is this same site opened in Telegram's own web view. What it gets that a
 * browser does not is `initData`: a signed statement of who is looking at it. The server
 * checks the signature — see `services/telegram_auth.py` — and that is the whole sign-in.
 * No password, no email, no mail server.
 *
 * Typed by hand rather than pulled from `@twa-dev/types`. Four fields are used and the
 * shape has been stable for years; a dependency for that is a dependency to keep updated.
 */

/** The subset of Telegram's WebApp object this page touches. */
interface TelegramWebApp {
  /** Signed, and meaningless until the server says otherwise. */
  initData: string
  /** What `?startapp=` carried, which is how a chat says "open this tournament". */
  initDataUnsafe?: { start_param?: string }
  /** Colours the client's own chrome to match the page. */
  ready: () => void
  expand: () => void
  colorScheme?: 'light' | 'dark'
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp }
  }
}

export function webApp(): TelegramWebApp | null {
  return window.Telegram?.WebApp ?? null
}

/** Are we inside Telegram, with something signed to show for it? */
export function insideTelegram(): boolean {
  const app = webApp()
  return app !== null && app.initData.length > 0
}

/**
 * Where a launch wants to go.
 *
 * `?startapp=` is the only parameter Telegram passes through, so destinations are encoded
 * into it: `t_<uuid>` for a tournament, `g_<uuid>` for a group. Anything unrecognised lands
 * on the home page rather than a broken route.
 */
export function launchDestination(param: string | undefined): string {
  if (!param) return '/'
  const [kind, ...rest] = param.split('_')
  const id = rest.join('-')
  if (kind === 't' && id) return `/t/${id}`
  if (kind === 'g' && id) return `/g/${id}`
  return '/'
}

/** Tell the client we have painted, and use the whole height while we are at it. */
export function settle(): void {
  const app = webApp()
  if (app === null) return
  app.ready()
  app.expand()
}
