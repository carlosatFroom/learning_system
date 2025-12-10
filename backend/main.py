from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .database import engine, Base
from .models import Course, Video, Transcript, Question, Answer, VideoProgress
from backend.routers import course, sync
import json
import os
from dotenv import load_dotenv

# Load env variables from backend/.env
env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)

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
app.include_router(sync.router)

# We will add more routers here later
