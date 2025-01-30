from sqlalchemy import Boolean, create_engine, Column, Integer, String, DateTime, ForeignKey, Float, JSON, LargeBinary, ARRAY
from sqlalchemy.dialects.postgresql import TSVECTOR
import sqlalchemy as sa
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from app.config import DATABASE_URL
from datetime import datetime
import uuid
from sqlalchemy import event
from sqlalchemy.schema import DDL

# Try to import pgvector, but don't fail if not available
try:
    from pgvector.sqlalchemy import Vector
    HAS_PGVECTOR = True
except ImportError:
    HAS_PGVECTOR = False
    Vector = lambda dim: sa.Column(JSON)  # Fallback to JSON type

Base = declarative_base()

class VerificationCode(Base):
    __tablename__ = "verification_codes"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, index=True)
    code = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    used = Column(Boolean, default=False)
    user_id = Column(String, ForeignKey("users.id"))
    user = relationship("User", back_populates="verification_codes")

class User(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=True)
    bio_info = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    verification_codes = relationship("VerificationCode", back_populates="user", cascade="all, delete-orphan")
    book_states = relationship("UserBookState", back_populates="user")
    bookmarks = relationship("Bookmark", back_populates="user")

class Book(Base):
    __tablename__ = "books"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    reference_string = Column(String, nullable=False)
    file_blob = Column(LargeBinary)
    file_hash = Column(String, unique=True, index=True)  # SHA-256 hash of the file
    total_pages = Column(Integer, nullable=False)
    table_of_contents = Column(JSON)  # Dictionary of chapter -> page range, timestamp
    created_at = Column(DateTime, default=datetime.utcnow)
    
    pages = relationship("Page", back_populates="book")
    book_states = relationship("UserBookState", back_populates="book")
    audio_files = relationship("AudioChunk", back_populates="book")

class Page(Base):
    __tablename__ = "pages"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    book_id = Column(String, ForeignKey("books.id"))
    page_number = Column(Integer, nullable=False)
    chapter = Column(String)
    paragraphed_text = Column(ARRAY(String), nullable=False)  # Array of paragraphs
    sentenced_text = Column(ARRAY(String), nullable=False)    # Array of sentences
    
    # Audio related fields
    audio_blob = Column(LargeBinary, nullable=True)  # Raw audio data
    audio_start_offset = Column(Float, nullable=True)  # Start time in chapter
    audio_duration = Column(Float, nullable=True)     # Duration of page audio
    chapter_audio_offset = Column(Float, nullable=True)  # Start time in book
    
    # Vector search columns - will store as JSON if pgvector not available
    embedding = Vector(1536)  # OpenAI's embedding dimension
    text_search = Column(TSVECTOR)
    chunk_embeddings = Column(JSON)  # Store chunk-level embeddings
    
    book = relationship("Book", back_populates="pages")

class UserBookState(Base):
    __tablename__ = "user_book_states"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"))
    book_id = Column(String, ForeignKey("books.id"))
    cursor_position = Column(JSON)  # {page, paragraph, sentence, timestamp}
    last_accessed = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
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

class AudioChunk(Base):
    __tablename__ = "audio_chunks"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    book_id = Column(String, ForeignKey("books.id"))
    sequence_number = Column(Integer, nullable=False)
    start_page = Column(Integer, nullable=False)
    end_page = Column(Integer, nullable=False)
    start_timestamp = Column(Float, nullable=False)
    end_timestamp = Column(Float, nullable=False)
    audio_blob = Column(LargeBinary)  # For direct DB storage
    
    book = relationship("Book", back_populates="audio_files")

    __table_args__ = (
        sa.Index('idx_book_timestamps', 'book_id', 'start_timestamp', 'end_timestamp'),
    )

engine = create_engine(DATABASE_URL)

# Actually allows us to use pgvector
event.listen(
    Base.metadata,
    'before_create',
    DDL('CREATE EXTENSION IF NOT EXISTS vector;')
)

# First create a function to handle array to tsvector conversion
create_array_to_tsvector = DDL("""
    CREATE OR REPLACE FUNCTION pages_trigger_function() RETURNS trigger AS $$
    BEGIN
        NEW.text_search := to_tsvector('pg_catalog.english', array_to_string(NEW.paragraphed_text, ' '));
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
""")

# Then create the trigger that uses this function
create_trigger = DDL("""
    CREATE TRIGGER tsvector_update 
    BEFORE INSERT OR UPDATE ON pages
    FOR EACH ROW 
    EXECUTE FUNCTION pages_trigger_function();
""")

# Register both events
event.listen(
    Page.__table__, 
    'after_create',
    create_array_to_tsvector.execute_if(dialect='postgresql')
)

event.listen(
    Page.__table__, 
    'after_create',
    create_trigger.execute_if(dialect='postgresql')
)

Base.metadata.create_all(engine)