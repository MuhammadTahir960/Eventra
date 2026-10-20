import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'
import { RequireRole } from './RequireRole'
import { authStore, type Role } from './auth-store'

// Renders an admin-only route plus a stand-in login page
function renderAdminRoute() {
  render(
    <MemoryRouter initialEntries={['/admin/moderation']}>
      <Routes>
        <Route path="/login" element={<p>Login page</p>} />
        <Route element={<RequireRole roles={['admin']} />}>
          <Route path="/admin/moderation" element={<p>Moderation queue</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

function signInAs(role: Role) {
  authStore.setSession(
    {
      id: 'u1',
      email: `${role}@example.com`,
      role,
      first_name: 'Test',
      last_name: 'User',
      gender: 'other',
      avatar: null,
    },
    'test-access',
    'test-refresh',
  )
}

describe('RequireRole', () => {
  afterEach(() => {
    authStore.clear()
  })

  it('sends signed-out visitors to the login page', () => {
    renderAdminRoute()
    expect(screen.getByText('Login page')).toBeInTheDocument()
  })

  it('never shows admin screens to an attendee', () => {
    signInAs('attendee')
    renderAdminRoute()
    expect(screen.getByRole('alert')).toHaveTextContent('Access restricted')
    expect(screen.queryByText('Moderation queue')).not.toBeInTheDocument()
  })

  it('never shows admin screens to an organizer', () => {
    signInAs('organizer')
    renderAdminRoute()
    expect(screen.queryByText('Moderation queue')).not.toBeInTheDocument()
  })

  it('lets an admin through', () => {
    signInAs('admin')
    renderAdminRoute()
    expect(screen.getByText('Moderation queue')).toBeInTheDocument()
  })
})
