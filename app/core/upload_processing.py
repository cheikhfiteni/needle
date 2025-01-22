from pathlib import Path
import uuid
from PyPDF2 import PdfReader
from typing import Dict, List, Optional
import numpy as np

from app.db.vector_database import get_vector_db, get_embedder
from app.db.database import create_book, create_user_book_state, create_page
from app.models.models import Book, UserBookState, Page

def _hash_consolidation_check(file_path: Path) -> bool:
    # TODO: Implement hash consolidation check
    return False

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
    print("Embedding pages done")
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
    reader = PdfReader(str(file_path))
    
    # Read file content for storage
    with open(file_path, 'rb') as f:
        file_blob = f.read()
    
    # Extract basic metadata
    toc = _create_table_of_contents(reader)
    total_pages = len(reader.pages)
    print(f"Total pages: {total_pages}")
    
    # Create book entry
    book = await create_book(
        reference_string=file_path.name,
        file_blob=file_blob,
        total_pages=total_pages,
        table_of_contents=toc
    )
    
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
    print(f"Book state created: {book_state.id}")
    # Process pages
    pages = _extract_pages_text(reader)
    embeddings = _embed_pages(pages)
    
    # Create page entries with chunking and embeddings
    for page_num, (page_text, embedding) in enumerate(zip(pages, embeddings)):
        print("Saving page", page_num)
        chunks = _chunk_page(page_text)
        
        # Create page with all data
        await create_page(
            book_id=book.id,
            page_number=page_num,
            paragraphed_text='\n\n'.join(chunks['paragraphs']),
            sentenced_text='\n'.join(chunks['sentences']),
            embedding=embedding,
            chunk_embeddings=None  # Optional, can be updated later if needed
        )
    
    return {
        'id': book.id,
        'reference_string': file_path.name,
        'total_pages': total_pages,
        'table_of_contents': toc,
        'user_book_state_id': book_state.id
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
