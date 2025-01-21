from sqlalchemy import Boolean, create_engine, Column, Integer, String, DateTime, ForeignKey, Float, JSON, LargeBinary
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from app.config import DATABASE_URL
from datetime import datetime
import uuid

Base = declarative_base()

class VerificationCode(Base):
    __tablename__ = "verification_codes"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, index=True)
    code = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    used = Column(Boolean, default=False)
    user = relationship("User", back_populates="verification_codes")

class User(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=True)
    bio_info = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    verification_codes = relationship("VerificationCode", back_populates="user")
    book_states = relationship("UserBookState", back_populates="user")
    bookmarks = relationship("Bookmark", back_populates="user")

class Book(Base):
    __tablename__ = "books"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    reference_string = Column(String, nullable=False)
    file_blob = Column(LargeBinary)
    total_pages = Column(Integer, nullable=False)
    table_of_contents = Column(JSON)  # Dictionary of chapter -> page range
    created_at = Column(DateTime, default=datetime.utcnow)
    
    pages = relationship("Page", back_populates="book")
    book_states = relationship("UserBookState", back_populates="book")

class Page(Base):
    __tablename__ = "pages"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    book_id = Column(String, ForeignKey("books.id"))
    page_number = Column(Integer, nullable=False)
    chapter = Column(String)
    paragraphed_text = Column(String, nullable=False)
    sentenced_text = Column(String, nullable=False)
    audio_chunks = Column(JSON)  # List of audio chunk metadata
    
    book = relationship("Book", back_populates="pages")

class UserBookState(Base):
    __tablename__ = "user_book_states"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"))
    book_id = Column(String, ForeignKey("books.id"))
    cursor_position = Column(JSON)  # {page, paragraph, sentence, timestamp}
    last_accessed = Column(DateTime, default=datetime.utcnow)
    voice_settings = Column(JSON)  # {speed, voice, etc.}
    
    user = relationship("User", back_populates="book_states")
    book = relationship("Book", back_populates="book_states")

class Bookmark(Base):
    __tablename__ = "bookmarks"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"))
    book_id = Column(String, ForeignKey("books.id"))
    position = Column(JSON)  # {page, paragraph, sentence}
    timestamp = Column(Float)
    note = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="bookmarks")

class Question(Base):
    __tablename__ = "questions"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"))
    book_id = Column(String, ForeignKey("books.id"))
    question_text = Column(String, nullable=False)
    answer_text = Column(String)
    position = Column(JSON)  # Position when question was asked
    created_at = Column(DateTime, default=datetime.utcnow)

# Initialize database
engine = create_engine(DATABASE_URL)
Base.metadata.create_all(engine)