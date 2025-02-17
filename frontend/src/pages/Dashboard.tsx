import { useAuth } from '../contexts/AuthContext'
import { useState, useEffect } from 'react'
import { API_BASE_URL } from '../services/config'

type BookMetadata = {
  id: string
  reference_string: string
  total_pages: number
  table_of_contents: Record<string, {
    title: string
    page_number: number
    timestamp?: number
  }>
}

export function Dashboard() {
  const { email, logout } = useAuth()
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [pendingFile, setPendingFile] = useState<File | null>(null)
  const [books, setBooks] = useState<BookMetadata[]>([])
  const [selectedBook, setSelectedBook] = useState<BookMetadata | null>(null)
  const [currentPosition, setCurrentPosition] = useState<{
    page: number;
    paragraph: number;
    sentence: number;
    timestamp: number;
  } | null>(null)

  useEffect(() => {
    const fetchBooks = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/books/list`, {
          credentials: 'include'
        })
        if (response.ok) {
          const data = await response.json()
          setBooks(data)
        }
      } catch (error) {
        console.error('Error fetching books:', error)
      }
    }

    fetchBooks()
    const interval = setInterval(fetchBooks, 120000) // Refresh every 2 minutes
    return () => clearInterval(interval)
  }, [])

  const handleBookSelect = async (book: BookMetadata) => {
    setSelectedBook(book)
    try {
      const response = await fetch(`${API_BASE_URL}/api/books/${book.id}/position`, {
        credentials: 'include'
      })
      if (response.ok) {
        const position = await response.json()
        setCurrentPosition(position)
      }
    } catch (error) {
      console.error('Error fetching book position:', error)
    }
  }

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
        throw new Error(data.id || 'Upload failed')
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

        <section className="mb-8 p-6 bg-white rounded-lg shadow">
          <h2 className="text-xl font-semibold mb-4">Your Books</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {books.map((book) => (
              <div
                key={book.id}
                className={`p-4 rounded-lg border cursor-pointer transition-colors ${
                  selectedBook?.id === book.id
                    ? 'border-violet-500 bg-violet-50'
                    : 'border-gray-200 hover:border-violet-300'
                }`}
                onClick={() => handleBookSelect(book)}
              >
                <h3 className="font-medium mb-2">{book.reference_string}</h3>
                <p className="text-sm text-gray-600">Pages: {book.total_pages}</p>
                {selectedBook?.id === book.id && currentPosition && (
                  <p className="text-sm text-violet-600 mt-2">
                    Current: Page {currentPosition.page}
                  </p>
                )}
              </div>
            ))}
          </div>
        </section>
      </main>
    </div>
  )
} 