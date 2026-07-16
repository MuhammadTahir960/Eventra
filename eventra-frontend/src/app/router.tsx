import { createBrowserRouter } from 'react-router-dom'

function Home() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <h1 className="text-3xl font-bold">Eventra</h1>
    </div>
  )
}

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Home />,
  },
])
