import { useAuth } from '../contexts/AuthContext'

export function Dashboard() {
  const { email, logout } = useAuth()

  return (
    <div className="min-h-screen p-4">
      <header className="flex justify-between items-center mb-8">
        <h1 className="text-2xl font-bold">Needle Dashboard</h1>
        <div className="flex items-center gap-4">
          <span>{email}</span>
          <button
            onClick={logout}
            className="px-4 py-2 text-white bg-red-500 rounded-md hover:bg-red-600"
          >
            Logout
          </button>
        </div>
      </header>
      <main>
        {/* Your dashboard content will go here */}
      </main>
    </div>
  )
} 