import path from 'path'
import { loadEnv, type Plugin } from 'vite'
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const envDir = path.resolve(import.meta.dirname, '..')

// Content-Security-Policy for production builds, as a <meta> tag so it travels
// with the build wherever it's hosted. Scripts only from this app, Stripe and
// Cloudflare Turnstile; no inline scripts. Dev is left alone: Vite's dev server
// injects an inline script. frame-ancestors can't go in a meta tag; the host
// that serves the build must send it as a header.
function contentSecurityPolicy(apiOrigin: string): Plugin {
  const socketOrigin = apiOrigin.replace(/^http/, 'ws')
  const policy = [
    "default-src 'self'",
    "script-src 'self' https://js.stripe.com https://*.js.stripe.com https://challenges.cloudflare.com",
    // React style attributes and the toast library's injected styles
    "style-src 'self' 'unsafe-inline'",
    // Images can't run code; media comes from the API or R2 over https
    `img-src 'self' data: blob: https: ${apiOrigin}`,
    "font-src 'self'",
    // fonts.googleapis.com: the Stripe card form fetches its font's stylesheet
    `connect-src 'self' ${apiOrigin} ${socketOrigin} https://api.stripe.com https://fonts.googleapis.com`,
    'frame-src https://js.stripe.com https://*.js.stripe.com https://hooks.stripe.com https://challenges.cloudflare.com',
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
  ].join('; ')
  return {
    name: 'content-security-policy',
    apply: 'build',
    transformIndexHtml: () => [
      {
        tag: 'meta',
        attrs: { 'http-equiv': 'Content-Security-Policy', content: policy },
        injectTo: 'head-prepend',
      },
    ],
  }
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, envDir, ['BACKEND_BASE_URL'])
  const apiOrigin = new URL(env.BACKEND_BASE_URL || 'http://localhost:8000')
    .origin
  return {
    envDir,
    envPrefix: ['VITE_', 'BACKEND_BASE_URL'],
    plugins: [react(), tailwindcss(), contentSecurityPolicy(apiOrigin)],
    resolve: { tsconfigPaths: true },
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
    },
  }
})
