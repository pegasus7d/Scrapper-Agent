import { useEffect, useRef, useState } from 'react'

interface Props {
  value: number
  formatter?: (value: number) => string
}

const DURATION_MS = 500

// Counts up from the previous value to the new one whenever it changes —
// hand-rolled requestAnimationFrame tween instead of pulling in `motion`
// for one simple numeric animation (PHASE5.md step 4: `motion` pulled in
// the full framer-motion/dom build, including gesture/layout/SVG-path
// engines this app never touched, for exactly this one call). The
// dialog/sheet/dropdown transitions already come from Base UI for free.
export function AnimatedNumber({ value, formatter = (n) => String(Math.round(n)) }: Props) {
  const [display, setDisplay] = useState(value)
  const previous = useRef(value)

  useEffect(() => {
    const from = previous.current
    const to = value
    const start = performance.now()
    let frame: number

    function tick(now: number) {
      const t = Math.min((now - start) / DURATION_MS, 1)
      const eased = 1 - (1 - t) ** 3 // cubic ease-out, matches the old `ease: 'easeOut'`
      setDisplay(from + (to - from) * eased)
      if (t < 1) frame = requestAnimationFrame(tick)
    }

    frame = requestAnimationFrame(tick)
    previous.current = value
    return () => cancelAnimationFrame(frame)
  }, [value])

  return <>{formatter(display)}</>
}
