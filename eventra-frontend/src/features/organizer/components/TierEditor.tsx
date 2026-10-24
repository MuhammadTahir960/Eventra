import { FormField } from '@/components/FormField'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { NativeSelect } from '@/components/ui/native-select'
import type { SectionSummary } from '@/features/seating/layout/summary'
import type { DraftErrors, TierDraft } from '../create-event'
import { MAX_TIERS, tierColor } from '../tier-colors'

interface TierEditorProps {
  tiers: TierDraft[]
  // The tier that clicking a section on the map assigns
  activeKey: string
  assignments: Record<string, string>
  sections: SectionSummary[]
  errors: DraftErrors
  disabled: boolean
  // Offered when section names look like classes (VIP, Business, Economy)
  onSuggest: (() => void) | null
  onActiveChange: (key: string) => void
  onTierChange: (
    key: string,
    patch: Partial<Pick<TierDraft, 'name' | 'price'>>,
  ) => void
  onAddTier: () => void
  onRemoveTier: (key: string) => void
  onAssign: (section: string, tierKey: string) => void
}

export function TierEditor({
  tiers,
  activeKey,
  assignments,
  sections,
  errors,
  disabled,
  onSuggest,
  onActiveChange,
  onTierChange,
  onAddTier,
  onRemoveTier,
  onAssign,
}: TierEditorProps) {
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Ticket tiers</h2>
          <p className="text-sm text-muted-foreground">
            Create a tier for each price (for example VIP, Business, Economy),
            then give every section a tier. Pick a tier below and click sections
            on the map, or use the table.
          </p>
        </div>
        {onSuggest && (
          <Button
            variant="outline"
            size="sm"
            onClick={onSuggest}
            disabled={disabled}
          >
            Create tiers from section names
          </Button>
        )}
      </div>

      {errors.tiers && (
        <p id="tiers" tabIndex={-1} className="text-sm text-danger">
          {errors.tiers}
        </p>
      )}

      <fieldset className="space-y-3" disabled={disabled}>
        <legend className="sr-only">
          Tier to apply when you click a section
        </legend>
        {tiers.map((tier, index) => (
          <div
            key={tier.key}
            className="grid items-start gap-3 rounded-lg border border-border bg-card p-3 sm:grid-cols-[auto_1fr_10rem_auto]"
          >
            <label className="flex items-center gap-2 pt-7 text-sm sm:pt-8">
              <input
                type="radio"
                name="paint-tier"
                checked={activeKey === tier.key}
                onChange={() => onActiveChange(tier.key)}
                className="accent-[var(--ink)]"
                aria-label={`Apply ${tier.name || `tier ${index + 1}`} when I click a section`}
              />
              <span
                aria-hidden="true"
                className="size-4 rounded-full border"
                style={{ background: tierColor(index) }}
              />
            </label>

            <FormField
              id={`tier-${tier.key}-name`}
              label="Tier name"
              error={errors[`tier-${tier.key}-name`]}
            >
              {(control) => (
                <Input
                  {...control}
                  value={tier.name}
                  maxLength={100}
                  placeholder="e.g. VIP"
                  onChange={(event) =>
                    onTierChange(tier.key, { name: event.target.value })
                  }
                />
              )}
            </FormField>

            <FormField
              id={`tier-${tier.key}-price`}
              label="Price (USD)"
              error={errors[`tier-${tier.key}-price`]}
            >
              {(control) => (
                <Input
                  {...control}
                  value={tier.price}
                  inputMode="decimal"
                  placeholder="45.00"
                  onChange={(event) =>
                    onTierChange(tier.key, { price: event.target.value })
                  }
                />
              )}
            </FormField>

            <Button
              variant="ghost"
              className="mt-7 sm:mt-8"
              onClick={() => onRemoveTier(tier.key)}
              disabled={tiers.length === 1}
              aria-label={`Remove ${tier.name || `tier ${index + 1}`}`}
            >
              Remove
            </Button>
          </div>
        ))}

        <Button
          variant="outline"
          size="sm"
          onClick={onAddTier}
          disabled={tiers.length >= MAX_TIERS}
        >
          Add a tier
        </Button>
      </fieldset>

      <div id="section-assignments" tabIndex={-1} className="outline-none">
        <h3 className="mb-2 text-[15px] font-semibold">Section tiers</h3>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-muted-foreground">
              <th scope="col" className="py-1.5 font-medium">
                Section
              </th>
              <th scope="col" className="py-1.5 font-medium">
                Seats
              </th>
              <th scope="col" className="py-1.5 font-medium">
                Tier
              </th>
            </tr>
          </thead>
          <tbody>
            {sections.map((section) => (
              <tr key={section.name} className="border-b last:border-0">
                <th scope="row" className="py-1.5 text-left font-medium">
                  <label htmlFor={`assign-${section.name}`}>
                    {section.name}
                  </label>
                </th>
                <td className="py-1.5 tabular-nums">{section.seats}</td>
                <td className="py-1.5">
                  <NativeSelect
                    id={`assign-${section.name}`}
                    value={assignments[section.name] ?? ''}
                    disabled={disabled}
                    onChange={(event) =>
                      onAssign(section.name, event.target.value)
                    }
                  >
                    <option value="">Not assigned</option>
                    {tiers.map((tier, index) => (
                      <option key={tier.key} value={tier.key}>
                        {tier.name || `Tier ${index + 1}`}
                      </option>
                    ))}
                  </NativeSelect>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {errors.sections && (
          <p className="mt-2 text-sm text-danger">{errors.sections}</p>
        )}
      </div>
    </div>
  )
}
