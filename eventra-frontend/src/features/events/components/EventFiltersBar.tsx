import { HugeiconsIcon } from '@hugeicons/react'
import { ArrowDown01Icon, Search01Icon } from '@hugeicons/core-free-icons'
import type { FormEvent, ReactNode } from 'react'
import type { Category } from '@/features/catalog/types'
import { cn } from '@/lib/utils'
import {
  DEFAULT_FILTERS,
  type EventDates,
  type EventFilters,
  type EventWhen,
} from '../filters'

interface EventFiltersBarProps {
  filters: EventFilters
  categories: Category[]
  cities: string[]
  autoFocusSearch?: boolean
  // Called with only the fields that changed; the page resets to 1
  onChange: (changes: Partial<EventFilters>) => void
}

const WHEN_OPTIONS: { value: EventWhen; label: string }[] = [
  { value: 'upcoming', label: 'Upcoming' },
  { value: 'past', label: 'Past' },
]

// A native <select> styled as a pill: real keyboard support and the phone's
// own picker sheet, with no extra JavaScript.
function PillSelect({
  id,
  label,
  value,
  onChange,
  children,
}: {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  children: ReactNode
}) {
  return (
    <div className="relative shrink-0">
      <label htmlFor={id} className="sr-only">
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className={cn(
          'h-9 max-w-56 truncate appearance-none rounded-full border pr-8 pl-3.5 text-sm outline-none transition-colors focus-visible:border-ring',
          value
            ? 'border-ink bg-ink text-paper'
            : 'border-hairline-strong bg-card text-foreground hover:bg-muted',
        )}
      >
        {children}
      </select>
      <HugeiconsIcon
        icon={ArrowDown01Icon}
        size={14}
        aria-hidden
        className={cn(
          'pointer-events-none absolute top-1/2 right-3 -translate-y-1/2',
          value ? 'text-paper' : 'text-muted-foreground',
        )}
      />
    </div>
  )
}

export function EventFiltersBar({
  filters,
  categories,
  cities,
  autoFocusSearch = false,
  onChange,
}: EventFiltersBarProps) {
  function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const value = new FormData(event.currentTarget).get('q')
    onChange({ search: typeof value === 'string' ? value.trim() : '' })
  }

  const hasFilters =
    filters.search ||
    filters.category ||
    filters.city ||
    filters.type ||
    filters.dates

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div
          role="group"
          aria-label="Show events"
          className="inline-flex w-fit rounded-full border border-border bg-card p-1"
        >
          {WHEN_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              aria-pressed={filters.when === option.value}
              onClick={() => onChange({ when: option.value, dates: '' })}
              className={cn(
                'h-8 rounded-full px-4 text-sm transition-colors',
                filters.when === option.value
                  ? 'bg-ink text-paper'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {option.label}
            </button>
          ))}
        </div>

        {/* key remounts the field when the URL changes the search from outside */}
        <form
          role="search"
          key={filters.search}
          onSubmit={handleSearch}
          className="relative w-full sm:w-80"
        >
          <label htmlFor="event-search" className="sr-only">
            Search events
          </label>
          <HugeiconsIcon
            icon={Search01Icon}
            size={16}
            aria-hidden
            className="pointer-events-none absolute top-1/2 left-3.5 -translate-y-1/2 text-muted-foreground"
          />
          <input
            id="event-search"
            name="q"
            type="search"
            defaultValue={filters.search}
            placeholder="Search events, venues, teams…"
            maxLength={100}
            autoComplete="off"
            autoFocus={autoFocusSearch}
            className="h-10 w-full rounded-full border border-hairline-strong bg-card pr-4 pl-10 text-[15px] outline-none placeholder:text-muted-foreground focus-visible:border-ring"
          />
        </form>
      </div>

      {/* Scrolls sideways on phones instead of wrapping into a tall block */}
      <div className="-mx-4 flex items-center gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:flex-wrap sm:px-0">
        <PillSelect
          id="filter-category"
          label="Category"
          value={filters.category}
          onChange={(category) => onChange({ category })}
        >
          <option value="">All categories</option>
          {categories.map((category) => (
            <option key={category.id} value={category.id}>
              {category.name}
            </option>
          ))}
        </PillSelect>

        {filters.when === 'upcoming' && (
          <PillSelect
            id="filter-dates"
            label="Dates"
            value={filters.dates}
            onChange={(dates) => onChange({ dates: dates as EventDates })}
          >
            <option value="">Any date</option>
            <option value="weekend">This weekend</option>
            <option value="week">Next 7 days</option>
            <option value="month">Next 30 days</option>
          </PillSelect>
        )}

        <PillSelect
          id="filter-city"
          label="City"
          value={filters.city}
          onChange={(city) => onChange({ city })}
        >
          <option value="">All cities</option>
          {cities.map((city) => (
            <option key={city} value={city}>
              {city}
            </option>
          ))}
        </PillSelect>

        <PillSelect
          id="filter-type"
          label="Type"
          value={filters.type}
          onChange={(type) => onChange({ type: type as EventFilters['type'] })}
        >
          <option value="">Events and matches</option>
          <option value="general">Events only</option>
          <option value="sports_match">Sports matches</option>
        </PillSelect>

        {hasFilters && (
          <button
            type="button"
            className="h-9 shrink-0 rounded-full px-3 text-sm text-ember-deep underline-offset-4 hover:underline"
            onClick={() =>
              onChange({
                search: DEFAULT_FILTERS.search,
                category: DEFAULT_FILTERS.category,
                city: DEFAULT_FILTERS.city,
                type: DEFAULT_FILTERS.type,
                dates: DEFAULT_FILTERS.dates,
              })
            }
          >
            Clear filters
          </button>
        )}
      </div>
    </div>
  )
}
