from sqlalchemy import Column, Integer, String, Text, ForeignKey, Boolean, DateTime, Float
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base

class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), index=True)
    description = Column(Text, nullable=True)
    playlist_id = Column(String(255), unique=True, index=True)
    is_hidden = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    videos = relationship("Video", back_populates="course")

class Video(Base):
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"))
    youtube_id = Column(String(255), index=True)
    title = Column(String(255))
    order = Column(Integer)
    duration = Column(Integer) # In seconds

    course = relationship("Course", back_populates="videos")
    transcripts = relationship("Transcript", back_populates="video")
    questions = relationship("Question", back_populates="video")
    progress = relationship("VideoProgress", back_populates="video")

class Transcript(Base):
    __tablename__ = "transcripts"

    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(Integer, ForeignKey("videos.id"))
    text = Column(Text)
    start_time = Column(Float)
    duration = Column(Float)
    
    video = relationship("Video", back_populates="transcripts")

class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(Integer, ForeignKey("videos.id"))
    text = Column(Text)
    kind = Column(String(50)) # 'text', 'multiple_choice', 'image_upload'
    correct_answer_summary = Column(Text, nullable=True)
    timestamp_reference = Column(Float, nullable=True)
    follow_up_to_id = Column(Integer, nullable=True) # ID of question this follows up on
    
    video = relationship("Video", back_populates="questions")
    answers = relationship("Answer", back_populates="question")

class Answer(Base):
    __tablename__ = "answers"

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"))
    user_answer = Column(Text) # Or path to image/audio
    is_correct = Column(Boolean)
    rating = Column(Integer, default=0) # 0-100
    feedback = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    question = relationship("Question", back_populates="answers")

class VideoProgress(Base):
    __tablename__ = "video_progress"

    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(Integer, ForeignKey("videos.id"))
    user_id = Column(String(255), default="user") # Placeholder for single user
    completed = Column(Boolean, default=False)
    score = Column(Integer, default=0)
    last_watched_timestamp = Column(Float, default=0.0)
    updated_at = Column(DateTime, default=datetime.utcnow)

    video = relationship("Video", back_populates="progress")
