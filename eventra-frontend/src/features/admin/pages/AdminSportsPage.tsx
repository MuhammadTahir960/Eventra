import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { FormField } from '@/components/FormField'
import { Notice } from '@/components/Notice'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { NativeSelect } from '@/components/ui/native-select'
import { useLeagues, useTeams } from '@/features/catalog/hooks'
import type { League, Team } from '@/features/catalog/types'
import { ApiError, apiFetch } from '@/lib/api-client'
import { fetchAllPages } from '@/lib/pagination'
import { ImageWithFallback } from '@/components/ImageWithFallback'
import { initial } from '@/lib/initial'
import { usePageTitle } from '@/lib/use-page-title'

interface Sport {
  id: string
  name: string
}

const LOGO_TYPES = 'image/jpeg,image/png,image/webp'
const MAX_LOGO_BYTES = 5 * 1024 * 1024

const messageOf = (caught: unknown, fallback: string) => {
  if (!(caught instanceof ApiError)) return fallback
  const first = Object.values(caught.fieldErrors)[0]?.[0]
  return first ?? caught.message
}

function useSports() {
  return useQuery({
    queryKey: ['catalog', 'sports'],
    queryFn: ({ signal }) => fetchAllPages<Sport>('/sports/', {}, signal),
  })
}

function SportsPanel({ sports }: { sports: Sport[] }) {
  const client = useQueryClient()
  const [name, setName] = useState('')
  const add = useMutation({
    mutationFn: () =>
      apiFetch<Sport>('/sports/', {
        method: 'POST',
        body: { name: name.trim() },
      }),
    onSuccess: () => {
      setName('')
      void client.invalidateQueries({ queryKey: ['catalog', 'sports'] })
    },
  })

  return (
    <section
      aria-labelledby="sports-heading"
      className="flex flex-col gap-4 rounded-lg border border-border bg-card p-5"
    >
      <h2 id="sports-heading" className="text-lg font-semibold tracking-tight">
        Sports
      </h2>
      <ul className="flex flex-wrap gap-2">
        {sports.map((sport) => (
          <li
            key={sport.id}
            className="rounded-full border border-border px-3 py-1 text-sm"
          >
            {sport.name}
          </li>
        ))}
      </ul>
      <form
        className="flex items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          if (name.trim()) add.mutate()
        }}
      >
        <FormField id="new-sport" label="Add a sport">
          {(control) => (
            <Input
              {...control}
              maxLength={100}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          )}
        </FormField>
        <Button
          type="submit"
          variant="outline"
          disabled={add.isPending || !name.trim()}
        >
          Add
        </Button>
      </form>
      {add.isError && (
        <Notice tone="error">
          {messageOf(add.error, 'The sport could not be added.')}
        </Notice>
      )}
    </section>
  )
}

function ClubLetter({ name }: { name: string }) {
  return (
    <span
      aria-hidden
      className="grid size-9 shrink-0 place-items-center rounded-full bg-muted text-sm font-medium"
    >
      {initial(name)}
    </span>
  )
}

