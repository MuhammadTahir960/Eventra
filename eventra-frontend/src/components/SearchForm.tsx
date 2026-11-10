import type { FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

// `value` comes from the URL; the key resets the box when it changes (back button)
export function SearchForm({
  id,
  label,
  placeholder,
  value,
  onSearch,
}: {
  id: string
  label: string
  placeholder: string
  value: string
  onSearch: (value: string) => void
}) {
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const query = new FormData(event.currentTarget).get('q')
    onSearch(typeof query === 'string' ? query : '')
  }

  return (
    <form
      key={value}
      role="search"
      onSubmit={submit}
      className="flex flex-1 gap-2"
    >
      <label htmlFor={id} className="sr-only">
        {label}
      </label>
      <Input
        id={id}
        name="q"
        type="search"
        maxLength={100}
        placeholder={placeholder}
        defaultValue={value}
      />
      <Button type="submit" variant="outline">
        Search
      </Button>
    </form>
  )
}
