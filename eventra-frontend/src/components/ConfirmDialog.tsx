import { AlertDialog } from '@base-ui/react/alert-dialog'
import { useEffect, useRef, type ReactElement, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'

// For actions that can't be undone (cancel an event, reject, settle).
// `trigger` is the button that opens it; `onConfirm` runs the action and the
// dialog stays open (showing `pending`) until the caller closes it.
export function ConfirmDialog({
  trigger,
  title,
  description,
  confirmLabel,
  destructive = false,
  pending = false,
  open,
  onOpenChange,
  onConfirm,
  children,
  confirmControl,
}: {
  trigger: ReactElement
  title: string
  description: ReactNode
  confirmLabel: string
  destructive?: boolean
  pending?: boolean
  open: boolean
  onOpenChange: (open: boolean) => void
  onConfirm: () => void
  // Extra fields, such as a rejection reason
  children?: ReactNode
  // Replaces the confirm button, e.g. with a HoldToConfirmButton
  confirmControl?: ReactNode
}) {
  // A double click lands before `pending` re-renders, so lock on the first
  // click and unlock once a render shows the action isn't running
  const locked = useRef(false)
  useEffect(() => {
    if (!pending) locked.current = false
  })
  function confirm() {
    if (locked.current || pending) return
    locked.current = true
    onConfirm()
  }

  return (
    <AlertDialog.Root open={open} onOpenChange={onOpenChange}>
      <AlertDialog.Trigger render={trigger} />
      <AlertDialog.Portal>
        <AlertDialog.Backdrop className="fixed inset-0 z-40 bg-ink/30 transition-opacity duration-200 ease-out data-ending-style:opacity-0 data-starting-style:opacity-0" />
        <AlertDialog.Popup className="fixed overscroll-contain top-1/2 left-1/2 z-50 w-[min(28rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-lg border border-border bg-card p-6 shadow-overlay transition-[opacity,scale] duration-200 ease-out data-ending-style:scale-[0.96] motion-reduce:data-starting-style:scale-100 motion-reduce:data-ending-style:scale-100 data-ending-style:opacity-0 data-starting-style:scale-[0.96] data-starting-style:opacity-0">
          <AlertDialog.Title className="font-display text-[28px] leading-tight">
            {title}
          </AlertDialog.Title>
          <AlertDialog.Description className="mt-2 text-[15px] text-muted-foreground">
            {description}
          </AlertDialog.Description>
          {children && <div className="mt-4">{children}</div>}
          <div className="mt-6 flex flex-wrap justify-end gap-2">
            <AlertDialog.Close
              render={<Button variant="ghost" />}
              disabled={pending}
            >
              Keep it
            </AlertDialog.Close>
            {confirmControl ?? (
              <Button
                variant={destructive ? 'destructive' : 'ink'}
                disabled={pending}
                onClick={confirm}
              >
                {pending ? 'Working…' : confirmLabel}
              </Button>
            )}
          </div>
        </AlertDialog.Popup>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  )
}
