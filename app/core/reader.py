from abc import ABC, abstractmethod
import os
import re
from openai import AsyncOpenAI
from sqlalchemy import select, and_
from app.db.database import get_async_db, get_audio_chunk_for_timestamp
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

def get_narrator() -> Narrator:
    global _narrator
    if _narrator is None:
        _narrator = Narrator()
    return _narrator