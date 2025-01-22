from abc import ABC, abstractmethod
import os
from openai import OpenAI
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_async_db, get_audio_chunk_for_timestamp
from app.models.models import Page

# Creating voices, synthesizing audio, diarization all done here.
class SynthTranscriber(ABC):
    @abstractmethod
    def synthesize_audio(self, page: Page) -> bytes:
        pass

# Actually managing the cursor position and plyaback interactions between
# Narrator, Chatter, and client. Also calls the SynthTranscriber to get the audio a couple pages ahead.

### Important question to answer is whether pages are first class citizens or not
class Narrator(ABC):
    def __init__(self):
        self.audio_buffer = {}  # Map of chunk sequence numbers to audio bytes
        self.current_chunk = None
        self.current_position = 0
        self.buffer_size = 2  # Number of chunks to buffer ahead

    @abstractmethod
    def narrate(self, current_position: float) -> str:
        pass

    @abstractmethod
    def interrupt(self, current_position: float) -> None:
        pass

    async def load_audio(self, timestamp: float) -> bytes:
        """Loads audio chunk for given timestamp and manages buffer"""
        async with get_async_db() as db:
            chunk, position = await get_audio_chunk_for_timestamp(db, self.book_id, timestamp)
            
            if not chunk:
                raise ValueError("No audio chunk found for timestamp")
                
            if chunk.sequence_number not in self.audio_buffer:
                # Load requested chunk
                self.audio_buffer[chunk.sequence_number] = chunk.audio_blob
                
                # Pre-fetch next chunks
                for i in range(1, self.buffer_size + 1):
                    next_chunk = await db.execute(
                        select(AudioChunk)
                        .where(
                            and_(
                                AudioChunk.book_id == self.book_id,
                                AudioChunk.sequence_number == chunk.sequence_number + i
                            )
                        )
                    )
                    next_chunk = next_chunk.scalar_one_or_none()
                    if next_chunk:
                        self.audio_buffer[next_chunk.sequence_number] = next_chunk.audio_blob
                        
                # Remove old chunks from buffer
                keys_to_remove = [
                    k for k in self.audio_buffer.keys() 
                    if k < chunk.sequence_number - 1
                ]
                for k in keys_to_remove:
                    del self.audio_buffer[k]
            
            self.current_chunk = chunk
            self.current_position = position
            
            return self.audio_buffer[chunk.sequence_number]

    @abstractmethod
    def _go_to_nearest_sentence(self, current_position: float) -> None:
        pass


    ### These are methods that are used to control playback in the client, and not used by the Narrator
    ### but doing tool use for this would be interesting (either to send to the frontend as just a seek, or prompt a audio load)
    @abstractmethod
    def rewind(self, duration: float) -> None:
        pass

    @abstractmethod
    def scrub(self, timestamp: float) -> None:
        pass

    @abstractmethod
    def jump_to_timestamp(self, timestamp: float) -> None:
        pass

    @abstractmethod
    def jump_to_page(self, page: Page) -> None:
        pass

    def resume(self) -> None:
        pass

    def stop(self) -> None:
        pass

# Honestly AI voice transcription is not very good, but will get better.
# Licensing out human audio would still be the recommended byte source.
class OpenAISynthTranscriber(SynthTranscriber):
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.MAX_CHARS = 4096

    def _convert_page_to_buffered_text(self, page: Page) -> list[str]:
        def add_to_buffer(text: str, separator: str = " ") -> None:
            nonlocal current_buffer, buffers
            if len(current_buffer + text) <= self.MAX_CHARS:
                current_buffer += text + separator
            else:
                if current_buffer:
                    buffers.append(current_buffer.strip())
                current_buffer = text + separator

        def flush_buffer() -> None:
            nonlocal current_buffer, buffers
            if current_buffer:
                buffers.append(current_buffer.strip())
                current_buffer = ""

        buffers = []
        current_buffer = ""

        # Process paragraphs
        for paragraph in page.paragraphed_text.split('\n'):
            add_to_buffer(paragraph, "\n")

        # Process any remaining sentences
        if not buffers:
            for sentence in page.sentenced_text.split('\n'):
                add_to_buffer(sentence, " ")
            flush_buffer()

        return buffers if buffers else [""]

    def _convert_text_to_audio(self, text: str, voice: str = "alloy") -> bytes:
        response = self.client.audio.speech.create(
            model="tts-1",
            input=text,
            voice=voice
        )
        return response.content
        
    def synthesize_audio(self, page: Page):
        text = self._convert_page_to_text(page)
        return self._convert_text_to_audio(text)
