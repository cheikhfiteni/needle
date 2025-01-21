from pathlib import Path
import uuid
from PyPDF2 import PdfReader
from typing import Dict

from app.db.vector_database import get_vector_db, get_embedder

def _create_table_of_contents(reader: PdfReader) -> Dict:
    toc = {}
    if reader.outline:
        for item in reader.outline:
            if isinstance(item, dict) and '/Page' in item:
                toc[item.get('/Title', '')] = {
                    'page': item['/Page'],
                    'paragraph': 0,
                    'sentence': 0,
                    'timestamp': 0.0
                }
    return toc

def _break_into_pages(reader: PdfReader) -> List[str]:
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text())
    return pages

def _embed_pages(pages: List[str]) -> List[np.ndarray]:
    embedder = get_embedder()
    return [embedder.embed_text(page) for page in pages]    


def _save_pages(pages: List[str]) -> List[str]:
    vector_db = get_vector_db()
    return [vector_db.add_page(page) for page in pages]


def process_pdf_upload(file_path: Path) -> Dict:
    """
    Process an uploaded PDF file and extract its metadata.
    Returns a dictionary containing book metadata.
    """
    reader = PdfReader(str(file_path))
    
    # Generate a unique ID for the book
    book_id = str(uuid.uuid4())
    
    # Extract table of contents if available
    toc = {}
    if reader.outline:
        for item in reader.outline:
            if isinstance(item, dict) and '/Page' in item:
                toc[item.get('/Title', '')] = {
                    'page': item['/Page'],
                    'paragraph': 0,
                    'sentence': 0,
                    'timestamp': 0.0
                }
    
    metadata = {
        'reference_string': file_path.name,
        'id': book_id,
        'total_pages': len(reader.pages),
        'table_of_contents': toc
    }
    
    return metadata

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
    
    return file_path
