import { useMemo, type KeyboardEvent } from 'react'
import {
  computeLayout,
  SEAT_RADIUS,
  type LayoutSeatInput,
} from '../layout/layout'
import { isVenueShape, type VenueShape } from '../layout/shapes'
import { summarizeSections } from '../layout/summary'

interface VenueMapPreviewProps {
  // The venue's reusable seat template
  seats: LayoutSeatInput[]
  // The venue's layout_shape from the API; anything unknown becomes an oval
  shape: string
  // Optional colour per section name (used once tiers are assigned)
  sectionColors?: Record<string, string>
  // Makes sections clickable (and keyboard-operable), e.g. to assign a tier
  onSectionSelect?: (section: string) => void
  // Extra words announced with each section, e.g. "VIP tier"
  sectionHints?: Record<string, string>
  // The text table of sections under the map (hide it if the page has its own)
  showTable?: boolean
}

const SHAPE_LABEL: Record<VenueShape, string> = {
  oval: 'oval',
  circle: 'circular',
  rectangle: 'rectangular',
  u_shape: 'U-shaped',
  semicircle: 'semicircular',
}

// Read-only top-down view of a venue, drawn from its seat template.
// Shown while someone creates an event, so they see the venue they picked.
export function VenueMapPreview({
  seats,
  shape,
  sectionColors,
  onSectionSelect,
  sectionHints,
  showTable = true,
}: VenueMapPreviewProps) {
  const resolved: VenueShape = isVenueShape(shape) ? shape : 'oval'
  const layout = useMemo(
    () => computeLayout(seats, resolved),
    [seats, resolved],
  )
  const summary = useMemo(() => summarizeSections(seats), [seats])

  const { viewBox } = layout
  const seatsById = useMemo(
    () => new Map(layout.seats.map((seat) => [seat.id, seat])),
    [layout.seats],
  )

  return (
    <div className="space-y-4">
      <svg
        viewBox={`${viewBox.x} ${viewBox.y} ${viewBox.width} ${viewBox.height}`}
        role={onSectionSelect ? 'group' : 'img'}
        aria-label={`Top-down map of a ${SHAPE_LABEL[resolved]} venue with ${seats.length} seats in ${summary.length} sections`}
        className="mx-auto h-auto max-h-[70vh] w-full rounded-lg border border-border bg-card"
      >
        <path
          d={layout.fieldPath}
          className="fill-muted stroke-hairline-strong"
          strokeWidth={2}
        />
        <text
          x={layout.fieldLabel.x}
          y={layout.fieldLabel.y}
          textAnchor="middle"
          dominantBaseline="middle"
          fontSize={12}
          letterSpacing={2}
          className="fill-muted-foreground"
        >
          STAGE / PITCH
        </text>

        {layout.sections.map((section) => {
          const color = sectionColors?.[section.name]
          return (
            <g
              key={section.name}
              {...(onSectionSelect
                ? {
                    role: 'button',
                    tabIndex: 0,
                    'aria-label': `Section ${section.name}${
                      sectionHints?.[section.name]
                        ? `, ${sectionHints[section.name]}`
                        : ''
                    }`,
                    onClick: () => onSectionSelect(section.name),
                    onKeyDown: (event: KeyboardEvent<SVGGElement>) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault()
                        onSectionSelect(section.name)
                      }
                    },
                    className:
                      'cursor-pointer outline-none focus-visible:[&_path]:stroke-ring focus-visible:[&_path]:stroke-[3]',
                  }
                : {})}
            >
              <path
                d={section.path}
                className="stroke-border"
                strokeWidth={1}
                style={{
                  fill: color ?? 'var(--muted)',
                  fillOpacity: color ? 0.2 : 0.5,
                }}
              />
              <g
                style={{
                  fill: color ?? 'var(--muted-foreground)',
                  opacity: 0.85,
                }}
              >
                {section.seatIds.map((id) => {
                  const seat = seatsById.get(id)
                  return seat ? (
                    <circle
                      key={id}
                      cx={seat.x}
                      cy={seat.y}
                      r={SEAT_RADIUS - 1}
                    />
                  ) : null
                })}
              </g>
              <text
                x={section.labelX}
                y={section.labelY}
                textAnchor="middle"
                dominantBaseline="middle"
                fontSize={11}
                fontWeight={600}
                className="fill-foreground"
              >
                {section.name}
              </text>
            </g>
          )
        })}
      </svg>

      {/* The same information as text, for screen readers and small screens */}
      {showTable && (
        <table className="w-full text-sm">
          <caption className="sr-only">Sections in this venue</caption>
          <thead>
            <tr className="border-b text-left text-muted-foreground">
              <th scope="col" className="py-1.5 font-medium">
                Section
              </th>
              <th scope="col" className="py-1.5 font-medium">
                Rows
              </th>
              <th scope="col" className="py-1.5 text-right font-medium">
                Seats
              </th>
            </tr>
          </thead>
          <tbody>
            {summary.map((section) => (
              <tr key={section.name} className="border-b last:border-0">
                <th scope="row" className="py-1.5 text-left font-medium">
                  {section.name}
                </th>
                <td className="py-1.5 tabular-nums">{section.rows}</td>
                <td className="py-1.5 text-right tabular-nums">
                  {section.seats}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
