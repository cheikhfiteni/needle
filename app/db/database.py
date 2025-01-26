from sqlalchemy import create_engine, select, and_
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from contextlib import contextmanager, asynccontextmanager
from app.config import DATABASE_URL
from typing import Optional, List, Dict
from uuid import UUID
from app.models.models import AudioChunk, Page, User, Book, UserBookState, VerificationCode
from datetime import datetime
import numpy as np

# Sync SQLAlchemy engine
engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(bind=engine)

# Async engine
async_engine = create_async_engine(
    DATABASE_URL.replace('postgresql://', 'postgresql+asyncpg://').replace("?sslmode=", "?ssl=")
)
AsyncSessionLocal = sessionmaker(
    async_engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

@contextmanager
def get_db_session() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

@asynccontextmanager
async def get_async_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

async def get_user_by_email(email: str) -> Optional[User]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

async def get_book_by_id(book_id: UUID) -> Optional[dict]:
    async with get_async_db() as session:
        result = await session.execute(
            select(Book).where(Book.id == book_id)
        )
        return result.scalar_one_or_none()

async def get_user_book_state(user_id: UUID, book_id: UUID) -> Optional[dict]:
    async with get_async_db() as session:
        result = await session.execute(
            select(UserBookState).where(
                and_(
                    UserBookState.user_id == user_id,
                    UserBookState.book_id == book_id
                )
            )
        )
        return result.scalar_one_or_none()

async def create_verification_code(email: str, code: str, expires_at: datetime) -> VerificationCode:
    async with AsyncSessionLocal() as session:
        verification_code = VerificationCode(
            email=email,
            code=code,
            expires_at=expires_at
        )
        session.add(verification_code)
        await session.commit()
        await session.refresh(verification_code)
        return verification_code

async def get_valid_verification_code(email: str, code: str) -> Optional[VerificationCode]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(VerificationCode).where(
                and_(
                    VerificationCode.email == email,
                    VerificationCode.code == code,
                    VerificationCode.used == False,
                    VerificationCode.expires_at > datetime.utcnow()
                )
            ).order_by(VerificationCode.created_at.desc())
        )
        return result.scalar_one_or_none()

async def create_book(reference_string: str, file_blob: bytes, file_hash: str, total_pages: int, table_of_contents: dict) -> Book:
    print("Creating book")
    async with AsyncSessionLocal() as session:
        book = Book(
            reference_string=reference_string,
            file_blob=file_blob,
            file_hash=file_hash,
            total_pages=total_pages,
            table_of_contents=table_of_contents
        )
        session.add(book)
        await session.commit()
        await session.refresh(book)
        return book

async def get_pages_from_book(book_id: str, start_page: int, num_pages: int) -> List[Page]:
    async with AsyncSessionLocal() as session:
        # Get book to check total pages
        book_result = await session.execute(
            select(Book).where(Book.id == book_id)
        )
        book = book_result.scalar_one_or_none()
        
        if not book:
            return []
            
        # Adjust num_pages if it would exceed book length
        pages_remaining = book.total_pages - start_page + 1
        pages_to_fetch = min(num_pages, pages_remaining)
        
        if pages_to_fetch <= 0:
            return []
            
        result = await session.execute(
            select(Page)
            .where(
                and_(
                    Page.book_id == book_id,
                    Page.page_number >= start_page,
                    Page.page_number < start_page + pages_to_fetch
                )
            )
            .order_by(Page.page_number)
        )
        
        return result.scalars().all()

async def create_user_book_state(user_id: str, book_id: str, cursor_position: Dict, voice_settings: Dict) -> UserBookState:
    async with AsyncSessionLocal() as session:
        book_state = UserBookState(
            user_id=user_id,
            book_id=book_id,
            cursor_position=cursor_position,
            voice_settings=voice_settings
        )
        session.add(book_state)
        await session.commit()
        await session.refresh(book_state)
        return book_state

