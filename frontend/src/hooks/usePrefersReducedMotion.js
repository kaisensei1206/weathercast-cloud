import { useEffect, useState } from 'react'

const QUERY = '(prefers-reduced-motion: reduce)'

function getMediaQuery() {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia(QUERY)
    : null
}

/** 使用者是否在系統設定「減少動態效果」；設定改變時會跟著更新。不支援 matchMedia 時當作 false。 */
export function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(() => getMediaQuery()?.matches ?? false)

  useEffect(() => {
    const mediaQuery = getMediaQuery()
    if (!mediaQuery) return undefined
    const onChange = () => setReduced(mediaQuery.matches)
    onChange()
    mediaQuery.addEventListener?.('change', onChange)
    return () => mediaQuery.removeEventListener?.('change', onChange)
  }, [])

  return reduced
}
