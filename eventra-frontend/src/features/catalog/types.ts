// Shapes of the backend's venue, category and sports serializers.
// Images are absolute URLs, or null when none was uploaded.

export interface Venue {
  id: string
  name: string
  address: string
  city: string
  // ISO 3166 code, e.g. "PK"; show it with countryName()
  country: string
  // IANA zone, e.g. "Asia/Karachi"
  time_zone: string
  capacity: number
  // Drives the shape of the bird's-eye seat map. Treated as a plain string
  // here; the seating feature validates it and falls back to an oval.
  layout_shape: string
  photo: string | null
  created_at: string
  updated_at: string
}

// GET /countries/: the countries a venue can be in
export interface Country {
  code: string
  time_zones: string[]
  currency: string
  // A paid ticket's price range in that currency, as decimal strings
  min_price: string
  max_price: string
}

export interface Category {
  id: string
  name: string
  slug: string
  icon: string
  sort_order: number
  // Only admins may list events here (Sports)
  admin_only: boolean
}

export interface League {
  id: string
  sport: string
  name: string
  logo: string | null
}

// Who gets paid for an admin-listed event (admins only)
export interface Partner {
  id: string
  name: string
}

export interface Team {
  id: string
  sport: string
  name: string
  logo: string | null
}
