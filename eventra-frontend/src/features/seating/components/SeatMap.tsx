import {
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
} from 'react'
import { HugeiconsIcon } from '@hugeicons/react'
import { MinusSignIcon, PlusSignIcon } from '@hugeicons/core-free-icons'
import { Button } from '@/components/ui/button'
import { NativeSelect } from '@/components/ui/native-select'
import { formatMoney } from '@/lib/format'
import { toCents } from '@/lib/money'
import { computeLayout, SEAT_RADIUS } from '../layout/layout'
import {
  buildNavigation,
  isNavigationKey,
  moveFocus,
} from '../layout/navigation'
import { isVenueShape, type VenueShape } from '../layout/shapes'
import {
  fitBounds,
  panBox,
  zoomBox,
  zoomLevel,
  type Box,
} from '../layout/viewport'
import type { EventSeat, SeatStatus } from '../types'

interface SeatMapProps {
  seats: EventSeat[]
  // The venue's layout_shape; anything unknown is drawn as an oval
  shape: string
  selected: ReadonlySet<string>
  onToggle: (seatId: string) => void
  // True while a request is in flight: seats can't be changed
  disabled?: boolean
  // What sits in the middle of the venue
  fieldLabel?: string
}

type DisplayState = 'available' | 'selected' | 'held' | 'booked'

const STATE_TEXT: Record<DisplayState, string> = {
  available: 'available',
  selected: 'selected',
  held: 'held by another buyer',
  booked: 'sold',
}

// Tiers are told apart by warm neutral shades and their labels, never by
// extra hues, so the ember of a selected seat is the only colour on the map
const TIER_SHADES = ['#f1efe9', '#e6e2d8', '#dbd6c8', '#d0cab9', '#c5beab']
const tierShade = (index: number) => TIER_SHADES[index % TIER_SHADES.length]

// Movement below this many pixels is a tap on a seat, not a drag of the map
const DRAG_THRESHOLD_PX = 5
const ZOOM_STEP = 1.6

// What a seat looks like in each state. Colour is never the only signal:
// every state also has its own shape (outline, check, dashes, cross).
function SeatGlyph({ state }: { state: DisplayState }) {
  const r = SEAT_RADIUS - 0.6
  switch (state) {
    case 'available':
      return (
        <circle
          r={r}
          fill="var(--card)"
          stroke="var(--hairline-strong)"
          strokeWidth={1.2}
        />
      )
    case 'selected':
      return (
        <>
          <circle
            r={r}
            fill="var(--seat-selected)"
            stroke="var(--seat-selected)"
          />
          <path
            d="M-2.3 0.2 L-0.7 1.8 L2.4 -1.8"
            fill="none"
            stroke="white"
            strokeWidth={1.5}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </>
      )
    case 'held':
      return (
        <circle
          r={r}
          fill="url(#seat-hatch)"
          stroke="var(--hairline-strong)"
          strokeWidth={1.2}
          strokeDasharray="1.6 1.4"
        />
      )
    case 'booked':
      return (
        <>
          <circle r={r} fill="var(--seat-booked)" />
          <path
            d="M-1.8 -1.8 L1.8 1.8 M1.8 -1.8 L-1.8 1.8"
            stroke="var(--hairline-strong)"
            strokeWidth={1.1}
            strokeLinecap="round"
          />
        </>
      )
  }
}

