import { Button } from '@/components/ui/button'

// The API's page size (PAGE_SIZE in the backend settings)
export const PAGE_SIZE = 50

export function Pagination({
  page,
  count,
  hasPrevious,
  hasNext,
  onPage,
}: {
  page: number
  count: number
  hasPrevious: boolean
  hasNext: boolean
  onPage: (page: number) => void
}) {
  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE))
  if (totalPages <= 1) return null

  return (
    <nav
      aria-label="Pagination"
      className="flex items-center justify-between gap-4 border-t border-border pt-6"
    >
      <Button
        variant="outline"
        disabled={!hasPrevious}
        onClick={() => onPage(page - 1)}
      >
        Previous
      </Button>
      <span className="tabular text-sm text-muted-foreground">
        Page {page} of {totalPages}
      </span>
      <Button
        variant="outline"
        disabled={!hasNext}
        onClick={() => onPage(page + 1)}
      >
        Next
      </Button>
    </nav>
  )
}
