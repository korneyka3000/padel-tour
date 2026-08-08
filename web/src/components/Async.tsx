/** Loading and failure, in the interface's own voice. */

import { useEffect, useState } from 'react'

interface State<T> {
  data: T | null
  error: string | null
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
        if (!live) return
        const message = error instanceof Error ? error.message : 'Что-то пошло не так'
        setState({ data: null, error: message, loading: false })
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
  return <Note title="Загружаем" />
}

/** Says what happened and what to do about it, without apologising. */
export function Failed({ message }: { message: string }) {
  return (
    <Note title="Не открылось">
      {message}. Обновите страницу или проверьте ссылку.
    </Note>
  )
}
