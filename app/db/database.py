from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from contextlib import contextmanager, asynccontextmanager
from app.config import DATABASE_URL
from typing import Optional
from uuid import UUID

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

async def get_user_by_email(email: str) -> Optional[dict]:
    async with get_async_db() as session:
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
