import { animate } from 'motion'
import { useEffect, useRef, useState } from 'react'

interface Props {
  value: number
  formatter?: (value: number) => string
}

// Counts up from the previous value to the new one whenever it changes —
// the one deliberate motion usage for this step (PHASE2.md step 5); the
// dialog/sheet/dropdown transitions already come from Base UI for free.
export function AnimatedNumber({ value, formatter = (n) => String(Math.round(n)) }: Props) {
  const [display, setDisplay] = useState(value)
  const previous = useRef(value)

  useEffect(() => {
    const from = previous.current
    const controls = animate(from, value, {
      duration: 0.5,
      ease: 'easeOut',
      onUpdate: setDisplay,
    })
    previous.current = value
    return () => controls.stop()
  }, [value])

  return <>{formatter(display)}</>
}
