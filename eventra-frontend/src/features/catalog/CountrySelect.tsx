import type { ComponentProps } from 'react'
import { NativeSelect } from '@/components/ui/native-select'
import { useCountries } from './hooks'

// The countries a venue can be in, by name; the value is the ISO code
export function CountrySelect(props: ComponentProps<typeof NativeSelect>) {
  const countries = useCountries()
  return (
    <NativeSelect {...props}>
      <option value="">
        {countries.isPending ? 'Loading countries…' : 'Select a country'}
      </option>
      {countries.data?.map((country) => (
        <option key={country.code} value={country.code}>
          {country.name}
        </option>
      ))}
    </NativeSelect>
  )
}
