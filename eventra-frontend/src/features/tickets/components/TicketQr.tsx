import QRCode from 'qrcode'
import { useEffect, useState } from 'react'

// The same payload as the PDF's QR code: the ticket code on its own
export function TicketQr({
  code,
  size = 176,
}: {
  code: string
  size?: number
}) {
  const [src, setSrc] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    QRCode.toDataURL(code, {
      margin: 0,
      // Rendered at 3x so it stays sharp on high-density phone screens
      width: size * 3,
      errorCorrectionLevel: 'M',
      color: { dark: '#141413', light: '#ffffff' },
    })
      .then((url) => !cancelled && setSrc(url))
      .catch(() => !cancelled && setSrc(null))
    return () => {
      cancelled = true
    }
  }, [code, size])

  return src ? (
    <img
      src={src}
      width={size}
      height={size}
      alt={`QR code for ticket ${code}`}
    />
  ) : (
    <div
      aria-hidden
      className="animate-pulse rounded bg-muted"
      style={{ width: size, height: size }}
    />
  )
}
