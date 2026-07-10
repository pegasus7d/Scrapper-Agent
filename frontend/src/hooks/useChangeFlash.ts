import { useEffect, useRef, useState } from 'react'

const FLASH_MS = 600

// True for a brief window right after `value` changes — a hand-rolled
// setTimeout toggle, not an animation library (frontend/CLAUDE.md, same
// reasoning as AnimatedNumber.tsx: one CSS transition doesn't justify a
// dependency). Consumers pair this with a Tailwind `transition-colors`
// class so the flash fades out smoothly instead of snapping.
export function useChangeFlash(value: number): boolean {
  const [flashing, setFlashing] = useState(false)
  const previous = useRef(value)

  useEffect(() => {
    if (previous.current === value) return
    previous.current = value
    setFlashing(true)
    const timer = setTimeout(() => setFlashing(false), FLASH_MS)
    return () => clearTimeout(timer)
  }, [value])

  return flashing
}
