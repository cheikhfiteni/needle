from abc import ABC, abstractmethod
import os
import re
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

    def _break_into_sentences(self, text: str) -> list[str]:
        text = text.replace('...', '###ELLIPSIS###')
        
        sentences = re.split(r'([.!?]+)\s+', text)
        # Recombine delimiter with sentence: ['Hi', '!', 'What', '!?', 'Name', '.'] -> ['Hi!', 'What!?', 'Name.']
        sentences = [''.join(sentences[i:i+2]) for i in range(0, len(sentences)-1, 2)]
        # If the last sentence doesn't end with a period, add one
        if sentences and sentences[-1][-1] not in '.!?':
            sentences[-1] = sentences[-1] + '.'

        sentences = [s.replace('###ELLIPSIS###', '...') for s in sentences]
        return sentences

    def _convert_page_to_buffered_text(self, page: Page) -> list[str]:
        def add_to_buffer(text: str, separator: str = " ") -> None:
            nonlocal current_buffer, sized_buffers
            if len(current_buffer + text) <= self.MAX_CHARS:
                current_buffer += text + separator
            else:
                if current_buffer:
                    sized_buffers.append(current_buffer.strip())
                current_buffer = text + separator

        def flush_buffer() -> None:
            nonlocal current_buffer, sized_buffers
            if current_buffer.strip():
                sized_buffers.append(current_buffer.strip())
                current_buffer = ""

        sized_buffers = []
        current_buffer = ""
        unprocessed_chunks = page.paragraphed_text[::-1]

        boundary_splits = [
        [' <p> '],           # Paragraph boundaries
        ['. ', '? ', '! '],  # Sentence boundaries
        [' ']                # Word boundaries
        ]

        # Process paragraphs
        while unprocessed_chunks:
            chunk = unprocessed_chunks.pop(0)
            if len(current_buffer + chunk) <= self.MAX_CHARS:
                current_buffer += chunk + "\n"
            else:
                # break into sentences
                # Split on any sentence boundary
                sentences = []
                current_chunk = chunk
                for boundary in boundary_splits[1]:
                    if boundary in current_chunk:
                        parts = current_chunk.split(boundary)
                        for i, part in enumerate(parts[:-1]):
                            sentences.append(part + boundary)
                        current_chunk = parts[-1]
                if current_chunk:
                    sentences.append(current_chunk)
                
                # Process sentences and re-add remainder to unprocessed chunks
                added_any = False
                for i, sentence in enumerate(sentences):
                    if len(current_buffer + sentence) <= self.MAX_CHARS:
                        current_buffer += sentence
                        added_any = True
                    else:
                        if added_any:
                            remainder = "".join(sentences[i:])
                            unprocessed_chunks.insert(0, remainder)
                        break
                for sentence in sentences:
                    if len(current_buffer + sentence) <= self.MAX_CHARS:
                        current_buffer += sentence + " "
                    else:
                        break

        # Process any remaining sentences
        if not sized_buffers:
            for sentence in page.sentenced_text.split('\n'):
                add_to_buffer(sentence, " ")
            flush_buffer()

        return sized_buffers if sized_buffers else [""]

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