async def create_page(
    book_id: str,
    page_number: int,
    paragraphed_text: List[str],
    sentenced_text: List[str],
    embedding: np.ndarray,
    chunk_embeddings: Optional[Dict] = None,
    chapter: Optional[str] = None
) -> Page:
    async with AsyncSessionLocal() as session:
        page = Page(
            book_id=book_id,
            page_number=page_number,
            chapter=chapter,
            paragraphed_text=paragraphed_text,
            sentenced_text=sentenced_text,
            embedding=embedding.tolist(),  # Convert numpy array to list for storage
            chunk_embeddings=chunk_embeddings
        )
        session.add(page)
        await session.commit()
        await session.refresh(page)
        return page

async def get_user_books(user_id: str) -> List[Book]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Book)
            .join(UserBookState, and_(
                UserBookState.book_id == Book.id,
                UserBookState.user_id == user_id
            ))
        )
        return [row[0] for row in result.all()]

async def get_book_with_state(book_id: str, user_id: str) -> Optional[tuple[Book, UserBookState]]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Book, UserBookState)
            .join(UserBookState, and_(
                UserBookState.book_id == Book.id,
                UserBookState.user_id == user_id
            ))
            .where(Book.id == book_id)
        )
        row = result.first()
        return row if row else None

async def update_reading_position(user_id: str, book_id: str, position: dict) -> Optional[UserBookState]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserBookState).where(
                and_(
                    UserBookState.user_id == user_id,
                    UserBookState.book_id == book_id
                )
            )
        )
        state = result.scalar_one_or_none()
        if state:
            state.cursor_position = position
            await session.commit()
            await session.refresh(state)
        return state

async def get_audio_chunk_for_timestamp(book_id: str, timestamp: float) -> tuple[Optional[AudioChunk], float]:
    """
    Gets the audio chunk and relative position for a given timestamp in a book
    Returns (chunk, relative_position) tuple
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AudioChunk).where(
                and_(
                    AudioChunk.book_id == book_id,
                    AudioChunk.start_timestamp <= timestamp,
                    AudioChunk.end_timestamp > timestamp
                )
            )
        )
        chunk = result.scalar_one_or_none()
        
        if not chunk:
            return None, 0.0
            
        relative_position = timestamp - chunk.start_timestamp
        return chunk, relative_position

async def save_page_audio(audio_bytes: bytes, page_id: str, duration: float, chapter_offset: float = 0.0) -> None:
    """
    Save audio data for a page with timing information
    
    Args:
        audio_bytes: Raw audio data
        page_id: ID of the page to save audio for
        duration: Duration of the audio in seconds
        chapter_offset: Offset from start of chapter in seconds
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Page).where(Page.id == page_id))
        page = result.scalar_one_or_none()
        
        if not page:
            raise ValueError(f"Page {page_id} not found")
            
        # Update page audio data
        page.audio_blob = audio_bytes
        page.audio_duration = duration
        page.audio_start_offset = chapter_offset
        
        # Calculate chapter offset based on previous pages if not provided
        if chapter_offset == 0.0:
            prev_pages = await session.execute(
                select(Page)
                .where(and_(
                    Page.book_id == page.book_id,
                    Page.chapter == page.chapter,
                    Page.page_number < page.page_number
                ))
                .order_by(Page.page_number)
            )
            prev_pages = prev_pages.scalars().all()
            
            if prev_pages:
                last_page = prev_pages[-1]
                page.audio_start_offset = (last_page.audio_start_offset or 0.0) + (last_page.audio_duration or 0.0)
        
        await session.commit()
        print(f"Saved audio for page {page.page_number} - Duration: {duration:.2f}s, Offset: {page.audio_start_offset:.2f}s")

async def get_book_by_hash(file_hash: str) -> Optional[Book]:
    """Get book by file hash"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Book).where(Book.file_hash == file_hash)
        )
        return result.scalar_one_or_none()

async def get_user_book_state_by_ids(user_id: str, book_id: str) -> Optional[UserBookState]:
    """Get user book state by user_id and book_id"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserBookState).where(
                and_(
                    UserBookState.user_id == user_id,
                    UserBookState.book_id == book_id
                )
            )
        )
        return result.scalar_one_or_none()
