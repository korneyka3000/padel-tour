/** Loading and failure, in the interface's own voice. */

import { useEffect, useState } from 'react'

import { useT } from './Locale'

interface State<T> {
  data: T | null
  /**
   * The failure itself, not a message.
   *
   * Flattening it to a string here would throw away the error code, and the code is the
   * only thing a translation can work from — the sentence is English and rewordable.
   */
  error: unknown
  loading: boolean
}

export function useAsync<T>(load: () => Promise<T>, deps: unknown[]): State<T> {
  const [state, setState] = useState<State<T>>({ data: null, error: null, loading: true })

  useEffect(() => {
    let live = true
    setState({ data: null, error: null, loading: true })

    load()
      .then((data) => {
        if (live) setState({ data, error: null, loading: false })
      })
      .catch((error: unknown) => {
        if (live) setState({ data: null, error, loading: false })
      })

    return () => {
      live = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return state
}

export function Note({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <p className="note">
      <strong>{title}</strong>
      {children}
    </p>
  )
}

export function Loading() {
  const t = useT()
  return <Note title={t('async.loading')} />
}

/** Says what happened and what to do about it, without apologising. */
export function Failed({ failure }: { failure: unknown }) {
  const t = useT()
  return (
    <Note title={t('async.failedTitle')}>
      {t('async.failedBody', { message: t.say(failure) })}
    </Note>
  )
}
