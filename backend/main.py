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

# Auto-migrate: add new columns if missing
from sqlalchemy import inspect as sa_inspect, text
with engine.connect() as conn:
    video_cols = [c['name'] for c in sa_inspect(engine).get_columns('videos')]
    if 'local_filename' not in video_cols:
        conn.execute(text("ALTER TABLE videos ADD COLUMN local_filename VARCHAR(512)"))
    course_cols = [c['name'] for c in sa_inspect(engine).get_columns('courses')]
    if 'source_path' not in course_cols:
        conn.execute(text("ALTER TABLE courses ADD COLUMN source_path VARCHAR(1024)"))
    if 'thumbnail' not in course_cols:
        conn.execute(text("ALTER TABLE courses ADD COLUMN thumbnail VARCHAR(512)"))
    conn.commit()

app = FastAPI(title="Learning Platform API")

app.mount("/static", StaticFiles(directory="backend/static"), name="static")

# Serve locally downloaded videos
videos_dir = os.path.join(os.path.dirname(__file__), "videos")
os.makedirs(videos_dir, exist_ok=True)
app.mount("/videos", StaticFiles(directory=videos_dir), name="videos")

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
