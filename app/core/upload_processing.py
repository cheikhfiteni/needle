from pathlib import Path
import uuid
from PyPDF2 import PdfReader
from typing import Dict, List, Optional
import numpy as np
import hashlib
import os

from app.db.vector_database import get_embedder
from app.db.database import create_book, create_user_book_state, create_page, get_book_by_hash, get_book_by_id, save_page_audio, get_user_book_state_by_ids, get_pages_from_book
from app.models.models import Book

from app.core.reader import get_synth
import asyncio

def _hash_file(file_path: Path) -> str:
    """Calculate SHA-256 hash of a file"""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        # Read file in chunks to handle large files
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def _cleanup_temp_file(file_path: Path) -> None:
    try:
        os.remove(file_path)
        print(f"Cleaned up temp file {file_path}")
    except Exception as e:
        print(f"Error cleaning up temp file: {e}")

async def _hash_consolidation_check(file_path: Path, user_id: str) -> Optional[Dict]:
    """
    Check if we already have this file processed
    Returns book state metadata if found, None otherwise
    """
    file_hash = _hash_file(file_path)
    existing_book = await get_book_by_hash(file_hash)

    if not existing_book:
        return None
    
    print(f"Book exists in global catalog with hash {file_hash}")
    existing_user_book_state = await get_user_book_state_by_ids(user_id, existing_book.id)

    if existing_user_book_state:
        book_state_metadata = {
            'id': existing_book.id,
            'reference_string': existing_book.reference_string,
            'total_pages': existing_book.total_pages,
            'table_of_contents': existing_book.table_of_contents,
            'user_book_state_id': existing_user_book_state.id,
            'reused_existing': True
        }
    else:
        book_state = await create_user_book_state(
            user_id=user_id,
            book_id=existing_book.id,
            cursor_position={'page': 0, 'paragraph': 0, 'sentence': 0, 'timestamp': 0.0},
            voice_settings={'speed': 1.0, 'voice': 'default', 'volume': 1.0}
        )
        book_state_metadata = {
            'id': existing_book.id,
            'reference_string': existing_book.reference_string,
            'total_pages': existing_book.total_pages,
            'table_of_contents': existing_book.table_of_contents,
            'user_book_state_id': book_state.id,
            'reused_existing': False
        }

    _cleanup_temp_file(file_path)
    return book_state_metadata


async def audio_entire_book(book_id: str) -> None:
    """
    Generate and save audio for an entire book, processing pages sequentially
    and maintaining timing information.
    """
    synth = get_synth()
    current_chapter: Optional[str] = None
    chapter_offset = 0.0
    
    print(f"\nStarting audio generation for book: {book_id}")
    
    # Get all pages using the database function
    pages = await get_pages_from_book(book_id, 0, 999999)  # Large number to get all pages
    
    for page in pages:
        print(f"Processing page {page.page_number}")
        print(page)
        # Track chapter transitions
        if page.chapter != current_chapter:
            if current_chapter is not None:
                print(f"\nCompleted chapter {current_chapter}")
            current_chapter = page.chapter
            chapter_offset = 0.0
            print(f"\nStarting chapter: {current_chapter}")
        
        try:
            # Generate audio for the page
            print(f"Generating audio for page {page.page_number}")
            audio_bytes = await synth.synthesize_page_audio(page)
            duration = len(audio_bytes) / 32000  # Approximate duration
            
            # Save the audio with timing information
            await save_page_audio(
                audio_bytes=audio_bytes,
                page_id=page.id,
                duration=duration,
                chapter_offset=chapter_offset
            )
            
            # Update offset for next page
            chapter_offset += duration
            print("\033[91mSaved page audio\033[0m")
            
        except Exception as e:
            print(f"Error processing page {page.page_number}: {str(e)}")
            continue

