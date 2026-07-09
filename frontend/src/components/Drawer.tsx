import type { ReactNode } from 'react'

import { Sheet, SheetContent, SheetHeader, SheetTitle } from './ui/sheet'

interface Props {
  title: string
  onClose: () => void
  children: ReactNode
}

export function Drawer({ title, onClose, children }: Props) {
  return (
    <Sheet open onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="overflow-y-auto">
        <SheetHeader>
          <SheetTitle>{title}</SheetTitle>
        </SheetHeader>
        <div className="px-4 pb-4">{children}</div>
      </SheetContent>
    </Sheet>
  )
}
