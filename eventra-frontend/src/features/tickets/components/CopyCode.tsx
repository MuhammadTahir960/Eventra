import { HugeiconsIcon } from '@hugeicons/react'
import { Copy01Icon, Tick02Icon } from '@hugeicons/core-free-icons'
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { SwapLabel } from '@/components/SwapLabel'
import { Button } from '@/components/ui/button'

// The ticket code with a copy button. Clipboard writes can be refused (old
// browsers, some in-app views); then the code is selected for a manual copy.
export function CopyCode({ code }: { code: string }) {
  const [copied, setCopied] = useState(false)
  const codeRef = useRef<HTMLSpanElement>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  useEffect(() => () => clearTimeout(timer.current), [])

  async function copy() {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
      toast.success('Ticket code copied')
      clearTimeout(timer.current)
      timer.current = setTimeout(() => setCopied(false), 2000)
    } catch {
      const node = codeRef.current
      if (!node) return
      const range = document.createRange()
      range.selectNodeContents(node)
      const selection = window.getSelection()
      selection?.removeAllRanges()
      selection?.addRange(range)
      toast('Code selected. Copy it with Ctrl+C or ⌘C.')
    }
  }

  return (
    <div className="flex items-center gap-1.5">
      <span
        ref={codeRef}
        translate="no"
        className="tabular text-sm font-medium tracking-wide select-all"
      >
        {code}
      </span>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => void copy()}
        aria-label={copied ? 'Ticket code copied' : 'Copy ticket code'}
      >
        <SwapLabel swapKey={copied ? 'copied' : 'copy'}>
          <HugeiconsIcon
            icon={copied ? Tick02Icon : Copy01Icon}
            size={15}
            aria-hidden
          />
          {copied ? 'Copied' : 'Copy'}
        </SwapLabel>
      </Button>
    </div>
  )
}
