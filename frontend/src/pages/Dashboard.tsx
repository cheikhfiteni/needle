import { useAuth } from '../contexts/AuthContext'
import { useState, useEffect, useRef } from 'react'
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

type AudioPlayerState = {
  isPlaying: boolean
  currentTime: number
  duration: number
  bufferedRanges: { start: number; end: number }[]
}

type BufferRange = {
  start: number
  end: number
}

export function Dashboard() {
  const { email, logout } = useAuth()
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [pendingFile, setPendingFile] = useState<File | null>(null)
  const [books, setBooks] = useState<BookMetadata[]>([])
  const [selectedBook, setSelectedBook] = useState<BookMetadata | null>(null)
  const [currentPosition, setCurrentPosition] = useState<{
    page: number;
    paragraph: number;
    sentence: number;
    timestamp: number;
  } | null>(null)

  // Audio player state
  const audioRef = useRef<HTMLAudioElement>(null)
  const [playerState, setPlayerState] = useState<AudioPlayerState>({
    isPlaying: false,
    currentTime: 0,
    duration: 0,
    bufferedRanges: []
  })

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

  // Handle audio time updates
  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return

    const handleTimeUpdate = () => {
      setPlayerState(prev => ({
        ...prev,
        currentTime: audio.currentTime
      }))
    }

    const handleDurationChange = () => {
      setPlayerState(prev => ({
        ...prev,
        duration: audio.duration
      }))
    }

    const handleProgress = () => {
      const ranges: BufferRange[] = []
      for (let i = 0; i < (audioRef.current?.buffered.length || 0); i++) {
        if (audioRef.current?.buffered) {
          ranges.push({
            start: audioRef.current.buffered.start(i),
            end: audioRef.current.buffered.end(i)
          })
        }
      }
      setPlayerState(prev => ({
        ...prev,
        bufferedRanges: ranges
      }))
    }

    audio.addEventListener('timeupdate', handleTimeUpdate)
    audio.addEventListener('durationchange', handleDurationChange)
    audio.addEventListener('progress', handleProgress)

    return () => {
      audio.removeEventListener('timeupdate', handleTimeUpdate)
      audio.removeEventListener('durationchange', handleDurationChange)
      audio.removeEventListener('progress', handleProgress)
    }
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
        if (audioRef.current) {
          audioRef.current.currentTime = position.timestamp || 0
        }
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

  // Handle audio playback controls
  const handlePlayPause = async () => {
    if (!selectedBook || !audioRef.current) return

    try {
      if (playerState.isPlaying) {
        audioRef.current.pause()
        await fetch(`${API_BASE_URL}/api/narration/interrupt`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            book_id: selectedBook.id,
            timestamp: audioRef.current.currentTime
          })
        })
      } else {
        // Instead of creating a blob URL, directly set the src to the streaming endpoint
        audioRef.current.src = `${API_BASE_URL}/api/narration/audio/${selectedBook.id}?timestamp=${audioRef.current.currentTime}`
        try {
          await audioRef.current.play()
        } catch (error) {
          console.error('Playback failed:', error)
          return
        }
      }
      setPlayerState(prev => ({ ...prev, isPlaying: !prev.isPlaying }))
    } catch (error) {
      console.error('Error controlling playback:', error)
    }
  }

  const handleScrub = async (newTime: number) => {
    if (!selectedBook || !audioRef.current) return

    try {
      // Update the audio source to the new timestamp
      audioRef.current.src = `${API_BASE_URL}/api/narration/audio/${selectedBook.id}?timestamp=${newTime}`
      audioRef.current.currentTime = newTime
      
      if (playerState.isPlaying) {
        try {
          await audioRef.current.play()
        } catch (error) {
          console.error('Playback failed after scrub:', error)
          setPlayerState(prev => ({ ...prev, isPlaying: false }))
        }
      }
    } catch (error) {
      console.error('Error scrubbing:', error)
    }
  }

  // Add error handling for audio
  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return

    const handleError = (e: Event) => {
      console.error('Audio error:', e)
      setPlayerState(prev => ({ ...prev, isPlaying: false }))
    }

    audio.addEventListener('error', handleError)
    return () => audio.removeEventListener('error', handleError)
  }, [])

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

        {selectedBook && (
          <section className="mb-8 p-6 bg-white rounded-lg shadow">
            <h2 className="text-xl font-semibold mb-4">Audio Player</h2>
            <div className="space-y-4">
              <audio ref={audioRef} className="hidden" />
              
              {/* Progress bar */}
              <div className="relative h-2 bg-gray-200 rounded-full">
                {/* Buffered ranges */}
                {playerState.bufferedRanges.map((range, i) => (
                  <div
                    key={i}
                    className="absolute h-full bg-gray-400 rounded-full"
                    style={{
                      left: `${(range.start / playerState.duration) * 100}%`,
                      width: `${((range.end - range.start) / playerState.duration) * 100}%`
                    }}
                  />
                ))}
                {/* Progress */}
                <div
                  className="absolute h-full bg-violet-500 rounded-full"
                  style={{
                    width: `${(playerState.currentTime / playerState.duration) * 100}%`
                  }}
                />
                <input
                  type="range"
                  min="0"
                  max={playerState.duration}
                  value={playerState.currentTime}
                  onChange={(e) => handleScrub(parseFloat(e.target.value))}
                  className="absolute w-full h-full opacity-0 cursor-pointer"
                />
              </div>

              {/* Controls */}
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-600">
                  {formatTime(playerState.currentTime)} / {formatTime(playerState.duration)}
                </span>
                <div className="flex gap-4">
                  <button
                    onClick={handlePlayPause}
                    className={`px-6 py-3 rounded-md font-medium ${
                      playerState.isPlaying
                        ? 'bg-red-500 hover:bg-red-600 text-white'
                        : 'bg-green-500 hover:bg-green-600 text-white'
                    }`}
                  >
                    {playerState.isPlaying ? 'Pause' : 'Play'}
                  </button>
                </div>
              </div>
            </div>
          </section>
        )}

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

// Helper function to format time
function formatTime(seconds: number): string {
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = Math.floor(seconds % 60)
  return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`
} 