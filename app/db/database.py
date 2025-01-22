from sqlalchemy import create_engine, select, and_
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from contextlib import contextmanager, asynccontextmanager
from app.config import DATABASE_URL
from typing import Optional, List, Dict
from uuid import UUID
from app.models.models import Page, User, Book, UserBookState, VerificationCode
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

async def create_book(reference_string: str, file_blob: bytes, total_pages: int, table_of_contents: dict) -> Book:
    async with AsyncSessionLocal() as session:
        book = Book(
            reference_string=reference_string,
            file_blob=file_blob,
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
    paragraphed_text: str,
    sentenced_text: str,
    embedding: np.ndarray,
    chunk_embeddings: Optional[Dict] = None,
    chapter: Optional[str] = None,
    audio_chunks: Optional[Dict] = None
) -> Page:
    async with AsyncSessionLocal() as session:
        page = Page(
            book_id=book_id,
            page_number=page_number,
            chapter=chapter,
            paragraphed_text=paragraphed_text,
            sentenced_text=sentenced_text,
            embedding=embedding.tolist(),  # Convert numpy array to list for storage
            chunk_embeddings=chunk_embeddings,
            audio_chunks=audio_chunks
        )
        session.add(page)
        await session.commit()
        await session.refresh(page)
        return page

