import { useAuth } from '../contexts/AuthContext'
import { useState } from 'react'
import { API_BASE_URL } from '../services/config'

type BookMetadata = {
  book_id: string
  reference_string: string
  total_pages: number
  table_of_contents: Record<number, {
    title: string
    page_number: number
    timestamp?: number
  }>
  user_book_state_id: string
}

export function Dashboard() {
  const { email, logout } = useAuth()
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [pendingFile, setPendingFile] = useState<File | null>(null)

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    setPendingFile(file)
  }

  const handleFileUpload = async () => {
    if (!pendingFile) return
    
    const formData = new FormData()
    formData.append('file', pendingFile)
    
    try {
      const response = await fetch(`${API_BASE_URL}/api/books/upload`, {
        method: 'POST',
        body: formData,
        credentials: 'include'
      })
      
      const data: BookMetadata = await response.json()
      if (!response.ok) {
        console.error('Upload error:', data)
        throw new Error(data.book_id || 'Upload failed')
      }
      console.log('Upload successful:', data)
      setSelectedFile(pendingFile)
      setPendingFile(null)
    } catch (error) {
      console.error('Error uploading file:', error)
    }
  }

  const togglePlayback = async () => {
    try {
      if (isPlaying) {
        console.log('Pausing narration')
        await fetch('/api/narration/pause', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ /* Add position data here */ })
        })
      } else {
        console.log('Starting narration')
        const ws = new WebSocket(`ws://${window.location.host}/api/narration/stream/book_id`)
        // Add WebSocket handling here
      }
      setIsPlaying(!isPlaying)
    } catch (error) {
      console.error('Error controlling playback:', error)
    }
  }

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
      <main className="max-w-4xl mx-auto">
        <section className="mb-8 p-6 bg-white rounded-lg shadow">
          <h2 className="text-xl font-semibold mb-4">Upload PDF</h2>
          <div className="flex items-center gap-4">
            <input
              type="file"
              accept=".pdf"
              onChange={handleFileSelect}
              className="block w-full text-sm text-slate-500
                file:mr-4 file:py-2 file:px-4
                file:rounded-full file:border-0
                file:text-sm file:font-semibold
                file:bg-violet-50 file:text-violet-700
                hover:file:bg-violet-100"
            />
            {pendingFile && (
              <button
                onClick={handleFileUpload}
                className="p-3 rounded-full bg-violet-500 hover:bg-violet-600 text-white"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                </svg>
              </button>
            )}
            {selectedFile && (
              <span className="text-green-600">
                {selectedFile.name} uploaded
              </span>
            )}
          </div>
        </section>

        <section className="p-6 bg-white rounded-lg shadow">
          <h2 className="text-xl font-semibold mb-4">Audio Controls</h2>
          <div className="flex gap-4">
            <button
              onClick={togglePlayback}
              className={`px-6 py-3 rounded-md font-medium ${
                isPlaying
                  ? 'bg-red-500 hover:bg-red-600 text-white'
                  : 'bg-green-500 hover:bg-green-600 text-white'
              }`}
            >
              {isPlaying ? 'Pause' : 'Play'}
            </button>
            <button
              className="px-6 py-3 bg-yellow-500 hover:bg-yellow-600 text-white rounded-md font-medium"
              onClick={() => {
                console.log('Interrupting narration')
                if (isPlaying) {
                  setIsPlaying(false)
                }
              }}
            >
              Interrupt
            </button>
          </div>
        </section>
      </main>
    </div>
  )
} 