// Leagues and teams share one shape: a name, a sport and an optional logo
function ClubPanel({
  kind,
  items,
  sports,
}: {
  kind: 'leagues' | 'teams'
  items: (League | Team)[]
  sports: Sport[]
}) {
  const client = useQueryClient()
  const label = kind === 'leagues' ? 'League' : 'Team'
  const [name, setName] = useState('')
  const [sport, setSport] = useState('')
  const [logo, setLogo] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const sportName = new Map(sports.map((s) => [s.id, s.name]))

  const refresh = () =>
    void client.invalidateQueries({ queryKey: ['catalog', kind] })

  const add = useMutation({
    mutationFn: () => {
      const body = new FormData()
      body.append('name', name.trim())
      body.append('sport', sport)
      if (logo) body.append('logo', logo)
      return apiFetch(`/${kind}/`, { method: 'POST', body })
    },
    onSuccess: () => {
      setName('')
      setLogo(null)
      refresh()
    },
    onError: (caught) =>
      setError(
        messageOf(caught, `The ${label.toLowerCase()} could not be added.`),
      ),
  })

  const replaceLogo = useMutation({
    mutationFn: ({ id, file }: { id: string; file: File }) => {
      const body = new FormData()
      body.append('logo', file)
      return apiFetch(`/${kind}/${id}/`, { method: 'PATCH', body })
    },
    onSuccess: refresh,
    onError: (caught) =>
      setError(messageOf(caught, 'The logo could not be uploaded.')),
  })

  function pickLogo(file: File | undefined, onOk: (file: File) => void) {
    setError(null)
    if (!file) return
    if (file.size > MAX_LOGO_BYTES) return setError('Use an image under 5 MB.')
    onOk(file)
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    if (!name.trim() || !sport)
      return setError(
        `Enter a name and choose a sport for the ${label.toLowerCase()}.`,
      )
    add.mutate()
  }

  return (
    <section
      aria-labelledby={`${kind}-heading`}
      className="flex flex-col gap-4 rounded-lg border border-border bg-card p-5"
    >
      <h2
        id={`${kind}-heading`}
        className="text-lg font-semibold tracking-tight"
      >
        {kind === 'leagues' ? 'Leagues' : 'Teams'}
      </h2>
      {error && <Notice tone="error">{error}</Notice>}
      <ul className="flex flex-col">
        {items.map((item) => (
          <li
            key={item.id}
            className="flex items-center gap-3 border-b border-border py-2.5 last:border-b-0"
          >
            {item.logo ? (
              <ImageWithFallback
                src={item.logo}
                alt=""
                fallback={<ClubLetter name={item.name} />}
                className="size-9 shrink-0 object-contain"
              />
            ) : (
              <ClubLetter name={item.name} />
            )}
            <span className="min-w-0 flex-1">
              <span className="block truncate font-medium">{item.name}</span>
              <span className="block text-[13px] text-muted-foreground">
                {sportName.get(item.sport) ?? ''}
              </span>
            </span>
            <label className="cursor-pointer rounded-md px-2.5 py-1.5 text-[13px] font-medium text-ember-deep hover:bg-muted has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-ring">
              {item.logo ? 'Replace logo' : 'Add logo'}
              <input
                type="file"
                accept={LOGO_TYPES}
                className="sr-only"
                onChange={(e) =>
                  pickLogo(e.target.files?.[0], (file) =>
                    replaceLogo.mutate({ id: item.id, file }),
                  )
                }
              />
            </label>
          </li>
        ))}
      </ul>
      <form
        onSubmit={handleSubmit}
        noValidate
        className="flex flex-col gap-3 border-t border-border pt-4"
      >
        <span className="text-sm font-medium">Add a {label.toLowerCase()}</span>
        <div className="grid gap-3 sm:grid-cols-2">
          <label htmlFor={`${kind}-name`} className="sr-only">
            Name
          </label>
          <Input
            id={`${kind}-name`}
            placeholder="Name"
            maxLength={100}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <label htmlFor={`${kind}-sport`} className="sr-only">
            Sport
          </label>
          <NativeSelect
            id={`${kind}-sport`}
            value={sport}
            onChange={(e) => setSport(e.target.value)}
          >
            <option value="">Sport</option>
            {sports.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </NativeSelect>
        </div>
        <input
          type="file"
          accept={LOGO_TYPES}
          aria-label={`${label} logo (optional)`}
          onChange={(e) => pickLogo(e.target.files?.[0], setLogo)}
          className="text-sm file:mr-3 file:h-9 file:rounded-md file:border file:border-hairline-strong file:bg-card file:px-3 file:text-sm file:font-medium hover:file:bg-muted"
        />
        <Button
          type="submit"
          variant="outline"
          className="w-fit"
          disabled={add.isPending}
        >
          {add.isPending ? 'Adding…' : `Add ${label.toLowerCase()}`}
        </Button>
      </form>
    </section>
  )
}

export function AdminSportsPage() {
  usePageTitle('Sports, leagues and teams')
  const sports = useSports()
  const leagues = useLeagues()
  const teams = useTeams()
  const sportList = sports.data ?? []

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        size="md"
        title="Sports"
        description="Sports, leagues and teams used for match listings. Team logos appear on match cards."
      />
      {sports.isError ? (
        <Notice tone="error">{sports.error.message}</Notice>
      ) : (
        <div className="grid gap-5 lg:grid-cols-2">
          <SportsPanel sports={sportList} />
          <ClubPanel
            kind="leagues"
            items={[...(leagues.data?.values() ?? [])]}
            sports={sportList}
          />
          <div className="lg:col-span-2">
            <ClubPanel
              kind="teams"
              items={[...(teams.data?.values() ?? [])]}
              sports={sportList}
            />
          </div>
        </div>
      )}
    </div>
  )
}
