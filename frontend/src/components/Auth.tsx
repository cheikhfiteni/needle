import { useState } from 'react'
import { useAuth } from '../contexts/AuthContext'
import { API_BASE_URL } from '../services/config'

export function Auth() {
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [codeSent, setCodeSent] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  
  const { login } = useAuth()

  const requestCode = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    
    try {
      const response = await fetch(`${API_BASE_URL}/auth/request-code`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email }),
      })

      if (response.ok) {
        setCodeSent(true)
      } else {
        const data = await response.json()
        setError(data.detail || 'Failed to send verification code')
      }
    } catch (err) {
      setError('Failed to send verification code')
    } finally {
      setLoading(false)
    }
  }

  const verifyCode = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')

    try {
      const response = await fetch(`${API_BASE_URL}/auth/verify-code`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({ email, code }),
      })

      if (response.ok) {
        login(email)
      } else {
        const data = await response.json()
        setError(data.detail || 'Verification failed')
      }
    } catch (err) {
      setError('Failed to verify code')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="mt-8 space-y-6">
      {error && (
        <div className="text-red-500 text-center">{error}</div>
      )}
      
      {!codeSent ? (
        <form onSubmit={requestCode} className="space-y-4">
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="Enter your email"
            className="w-full px-4 py-2 border rounded-md"
            required
          />
          <button
            type="submit"
            disabled={loading}
            className="w-full px-4 py-2 text-white bg-blue-500 rounded-md hover:bg-blue-600 disabled:opacity-50"
          >
            {loading ? 'Sending...' : 'Get Verification Code'}
          </button>
        </form>
      ) : (
        <form onSubmit={verifyCode} className="space-y-4">
          <input
            type="text"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="Enter verification code"
            className="w-full px-4 py-2 border rounded-md"
            required
          />
          <button
            type="submit"
            disabled={loading}
            className="w-full px-4 py-2 text-white bg-blue-500 rounded-md hover:bg-blue-600 disabled:opacity-50"
          >
            {loading ? 'Verifying...' : 'Verify Code'}
          </button>
        </form>
      )}
    </div>
  )
} 