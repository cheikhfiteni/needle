import { useAuth } from '../contexts/AuthContext'
import { Navigate } from 'react-router-dom'
import { Auth } from '../components/Auth'

export function Welcome() {
  const { isAuthenticated } = useAuth()

  if (isAuthenticated) {
    return <Navigate to="/" replace />
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gray-50">
      <div className="max-w-md w-full space-y-8">
        <div className="text-center">
          <h1 className="text-4xl font-bold">Welcome to Needle</h1>
          <p className="mt-2 text-gray-600">
            Your interactive storytelling companion
          </p>
        </div>
        <Auth />
      </div>
    </div>
  )
} 