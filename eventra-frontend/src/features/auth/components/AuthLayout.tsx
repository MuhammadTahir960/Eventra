import type { ReactNode } from 'react'

export function AuthLayout({
  title,
  description,
  children,
  footer,
}: {
  title: string
  description?: string
  children: ReactNode
  footer?: ReactNode
}) {
  return (
    <section className="gutter mx-auto w-full max-w-[460px] pt-12 sm:pt-20">
      <h1 className="font-display text-[clamp(2.5rem,6vw,3.25rem)] leading-[1.05]">
        {title}
      </h1>
      {description && (
        <p className="mt-2 text-[15px] text-muted-foreground">{description}</p>
      )}
      <div className="mt-8 flex flex-col gap-5">{children}</div>
      {footer && (
        <p className="mt-8 border-t border-border pt-6 text-sm text-muted-foreground">
          {footer}
        </p>
      )}
    </section>
  )
}