def _create_table_of_contents(reader: PdfReader) -> Dict:
    toc = {}
    if not reader.outline:
        return toc
        
    def process_outline_item(item) -> Dict:
        if isinstance(item, dict):
            return {
                'title': item.get('/Title', ''),
                'page_number': 0, # everything about TOC needs to change
                'timestamp': 0.0
            }
        elif isinstance(item, list):
            # Handle nested chapters like in Great Gatsby
            return [process_outline_item(subitem) for subitem in item]
        return None
        
    # Process each outline item
    for i, item in enumerate(reader.outline):
        result = process_outline_item(item)
        if isinstance(result, list):
            # TODO: Fix, this should probably be a list rather than a dict
            for j, chapter in enumerate(result):
                if chapter:  # Only add valid entries
                    toc[str(j)] = chapter
        elif result:
            toc[str(i)] = result
            
    return toc

def _extract_pages_text(reader: PdfReader) -> List[str]:
    pages = []
    index = 0
    for page in reader.pages:
        print(f"Extracting text from page {(index := index + 1)}")
        pages.append(page.extract_text())
    return pages

def _embed_pages(pages: List[str]) -> List[np.ndarray]:
    print("Embedding pages")
    embedder = get_embedder()
    return [embedder.embed_text(page) for page in pages]    

def _chunk_page(page_text: str) -> Dict[str, List[str]]:
    embedder = get_embedder()
    paragraphs = embedder.chunk_text(page_text, method="paragraphs")
    sentences = embedder.chunk_text(page_text, method="sentences")
    return {
        'paragraphs': paragraphs,
        'sentences': sentences
    }

async def process_pdf_upload(file_path: Path, user_id: str) -> Dict:
    """
    Process an uploaded PDF file and create all necessary database entries.
    Returns a dictionary containing book metadata.
    """
    # Check if we already have this file
    if book_state_metadata := await _hash_consolidation_check(file_path, user_id):
        return book_state_metadata
    
    reader = PdfReader(str(file_path))
    file_hash = _hash_file(file_path)
    
    # Read file content for storage
    with open(file_path, 'rb') as f:
        file_blob = f.read()
    
    # Extract basic metadata
    toc = _create_table_of_contents(reader)
    total_pages = len(reader.pages)
    print(f"Total pages: {total_pages}")
    print("Creating book")
    # Create book entry
    book = await create_book(
        reference_string=file_path.name,
        file_blob=file_blob,
        file_hash=file_hash,
        total_pages=total_pages,
        table_of_contents=toc
    )
    print("Book created")
    # Initialize user book state
    initial_cursor = {
        'page': 0,
        'paragraph': 0,
        'sentence': 0,
        'timestamp': 0.0
    }
    default_voice_settings = {
        'speed': 1.0,
        'voice': 'default',
        'volume': 1.0
    }
    
    book_state = await create_user_book_state(
        user_id=user_id,
        book_id=book.id,
        cursor_position=initial_cursor,
        voice_settings=default_voice_settings
    )
    print("Book state created")
    # Process pages
    pages = _extract_pages_text(reader)
    embeddings = _embed_pages(pages)
    
    # Create page entries with chunking and embeddings
    for page_num, (page_text, embedding) in enumerate(zip(pages, embeddings)):
        print("Saving page", page_num)
        chunks = _chunk_page(page_text)
        
        await create_page(
            book_id=book.id,
            page_number=page_num,
            paragraphed_text=chunks['paragraphs'],
            sentenced_text=chunks['sentences'],
            embedding=embedding,
            chunk_embeddings=None
        )
    print("Creating pages done")    
    asyncio.create_task(audio_entire_book(book.id))
    print("Audio processing started")
    return {
        'id': book.id,
        'reference_string': file_path.name,
        'total_pages': total_pages,
        'table_of_contents': toc,
        'user_book_state_id': book_state.id,
        'reused_existing': False
    }

def save_uploaded_file(file_content: bytes, filename: str, upload_dir: Path) -> Path:
    """
    Save an uploaded file to disk and return its path.
    """
    # Create upload directory if it doesn't exist
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate unique filename to avoid collisions
    file_path = upload_dir / f"{uuid.uuid4()}_{filename}"
    
    with open(file_path, 'wb') as f:
        f.write(file_content)
    print(f"File saved to: {file_path}")
    return file_path
