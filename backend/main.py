from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .database import engine, Base
from .models import Course, Video, Transcript, Question, Answer, VideoProgress
from .routers import course
import json

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Learning Platform API")

app.mount("/static", StaticFiles(directory="backend/static"), name="static")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all origins for dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(course.router)

# We will add more routers here later
