from abc import ABC, abstractmethod
from typing import List, Optional, Tuple
import numpy as np
from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session
from openai import OpenAI
from app.config import DATABASE_URL, OPENAI_API_KEY
from app.models.models import Page
import nltk
from nltk.tokenize import sent_tokenize
from contextlib import contextmanager

nltk.download('punkt_tab')
class TextEmbedder(ABC):
    @abstractmethod
    def embed_text(self, text: str) -> np.ndarray:
        pass

    @abstractmethod
    def chunk_text(self, text: str) -> List[str]:
        pass

class VectorDatabase(ABC):
    @abstractmethod
    def similarity_search(self, query_vector: np.ndarray, limit: int = 5) -> List[Tuple[float, str]]:
        pass

    @abstractmethod
    def hybrid_search(self, query_text: str, query_vector: np.ndarray, limit: int = 5) -> List[Tuple[float, str]]:
        pass

# USING OPENAI EMBEDDINGS FOR SIMPLICTY
# TODO: switch to something from https://huggingface.co/spaces/mteb/leaderboard
# Either creating our own service or using managed endpoint. Multilanguage support will also be needed.
class OpenAIEmbedder(TextEmbedder):
    def __init__(self, model="text-embedding-3-small"):
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.model = model
        
    def embed_text(self, text: str) -> np.ndarray:
        print(text)
        response = self.client.embeddings.create(
            model=self.model,
            input=text
        )
        print(text)
        print(response.data[0].embedding)
        print(len(response.data[0].embedding))
        return np.array(response.data[0].embedding)

    def chunk_text(self, text: str, method: str = "sentences", **kwargs) -> List[str]:
        if method == "sentences":
            return self._chunk_by_sentences(text, **kwargs)
        elif method == "words":
            return self._chunk_by_words(text, **kwargs)
        return self._chunk_by_paragraph(text)

    def _chunk_by_sentences(self, text: str, window_size: int = 3) -> List[str]:
        sentences = sent_tokenize(text)
        chunks = []
        
        for i in range(0, len(sentences), window_size):
            chunk = " ".join(sentences[i:i + window_size])
            chunks.append(chunk)
        return chunks

    def _chunk_by_words(self, text: str, chunk_size: int = 500, overlap: int = 100) -> List[str]:
        words = text.split()
        chunks = []
        
        for i in range(0, len(words), chunk_size - overlap):
            chunk = " ".join(words[i:i + chunk_size])
            if chunk:
                chunks.append(chunk)
        return chunks

    def _chunk_by_paragraph(self, text: str) -> List[str]:
        paragraphs = text.split('\n\n')
        return [p.strip() for p in paragraphs if p.strip()]


class PGVectorDB(VectorDatabase):
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.engine = create_engine(db_url)

    @contextmanager
    def get_session(self) -> Session:
        session = Session(self.engine)
        try:
            yield session
        finally:
            session.close()

    def similarity_search(self, query_vector: np.ndarray, limit: int = 5) -> List[Tuple[float, str]]:
        with self.get_session() as session:
            results = (
                session.query(
                    func.cosine_similarity(Page.embedding, query_vector).label('similarity'),
                    Page.paragraphed_text
                )
                .order_by(func.cosine_similarity(Page.embedding, query_vector).desc())
                .limit(limit)
                .all()
            )
            return [(float(r[0]), r[1]) for r in results]

    def hybrid_search(self, query_text: str, query_vector: np.ndarray, limit: int = 5) -> List[Tuple[float, str]]:
        with self.get_session() as session:
            results = (
                session.query(
                    func.cosine_similarity(Page.embedding, query_vector).label('similarity'),
                    Page.paragraphed_text
                )
                .filter(Page.text_search.op('@@')(func.plainto_tsquery('english', query_text)))
                .order_by(func.cosine_similarity(Page.embedding, query_vector).desc())
                .limit(limit)
                .all()
            )
            return [(float(r[0]), r[1]) for r in results]

# Singleton instances
_openai_embedder = None
_pg_vector_db = None

def get_embedder() -> OpenAIEmbedder:
    global _openai_embedder
    if _openai_embedder is None:
        _openai_embedder = OpenAIEmbedder()
    return _openai_embedder

def get_vector_db() -> PGVectorDB:
    global _pg_vector_db
    if _pg_vector_db is None:
        _pg_vector_db = PGVectorDB(DATABASE_URL)
    return _pg_vector_db
