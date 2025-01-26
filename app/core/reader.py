from abc import ABC, abstractmethod
import os
import re
from openai import AsyncOpenAI
from sqlalchemy import select, and_
from app.db.database import get_async_db, get_audio_chunk_for_timestamp, get_pages_from_book, update_reading_position
from app.models.models import Page

# Creating voices, synthesizing audio, diarization all done here.
class SynthTranscriber(ABC):
    @abstractmethod
    def synthesize_page_audio(self, page: Page) -> bytes:
        pass

# Actually managing the cursor position and plyaback interactions between
# Narrator, Chatter, and client. Also calls the SynthTranscriber to get the audio a couple pages ahead.

### Important question to answer is whether pages are first class citizens or not

class Narrator(ABC):
    @abstractmethod
    def load_audio_for_timestamp(self, timestamp: float) -> bytes:
        pass

    @abstractmethod
    def get_current_position(self) -> dict:
        pass
    
    @abstractmethod
    def interrupt(self, timestamp: float, user_id: str) -> None:
        pass

class ConcreteNarrator(Narrator):
    def __init__(self, book_id: str):
        self.book_id = book_id
        self.audio_buffer = {}  # Map of timestamps to audio bytes
        self.current_timestamp = 0
        self.buffer_window = {
            'back': 1,  # Pages to buffer backwards
            'forward': 2  # Pages to buffer forwards
        }

    async def load_audio_for_timestamp(self, timestamp: float) -> bytes:
        """Loads audio chunk for given timestamp and manages buffer"""
        async with get_async_db() as db:
            chunk, position = await get_audio_chunk_for_timestamp(db, self.book_id, timestamp)
            
            if not chunk:
                raise ValueError("No audio chunk found for timestamp")

            # Update current position
            self.current_timestamp = timestamp
            
            # Get surrounding pages
            start_page = max(1, chunk.start_page - self.buffer_window['back'])
            end_page = chunk.end_page + self.buffer_window['forward']
            
            pages = await get_pages_from_book(self.book_id, start_page, end_page - start_page + 1)
            
            # Build audio buffer
            buffer_audio = b""
            current_timestamp = 0
            
            for page in pages:
                if page.audio_blob:
                    self.audio_buffer[current_timestamp] = page.audio_blob
                    if current_timestamp <= timestamp < current_timestamp + page.audio_duration:
                        buffer_audio = page.audio_blob
                    current_timestamp += page.audio_duration

            return buffer_audio

    async def get_current_position(self) -> dict:
        """Get current reading position information"""
        async with get_async_db() as db:
            chunk, _ = await get_audio_chunk_for_timestamp(db, self.book_id, self.current_timestamp)
            if chunk:
                return {
                    'page': chunk.start_page,
                    'timestamp': self.current_timestamp,
                    'total_duration': chunk.end_timestamp
                }
            return None

    async def interrupt(self, timestamp: float, user_id: str) -> None:
        """Handle interruption by updating user's book state"""
        position = await self.get_current_position()
        if position:
            await update_reading_position(user_id, self.book_id, position)

    async def scrub(self, timestamp: float) -> bytes:
        """Handle scrubbing to a new position"""
        # Check if timestamp is in buffer
        for buffer_timestamp, audio in self.audio_buffer.items():
            chunk_duration = len(audio) / 44100  # Assuming 44.1kHz sample rate
            if buffer_timestamp <= timestamp < buffer_timestamp + chunk_duration:
                return audio

        # If not in buffer, load new audio
        return await self.load_audio_for_timestamp(timestamp)

 
# Honestly AI voice transcription is not very good, but will get better.
# Licensing out human audio would still be the recommended byte source.
class OpenAISynthTranscriber(SynthTranscriber):
    def __init__(self):
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
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
    
    def _convert_paragraph_text_to_buffers(self, paragraphed_text: list[str]) -> list[str]:
        """Converts paragraphed text into buffers that are under MAX_CHARS in length.
        Processing order:
        1. Tries to fit whole paragraphs into a buffer
        2. If space remains, tries to fit whole sentences
        3. If space still remains, fits individual words
        Any remaining text is added back to the start of the paragraph list for next iteration"""
        def flush_buffer() -> None:
            nonlocal current_buffer, sized_buffers
            if current_buffer.strip():
                sized_buffers.append(current_buffer.strip())
                current_buffer = ""

        def process_sentences(current_buffer: str, paragraph_chunk: str) -> tuple[bool, list[str]]:
            sentences = self._break_into_sentences(paragraph_chunk)
            did_any_fit = False
            while sentences:
                sentence = sentences.pop(0)
                if len(current_buffer + sentence + "\n") <= self.MAX_CHARS:
                    current_buffer += sentence + "\n"
                    did_any_fit = True
                else:
                    sentences.insert(0, sentence)
                    break
            return did_any_fit, current_buffer, sentences
        

        def process_words(current_buffer: str, sentences: list[str]) -> tuple[str, list[str]]:
            words = sentences.pop(0).split(' ')
            while words:
                word = words.pop(0)
                if len(current_buffer + word + " ") <= self.MAX_CHARS:
                    current_buffer += word + " "
                else:
                    words.insert(0, word)
                    break
            sentences.insert(0, " ".join(words))
            return current_buffer, sentences
        

        sized_buffers = []
        current_buffer = ""
        unprocessed_chunks = paragraphed_text
        print("\033[95mTotal paragraphs:", len(paragraphed_text))
        for i, p in enumerate(paragraphed_text):
            print(f"Paragraph {i} length:", len(p), "\033[0m")

        # Process paragraphs
        while unprocessed_chunks:
            paragraph_processed = False
            # At this point, optimistically processing paragraphs
            while unprocessed_chunks and len(current_buffer + (chunk:=unprocessed_chunks.pop(0)) + "\n") <= self.MAX_CHARS:
                current_buffer += chunk + "\n"
                paragraph_processed = True

            if not paragraph_processed:
                # process the paragragh as sentences if > max_chars
                did_any_sentences_fit, current_buffer, sentences = process_sentences(current_buffer, chunk)

                # process the sentence as words if > max_chars:
                if sentences and not did_any_sentences_fit:
                    current_buffer, sentences = process_words(current_buffer, sentences)
                    remainder = " ".join(sentences)
                    unprocessed_chunks.insert(0, remainder)

            flush_buffer()

        flush_buffer() # clear remaining buffer
        return sized_buffers if sized_buffers else [""]

    def _convert_page_to_buffered_text(self, page: Page) -> list[str]:
        unprocessed_chunks = page.paragraphed_text[::-1]
        return self._convert_paragraph_text_to_buffers(unprocessed_chunks)

    async def _convert_text_to_audio(self, text: str, voice: str = "alloy") -> bytes:
        response = await self.client.audio.speech.create(
            model="tts-1",
            input=text,
            voice=voice
        )
        return response.content
        
    async def synthesize_page_audio(self, page: Page):
        buffers = self._convert_page_to_buffered_text(page)
        audio_bytes = b""
        for buffer in buffers:
            audio_bytes += await self._convert_text_to_audio(buffer)
        return audio_bytes
    
# Singleton instances
_openai_synth = None
_narrator = None

def get_synth() -> OpenAISynthTranscriber:
    global _openai_synth
    if _openai_synth is None:
        _openai_synth = OpenAISynthTranscriber()
    return _openai_synth

def get_narrator(book_id: str) -> Narrator:
    global _narrator
    if _narrator is None or _narrator.book_id != book_id:
        _narrator = ConcreteNarrator(book_id)
    return _narrator