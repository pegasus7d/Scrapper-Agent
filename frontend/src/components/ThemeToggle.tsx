import { Moon, Sun } from 'lucide-react'

import { useTheme } from '../hooks/useTheme'
import { Button } from './ui/button'

export function ThemeToggle() {
  const [theme, toggle] = useTheme()

  return (
    <Button variant="ghost" size="icon-sm" onClick={toggle} aria-label="Toggle theme">
      {theme === 'dark' ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </Button>
  )
}
