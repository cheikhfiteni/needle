// components/AudioStreamer.tsx
import { useEffect, useRef, useState } from 'react'
import { API_BASE_URL } from '../services/config'

interface AudioStreamerProps {
  bookId: string
  onTimeUpdate?: (time: number) => void
  onError?: (error: Error) => void
  initialTimestamp?: number
}

interface BufferRange {
  start: number
  end: number
}

export function AudioStreamer({ bookId, onTimeUpdate, onError, initialTimestamp = 0 }: AudioStreamerProps) {
  const audioRef = useRef<HTMLAudioElement>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [bufferedRanges, setBufferedRanges] = useState<BufferRange[]>([])

  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return

    const handleTimeUpdate = () => {
      setCurrentTime(audio.currentTime)
      onTimeUpdate?.(audio.currentTime)
    }

    const handleDurationChange = () => {
      setDuration(audio.duration)
    }

    const handleProgress = () => {
      const ranges: BufferRange[] = []
      for (let i = 0; i < (audio?.buffered.length || 0); i++) {
        ranges.push({
          start: audio!.buffered.start(i),
          end: audio!.buffered.end(i)
        })
      }
      setBufferedRanges(ranges)
    }

    const handleError = (e: Event) => {
      console.error('Audio error:', e)
      onError?.(new Error('Audio playback error'))
      setIsPlaying(false)
    }

    audio.addEventListener('timeupdate', handleTimeUpdate)
    audio.addEventListener('durationchange', handleDurationChange)
    audio.addEventListener('progress', handleProgress)
    audio.addEventListener('error', handleError)

    return () => {
      audio.removeEventListener('timeupdate', handleTimeUpdate)
      audio.removeEventListener('durationchange', handleDurationChange)
      audio.removeEventListener('progress', handleProgress)
      audio.removeEventListener('error', handleError)
    }
  }, [onTimeUpdate, onError])

  const play = async () => {
    if (!audioRef.current || !bookId) return

    try {
      const audio = audioRef.current
      const response = await fetch(`${API_BASE_URL}/api/narration/audio/${bookId}?timestamp=${audio.currentTime}`, {
        credentials: 'include'
      })
      
      if (!response.ok) {
        throw new Error('Failed to fetch audio')
      }

      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      audio.src = url
      await audio.play()
      setIsPlaying(true)

      // Clean up the URL when we're done with it
      audio.onended = () => {
        URL.revokeObjectURL(url)
        setIsPlaying(false)
      }
    } catch (error) {
      console.error('Play error:', error)
      onError?.(error as Error)
      setIsPlaying(false)
    }
  }

  const pause = async () => {
    if (!audioRef.current || !bookId) return

    try {
      audioRef.current.pause()
      await fetch(`${API_BASE_URL}/api/narration/interrupt`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          book_id: bookId,
          timestamp: audioRef.current.currentTime
        })
      })
      setIsPlaying(false)
    } catch (error) {
      console.error('Pause error:', error)
      onError?.(error as Error)
    }
  }

  const seek = async (newTime: number) => {
    if (!audioRef.current || !bookId) return

    try {
      const response = await fetch(`${API_BASE_URL}/api/narration/audio/${bookId}?timestamp=${newTime}`, {
        credentials: 'include'
      })
      
      if (!response.ok) {
        throw new Error('Failed to fetch audio')
      }

      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      
      audioRef.current.src = url
      audioRef.current.currentTime = newTime
      
      if (isPlaying) {
        await audioRef.current.play()
      }

      // Clean up the URL when we're done with it
      audioRef.current.onended = () => {
        URL.revokeObjectURL(url)
      }
    } catch (error) {
      console.error('Seek error:', error)
      onError?.(error as Error)
    }
  }

  useEffect(() => {
    if (audioRef.current && initialTimestamp > 0) {
      seek(initialTimestamp)
    }
  }, [initialTimestamp])

  return {
    controls: {
      play,
      pause,
      seek,
      isPlaying,
      currentTime,
      duration,
      bufferedRanges,
    },
    AudioElement: <audio ref={audioRef} className="hidden" />
  }
}