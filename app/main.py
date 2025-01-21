from fastapi import Depends, FastAPI, File, UploadFile, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from app.services.authentication import ACCESS_TOKEN_EXPIRE_MINUTES, SECRET_KEY, router as auth_router, get_current_user
from app.models.models import Book, User
from starlette.middleware.sessions import SessionMiddleware

from typing import Dict, List, Literal, Optional
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

# Actually think speedup should be handled on the client
# and we should just send the current position to the server
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

@app.post("/api/books/upload", response_model=BookMetadata)
async def upload_book(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    pass

@app.get("/api/books/list", response_model=List[BookMetadata])
async def list_books(
    current_user: User = Depends(get_current_user)
):
    pass

@app.get("/api/books/{book_id}", response_model=BookMetadata)
async def get_book(
    book_id: str,
    current_user: User = Depends(get_current_user)
):
    pass

@app.get("/api/books/{book_id}/position", response_model=ReadingPosition)
async def get_reading_position(
    book_id: str,
    user_id: str,
    current_user: User = Depends(get_current_user)
):
    pass

@app.post("/api/books/{book_id}/position")
async def set_reading_position(
    book_id: str,
    position: ReadingPosition,
    current_user: User = Depends(get_current_user)
):
    pass

# potentially don't stream, but send buffer and let the client handle pacing
# polling for the next chunk when the current one is done. Better for latency?
@app.websocket("/api/narration/stream/{book_id}")
async def narration_stream(
    websocket: WebSocket,
    book_id: str,
    position: Optional[ReadingPosition] = None # if None, start from the beginning
):
    await websocket.accept()
    pass

@app.post("/api/narration/pause")
async def pause_narration(
    book_id: str,
    position: ReadingPosition,
    current_user: User = Depends(get_current_user)
):
    pass

@app.post("/api/chat/ask")
async def ask_question(
    question: QuestionCreate,
    current_user: User = Depends(get_current_user)
):
    pass


## IGNORE EVERYTHING BELOW THIS LINE FOR NOW
## DO SEARCH FIRST BEFORE BOOKMARKS, IDEALLY PAGE, ETC SEARCH
## AND THEN ONWARDS

@app.post("/api/bookmarks", response_model=dict)
async def create_bookmark(
    bookmark: BookmarkCreate,
    current_user: User = Depends(get_current_user)
):
    pass

@app.get("/api/bookmarks/{book_id}")
async def get_bookmarks(
    book_id: str,
    user_id: str,
    current_user: User = Depends(get_current_user)
):
    pass

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
