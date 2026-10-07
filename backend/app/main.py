from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import init_db
from app.api import upload, analysis, chat

app = FastAPI(
    title="LexClarity API",
    description="AI-powered legal document analysis and RAG chatbot.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Never leak stack traces / internals to the client.
    return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred. Please try again."})


app.include_router(upload.router)
app.include_router(analysis.router)
app.include_router(chat.router)


@app.get("/")
def root():
    return {"service": "LexClarity API", "status": "ok"}


@app.get("/health")
def health():
    return {"status": "ok"}
