// Shapes of the backend's venue, category and sports serializers.
// Images are absolute URLs, or null when none was uploaded.

export interface Venue {
  id: string
  name: string
  address: string
  city: string
  country: string
  capacity: number
  // Drives the shape of the bird's-eye seat map. Treated as a plain string
  // here; the seating feature validates it and falls back to an oval.
  layout_shape: string
  photo: string | null
  created_at: string
  updated_at: string
}

export interface Category {
  id: string
  name: string
  slug: string
  icon: string
  sort_order: number
}

export interface League {
  id: string
  sport: string
  name: string
  logo: string | null
}

export interface Team {
  id: string
  sport: string
  name: string
  logo: string | null
}