export function SeatMap({
  seats,
  shape,
  selected,
  onToggle,
  disabled = false,
  fieldLabel = 'Stage',
}: SeatMapProps) {
  const resolved: VenueShape = isVenueShape(shape) ? shape : 'oval'

  // Seat positions depend only on which seats exist, not on their status, so
  // a live status change must not redo the layout of a 1,000-seat venue.
  // `structure` keeps the same array until the set of seats really changes.
  const signature = seats.map((seat) => seat.id).join('|')
  const [structure, setStructure] = useState({ signature, seats })
  if (structure.signature !== signature) setStructure({ signature, seats })

  const layout = useMemo(
    () => computeLayout(structure.seats, resolved),
    [structure, resolved],
  )
  const navigation = useMemo(
    () => buildNavigation(structure.seats),
    [structure],
  )

  const positions = useMemo(
    () => new Map(layout.seats.map((seat) => [seat.id, seat])),
    [layout.seats],
  )
  const seatsById = useMemo(
    () => new Map(seats.map((seat) => [seat.id, seat])),
    [seats],
  )

  // Tiers in price order, each with a colour; sections are tinted by tier
  const { tiers, sectionTier } = useMemo(() => {
    const byTier = new Map<
      string,
      { id: string; name: string; price: string | number }
    >()
    const forSection = new Map<string, string>()
    for (const seat of structure.seats) {
      if (!byTier.has(seat.ticket_tier)) {
        byTier.set(seat.ticket_tier, {
          id: seat.ticket_tier,
          name: seat.tier_name,
          price: seat.price,
        })
      }
      if (!forSection.has(seat.section))
        forSection.set(seat.section, seat.ticket_tier)
    }
    const ordered = [...byTier.values()].sort(
      (a, b) => toCents(a.price) - toCents(b.price),
    )
    return { tiers: ordered, sectionTier: forSection }
  }, [structure])

  // ----- zoom and pan -----
  const full: Box = layout.viewBox
  const [view, setView] = useState<Box | null>(null)
  const box = view ? panBox(full, view, 0, 0) : full
  const zoomed = zoomLevel(full, box) > 1.01

  const svgRef = useRef<SVGSVGElement>(null)
  const drag = useRef<{
    pointerId: number
    startX: number
    startY: number
    startBox: Box
    moved: boolean
  } | null>(null)
  // A drag ends with a click event; this stops it toggling the seat under it
  const suppressClick = useRef(false)

  function handlePointerDown(event: PointerEvent<SVGSVGElement>) {
    drag.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      startBox: box,
      moved: false,
    }
  }

  function handlePointerMove(event: PointerEvent<SVGSVGElement>) {
    const state = drag.current
    if (!state || state.pointerId !== event.pointerId) return
    const dx = event.clientX - state.startX
    const dy = event.clientY - state.startY
    if (!state.moved && Math.hypot(dx, dy) < DRAG_THRESHOLD_PX) return
    if (!zoomed) return

    if (!state.moved) {
      state.moved = true
      // Capture only once it is really a drag, so seat taps still work
      svgRef.current?.setPointerCapture(event.pointerId)
    }
    const width = svgRef.current?.getBoundingClientRect().width || 1
    const scale = state.startBox.width / width
    setView(panBox(full, state.startBox, -dx * scale, -dy * scale))
  }

  function handlePointerEnd(event: PointerEvent<SVGSVGElement>) {
    const state = drag.current
    if (!state || state.pointerId !== event.pointerId) return
    if (state.moved) {
      suppressClick.current = true
      // Clear after the click that follows the drag has been ignored
      setTimeout(() => {
        suppressClick.current = false
      }, 0)
    }
    drag.current = null
  }

  // ----- keyboard focus: one tab stop, arrows move between seats -----
  const [focusId, setFocusId] = useState<string | null>(null)
  const tabStop = focusId && positions.has(focusId) ? focusId : navigation.first

  function describe(seat: EventSeat, state: DisplayState): string {
    return `Section ${seat.section}, row ${seat.row_label}, seat ${seat.seat_number}, ${seat.tier_name}, ${formatMoney(seat.price)}, ${STATE_TEXT[state]}`
  }

  function stateOf(seat: EventSeat): DisplayState {
    if (selected.has(seat.id) && seat.status === 'available') return 'selected'
    return seat.status satisfies SeatStatus
  }

  function activate(seat: EventSeat) {
    if (disabled || suppressClick.current) return
    if (seat.status === 'available') onToggle(seat.id)
  }

  function handleKeyDown(event: KeyboardEvent<SVGGElement>, seat: EventSeat) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      activate(seat)
      return
    }
    if (!isNavigationKey(event.key)) return
    event.preventDefault()
    const next = moveFocus(navigation, seat.id, event.key)
    setFocusId(next)
    document.getElementById(`seat-${next}`)?.focus()
  }

  // If keyboard focus lands on a seat outside the zoomed view, bring it in
  function handleFocus(seatId: string) {
    setFocusId(seatId)
    const p = positions.get(seatId)
    if (!p || !zoomed) return
    const outside =
      p.x < box.x ||
      p.x > box.x + box.width ||
      p.y < box.y ||
      p.y > box.y + box.height
    if (outside) {
      setView(
        panBox(
          full,
          box,
          p.x - (box.x + box.width / 2),
          p.y - (box.y + box.height / 2),
        ),
      )
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="outline"
          size="icon-sm"
          onClick={() => setView(zoomBox(full, box, ZOOM_STEP))}
          aria-label="Zoom in"
        >
          <HugeiconsIcon icon={PlusSignIcon} size={16} />
        </Button>
        <Button
          variant="outline"
          size="icon-sm"
          onClick={() => setView(zoomBox(full, box, 1 / ZOOM_STEP))}
          aria-label="Zoom out"
        >
          <HugeiconsIcon icon={MinusSignIcon} size={16} />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setView(null)}
          disabled={!zoomed}
        >
          Whole venue
        </Button>
        <div className="ml-auto">
          <label htmlFor="zoom-section" className="sr-only">
            Zoom to section
          </label>
          <NativeSelect
            id="zoom-section"
            className="h-8 rounded-full text-sm"
            value=""
            onChange={(event) => {
              const section = layout.sections.find(
                (s) => s.name === event.target.value,
              )
              setView(section ? fitBounds(full, section.bounds) : null)
            }}
          >
            <option value="">Zoom to section…</option>
            {layout.sections.map((section) => (
              <option key={section.name} value={section.name}>
                Section {section.name}
              </option>
            ))}
          </NativeSelect>
        </div>
      </div>

      <svg
        ref={svgRef}
        viewBox={`${box.x} ${box.y} ${box.width} ${box.height}`}
        role="group"
        aria-label="Seat map. Use the arrow keys to move between seats and Enter to select."
        className="h-auto max-h-[70vh] w-full rounded-lg border border-border bg-card select-none"
        // Let the page scroll normally until the map is zoomed in
        style={{ touchAction: zoomed ? 'none' : 'pan-y' }}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerEnd}
        onPointerCancel={handlePointerEnd}
      >
        <defs>
          <pattern
            id="seat-hatch"
            width="2.4"
            height="2.4"
            patternUnits="userSpaceOnUse"
            patternTransform="rotate(45)"
          >
            <rect width="2.4" height="2.4" fill="var(--card)" />
            <line y2="2.4" stroke="var(--hairline-strong)" strokeWidth="1" />
          </pattern>
        </defs>
        <path
          d={layout.fieldPath}
          className="fill-muted stroke-hairline-strong"
          strokeWidth={1.5}
        />
        <text
          x={layout.fieldLabel.x}
          y={layout.fieldLabel.y}
          textAnchor="middle"
          dominantBaseline="middle"
          fontSize={13}
          letterSpacing={2}
          className="fill-muted-foreground"
        >
          {fieldLabel.toUpperCase()}
        </text>

        {layout.sections.map((section) => {
          const tierId = sectionTier.get(section.name)
          const tierIndex = tiers.findIndex((tier) => tier.id === tierId)
          return (
            <g key={section.name}>
              <path
                d={section.path}
                className="stroke-border"
                strokeWidth={1}
                style={{
                  fill: tierIndex >= 0 ? tierShade(tierIndex) : 'var(--muted)',
                  fillOpacity: 0.55,
                }}
              />
              <text
                x={section.labelX}
                y={section.labelY}
                textAnchor="middle"
                dominantBaseline="middle"
                fontSize={11}
                fontWeight={500}
                className="fill-muted-foreground"
                aria-hidden="true"
              >
                {section.name}
              </text>
            </g>
          )
        })}

        {layout.seats.map((position) => {
          const seat = seatsById.get(position.id)
          if (!seat) return null
          const state = stateOf(seat)
          const selectable = seat.status === 'available'
          return (
            <g
              key={seat.id}
              id={`seat-${seat.id}`}
              transform={`translate(${position.x} ${position.y})`}
              role="button"
              tabIndex={seat.id === tabStop ? 0 : -1}
              aria-label={describe(seat, state)}
              aria-pressed={selectable ? state === 'selected' : undefined}
              aria-disabled={!selectable || disabled}
              onClick={() => activate(seat)}
              onKeyDown={(event) => handleKeyDown(event, seat)}
              onFocus={() => handleFocus(seat.id)}
              className={`outline-none focus-visible:[&_.seat-ring]:opacity-100 ${
                selectable && !disabled
                  ? 'cursor-pointer'
                  : 'cursor-not-allowed'
              }`}
            >
              {/* Larger invisible target so small seats are easy to hit */}
              <circle r={SEAT_RADIUS + 2} fill="transparent" />
              <circle
                className="seat-ring opacity-0"
                r={SEAT_RADIUS + 1.6}
                fill="none"
                stroke="var(--ring)"
                strokeWidth={1.6}
              />
              {/* The pop on select scales the glyph about its own centre */}
              <g
                className="transition-transform duration-160 ease-out motion-reduce:transition-none [transform-box:fill-box] [transform-origin:center]"
                style={{
                  transform: state === 'selected' ? 'scale(1.12)' : undefined,
                }}
              >
                <SeatGlyph state={state} />
              </g>
            </g>
          )
        })}
      </svg>

      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 text-[13px] text-muted-foreground">
        <ul aria-label="Seat states" className="flex flex-wrap gap-x-4 gap-y-1">
          {(['available', 'selected', 'held', 'booked'] as const).map(
            (state) => (
              <li key={state} className="flex items-center gap-1.5">
                <svg
                  width="16"
                  height="16"
                  viewBox="-8 -8 16 16"
                  aria-hidden="true"
                >
                  <SeatGlyph state={state} />
                </svg>
                {state === 'booked'
                  ? 'Sold'
                  : state === 'held'
                    ? 'On hold'
                    : state === 'selected'
                      ? 'Your pick'
                      : 'Available'}
              </li>
            ),
          )}
        </ul>
        <ul
          aria-label="Ticket tiers"
          className="flex flex-wrap gap-x-4 gap-y-1"
        >
          {tiers.map((tier, index) => (
            <li key={tier.id} className="flex items-center gap-1.5">
              <span
                aria-hidden="true"
                className="size-3 rounded-sm border border-hairline-strong"
                style={{ background: tierShade(index) }}
              />
              <span className="text-foreground">{tier.name}</span>{' '}
              <span className="tabular">{formatMoney(tier.price)}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
