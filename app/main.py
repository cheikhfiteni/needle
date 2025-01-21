from fastapi import Depends, FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from app.services.authentication import ACCESS_TOKEN_EXPIRE_MINUTES, SECRET_KEY, router as auth_router, get_current_user
from app.models.models import Book, User
from starlette.middleware.sessions import SessionMiddleware

from typing import Dict, Literal, Optional
from pydantic import BaseModel

class ReadingPosition(BaseModel):
    page: int
    paragraph: int
    sentence: int
    timestamp: float

class BookMetadata(BaseModel):
    reference_string: str
    id: str
    total_pages: int
    table_of_contents: Dict[str, ReadingPosition]

class VoiceSettings(BaseModel):
    speed: float
    voice: str

class BookmarkCreate(BaseModel):
    book_id: str
    position: ReadingPosition
    note: Optional[str]

class QuestionCreate(BaseModel):
    book_id: str
    question: str
    position: ReadingPosition

class NavigationTarget(BaseModel):
    type: Literal['page', 'chapter', 'bookmark']
    value: str

class SearchQuery(BaseModel):
    book_id: str
    query: str
    type: Literal['text', 'semantic']
    scope: Optional[dict]

app = FastAPI()
app.include_router(auth_router, prefix="/auth", tags=["authentication"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
        SessionMiddleware,
        secret_key=SECRET_KEY,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60
)

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/")
async def root():
    return {"message": "Hello World from Needle, the interactive storyteller."}

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/api/books", response_model=BookMetadata)
async def upload_book(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    pass

@app.get("/api/books/{book_id}", response_model=BookMetadata)
async def get_book(
    book_id: str,
    current_user: User = Depends(get_current_user)
):
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return book

@app.get("/api/books/{book_id}/position", response_model=ReadingPosition)
async def get_reading_position(
    book_id: str,
    user_id: str,
    current_user: User = Depends(get_current_user)
):
    state = db.query(UserBookState).filter(
        UserBookState.book_id == book_id,
        UserBookState.user_id == user_id
    ).first()
    if not state:
        raise HTTPException(status_code=404, detail="Reading state not found")
    return state.cursor_position

@app.websocket("/api/narration/stream/{book_id}")
async def narration_stream(
    websocket: WebSocket,
    book_id: str,
    position: Optional[ReadingPosition] = None
):
    await websocket.accept()
    pass

@app.post("/api/narration/start")
async def start_narration(
    book_id: str,
    position: Optional[ReadingPosition] = None,
    voice_settings: Optional[VoiceSettings] = None,
    current_user: User = Depends(get_current_user)
):
    pass

@app.post("/api/narration/pause")
async def pause_narration(
    book_id: str,
    position: ReadingPosition,
    current_user: User = Depends(get_current_user)
):
    pass

@app.post("/api/narration/resume")
async def resume_narration(
    book_id: str,
    position: ReadingPosition,
    current_user: User = Depends(get_current_user)
):
    pass

@app.post("/api/questions/ask")
async def ask_question(
    question: QuestionCreate,
    current_user: User = Depends(get_current_user)
):
    pass

@app.post("/api/bookmarks", response_model=dict)
async def create_bookmark(
    bookmark: BookmarkCreate,
    current_user: User = Depends(get_current_user)
):
    new_bookmark = Bookmark(
        book_id=bookmark.book_id,
        position=bookmark.position.dict(),
        note=bookmark.note
    )
    db.add(new_bookmark)
    db.commit()
    return new_bookmark

@app.get("/api/bookmarks/{book_id}")
async def get_bookmarks(
    book_id: str,
    user_id: str,
    current_user: User = Depends(get_current_user)
):
    bookmarks = db.query(Bookmark).filter(
        Bookmark.book_id == book_id,
        Bookmark.user_id == user_id
    ).all()
    return bookmarks

@app.post("/api/navigation/jump")
async def jump_to_position(
    target: NavigationTarget,
    book_id: str,
    current_user: User = Depends(get_current_user)
):
    pass

@app.post("/api/search")
async def search_book(
    search: SearchQuery,
    current_user: User = Depends(get_current_user)
):
    pass
