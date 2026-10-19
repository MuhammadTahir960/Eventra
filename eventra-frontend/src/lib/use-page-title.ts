import { useEffect } from 'react'

const SITE = 'Eventra'

// Sets the browser tab title: "Page | Eventra", or the site name alone.
// Screen readers announce it on navigation, so every page calls this. Pass
// undefined while data loads; the title updates once it arrives.
export function usePageTitle(title: string | undefined) {
  useEffect(() => {
    document.title = title ? `${title} | ${SITE}` : SITE
  }, [title])
}
